# -*- coding: utf-8 -*-
"""
drivers/asr.py — 语音识别 (ASR)
=================================
三种实现: whisper (本地), mock (终端输入), 云端 (TODO)
"""

from __future__ import annotations

import sys
import os
import time
import wave
import queue
import tempfile
import threading
import re
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar import config


class _SpeechGate:
    """RMS gate without a deaf calibration period at the start of a sentence."""

    def __init__(self, threshold_max, speech_ms, silence_ms):
        self.threshold_max = max(0.002, threshold_max)
        self.threshold = min(self.threshold_max, 0.003)
        self.speech_ms = speech_ms
        self.silence_ms = silence_ms
        self.speech = self.silence = 0
        self.started = False
        self.noise = []

    def feed(self, rms, duration_ms=100):
        if not self.started:
            if rms > self.threshold:
                self.speech += duration_ms
                if self.speech >= self.speech_ms:
                    self.started = True
                    return "start"
            else:
                self.speech = 0
                # Only quiet chunks calibrate the noise floor, never speech.
                self.noise = (self.noise + [rms])[-30:]
                self.threshold = min(self.threshold_max,
                                     max(0.002, sum(self.noise) / len(self.noise) * 1.8))
            return "waiting"
        # Lower release threshold preserves quiet syllables within a sentence.
        self.silence = (0 if rms > self.threshold * 0.65 else
                        self.silence + duration_ms)
        return "done" if self.silence >= self.silence_ms else "record"


class ASRDriver:
    """语音识别"""

    def __init__(self, mode: str = config.ASR_MODE):
        self.mode = mode
        self._model = None
        self._fast_model = None
        self._input_device = None
        self.last_debug = {}
        self.paused = False
        self._lock = threading.Lock()
        self._abort = threading.Event()   # 打断正在进行的收音 (面板要独占麦克风)
        self._audio_queue: "queue.Queue[bytes]" = queue.Queue()
        self._running = False

        if mode == "whisper":
            self._init_whisper()
        elif mode == "mock":
            print("[ASR] Mock 模式 (从终端读输入)")
        else:
            print(f"[ASR] 未知模式 {mode}, 退回 mock")
            self.mode = "mock"

    # ========================================================================
    def _init_whisper(self):
        try:
            from faster_whisper import WhisperModel
            device = "cpu"
            compute_type = "int8"
            print(f"[ASR] 加载 faster-whisper {config.WHISPER_MODEL} ...")
            self._model = WhisperModel(config.WHISPER_MODEL,
                                       device=device,
                                       compute_type=compute_type,
                                       cpu_threads=3)
            print("[ASR] whisper 加载成功")
            if config.WHISPER_MODEL != "tiny":
                try:
                    self._fast_model = WhisperModel(
                        "tiny", device=device, compute_type=compute_type,
                        cpu_threads=3, local_files_only=True)
                    print("[ASR] 简短动作指令快速识别已就绪")
                except Exception as e:
                    print(f"[ASR] 快速识别不可用，保留主模型: {e}")
        except ImportError:
            print("[ASR] faster-whisper 未安装, 退回 mock")
            self.mode = "mock"
        except Exception as e:
            print(f"[ASR] whisper 加载失败 ({e}), 退回 mock")
            self.mode = "mock"
            return

        self._resolve_input_device()

    def _resolve_input_device(self):
        """选麦克风: 配置优先(序号或名字片段), 否则自动找 USB 麦克风"""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            if config.ASR_DEVICE:
                if str(config.ASR_DEVICE).isdigit():
                    self._input_device = int(config.ASR_DEVICE)
                else:
                    for idx, dev in enumerate(devices):
                        if (dev["max_input_channels"] > 0
                                and str(config.ASR_DEVICE) in dev["name"]):
                            self._input_device = idx
                            break
            if self._input_device is None:
                for idx, dev in enumerate(devices):
                    if dev["max_input_channels"] > 0 and any(
                            k in dev["name"] for k in
                            ("USB", "UAC", "Mic", "mic", "Microphone")):
                        self._input_device = idx
                        break
            info = (sd.query_devices(self._input_device)
                    if self._input_device is not None else None)
            print(f"[ASR] 麦克风: {info['name'] if info else '系统默认'}")
        except Exception as e:
            self._input_device = None
            print(f"[ASR] 麦克风探测失败 ({e}), 用系统默认")

    # ========================================================================
    def apply_config(self):
        """面板改了麦克风配置后重新探测设备 (VAD 参数每次录音时现读)"""
        self._input_device = None
        if self.mode == "whisper":
            self._resolve_input_device()

    # ========================================================================
    def listen(self, timeout: float = 5.0, auto: bool = False,
               exclusive: bool = False) -> Optional[str]:
        """录音识别一段语音。超时或没听清返回 None。

        auto=True 时忽略终端交互, 直接走自动 VAD 收音 —— 面板上点按钮触发的
        识别走这条路径, 否则人在 Web 端点按钮、却还要跑去小车终端按 Enter。
        exclusive=True 表示面板要独占麦克风: 打断后台主循环正在收的那一路,
        且主循环这一次收音直接让路, 不用等它 15s 超时。
        """
        if exclusive:
            self._abort.set()
        # 同一时刻只能有一路再抢麦克风 (面板测试 vs 语音主循环)
        with self._lock:
            if not exclusive and self._abort.is_set():
                return None
            self._abort.clear()
            if self.mode == "mock":
                return self._listen_mock(timeout)
            elif self.mode == "whisper":
                return self._listen_whisper(timeout, force_auto=auto)
            return None

    def abort_listen(self):
        """打断当前这次收音, 让出麦克风 (面板点按钮时先调它, 不用等满超时)"""
        self._abort.set()

    def release(self):
        """面板用完麦克风, 恢复后台语音主循环收音"""
        self.paused = False
        self._abort.clear()

    def _listen_mock(self, timeout: float) -> Optional[str]:
        """Mock 模式: 直接从命令行输入"""
        try:
            text = input(f"[ASR Mock] ({timeout}s) 你说: ").strip()
            return text if text else None
        except (EOFError, KeyboardInterrupt):
            return None

    def _listen_whisper(self, timeout: float, force_auto: bool = False) -> Optional[str]:
        """录音 + whisper 识别"""
        try:
            import sounddevice as sd
            import numpy as np

            device = self._input_device
            interactive = sys.stdin.isatty() and not force_auto

            # 有终端时手动控制录音; 后台运行(/dev/null)时自动录音
            if interactive:
                print("[ASR] 按 Enter 开始录音...")
                try:
                    input()
                except (EOFError, KeyboardInterrupt):
                    return None

            # 注意: 树莓派板载 USB 麦克风通常只支持 48000 Hz!
            # 如果 48kHz 不行就回退 16kHz
            sample_rate = 48000
            try:
                sd.check_input_settings(device=device, samplerate=sample_rate,
                                        channels=1)
            except Exception:
                sample_rate = 16000
            chunk = int(sample_rate * 0.1)   # 100ms 一块
            recorded = []

            if not interactive:
                # 从第一块音频开始检测，保留 0.8 秒前置音频，避免吞掉开头。
                gate = _SpeechGate(config.VAD_THRESHOLD_MAX,
                                   config.VAD_SPEECH_MS, config.VAD_SILENCE_MS)
                preroll = []
                threshold = gate.threshold
                started = False
                peak = 0.0
                start = time.time()
                print("[ASR] 自动聆听中...")
                # 用回调 + 队列取数据: stream.read() 在设备不给数据时会永久阻塞,
                # 导致整个识别卡死, 这里保证最多等 0.5s 就能检查超时。
                chunks: "queue.Queue" = queue.Queue()

                def _cb(indata, frames, time_info, status):
                    chunks.put(indata.copy())

                with sd.InputStream(device=device, samplerate=sample_rate,
                                    channels=1, dtype='int16', blocksize=chunk,
                                    callback=_cb):
                    while (time.time() - start) < timeout and not self._abort.is_set():
                        try:
                            data = chunks.get(timeout=0.5)
                        except queue.Empty:
                            continue
                        rms = float(np.sqrt(np.mean(
                            (data.astype(np.float32) / 32768.0) ** 2)))
                        peak = max(peak, rms)
                        state = gate.feed(rms)
                        threshold = gate.threshold
                        if not started:
                            preroll.append(data.copy())
                            if len(preroll) > 8:
                                preroll.pop(0)
                            if state == "start":
                                started = True
                                recorded.extend(preroll)
                                preroll = []
                            continue
                        recorded.append(data.copy())
                        if state == "done":
                            break
                if self._abort.is_set():
                    return None
                if not started:
                    print(f"[ASR] 未检测到人声 (峰值 {peak:.4f} / 阈值 {threshold:.4f})")
                    self.last_debug = {"ms": 0, "peak": round(peak, 4),
                                       "threshold": round(threshold, 4)}
                    return None
                print(f"[ASR] 拾音 {len(recorded) * 100} ms (峰值 {peak:.4f})")
                self.last_debug = {"ms": len(recorded) * 100, "peak": round(peak, 4),
                                   "threshold": round(threshold, 4)}
            else:
                def callback(indata, frames, time_info, status):
                    recorded.append(indata.copy())

                print("[ASR] 录音中 (按 Enter 停止, 或 5s 自动停止)...")
                start = time.time()
                stop = threading.Event()

                def wait_enter():
                    try:
                        input()
                    except (EOFError, KeyboardInterrupt):
                        pass
                    stop.set()

                t = threading.Thread(target=wait_enter, daemon=True)
                t.start()

                with sd.InputStream(device=device, samplerate=sample_rate,
                                    channels=1, dtype='int16', blocksize=chunk,
                                    callback=callback):
                    while (not stop.is_set() and not self._abort.is_set()
                           and (time.time() - start) < timeout):
                        time.sleep(0.05)

                if not recorded:
                    return None

            # InputStream 回调/读取的数据是 (frames, 1), 拉平成 1D 给 whisper
            audio = (np.concatenate(recorded, axis=0)
                     .astype(np.float32).reshape(-1) / 32768.0)
            # 麦克风音量偏低时 whisper 识别率很差, 先把峰值拉到 0.9
            peak = float(np.abs(audio).max()) if len(audio) else 0.0
            if peak > 0.001:
                audio = audio * (0.9 / peak)
            print("[ASR] 识别中...")

            # whisper 只吃 16k 单声道; USB 麦克风是 48k, 直接把数组喂进去会被当成
            # 16k 播放 (语速慢 3 倍) 从而识别不出内容。落成 wav 让 faster-whisper
            # 自己按文件头重采样到 16k。
            wav_path = os.path.join(tempfile.gettempdir(), "petcar_asr.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(np.clip(audio * 32768, -32768, 32767)
                               .astype(np.int16).tobytes())

            decode_started = time.monotonic()
            segs = self._transcribe_audio(wav_path, len(audio) / sample_rate)
            self.last_debug["decode_ms"] = round((time.monotonic() - decode_started) * 1000)
            print(f"[ASR] 识别耗时 {self.last_debug['decode_ms']} ms "
                  f"(通道: {self.last_debug.get('decoder', 'main')})")
            text = "".join(seg.text for seg in segs).strip()
            self.last_debug.update({
                "text": text,
                "logprob": round(sum(s.avg_logprob for s in segs) / len(segs), 2)
                if segs else None,
            })
            # 噪音上 whisper 容易瞎编 (低置信度/整句重复), 直接丢掉
            if segs:
                avg_logprob = sum(s.avg_logprob for s in segs) / len(segs)
                if avg_logprob < -1.0:
                    print(f"[ASR] 置信度低 ({avg_logprob:.2f}), 忽略: {text[:20]}")
                    return None
            if len(text) >= 8 and text[:len(text) // 2] == text[len(text) // 2:]:
                text = text[:len(text) // 2]
            # tiny 模型常把噪声识别成纯数字串 (12345), 去掉
            text = " ".join(tok for tok in text.split() if not tok.isdigit()).strip()
            return text if text else None

        except ImportError:
            print("[ASR] sounddevice 未安装, 退回 mock")
            return self._listen_mock(timeout)
        except Exception as e:
            print(f"[ASR] 录音异常: {e}")
            return None

    @staticmethod
    def _clear_fast_command(segments):
        if not segments or any(s.avg_logprob < -0.7 or
                               getattr(s, "no_speech_prob", 1.0) > 0.35
                               for s in segments):
            return False
        text = "".join(s.text for s in segments).strip()
        text = text.translate(str.maketrans({"搖":"摇", "頭":"头", "點":"点",
                                            "轉":"转", "請":"请", "後":"后"}))
        pattern = (
            r"(?:你好)?(?:小坦)?(?:请你|请|帮我|麻烦你)?"
            r"(?:摇摇头|摇头|摇一摇头|点点头|点头|点一点头|歪歪头|歪头|"
            r"跳舞|跳个舞|抬头|低头|向上看|向下看|向左看|向右看|"
            r"往前走|向前走|前进|后退|往后走|左转|右转|转个圈|停止|停下|拍照)"
            r"(?:一下|吧|好吗|可以吗)?[。！？!?，,\s]*"
        )
        return re.fullmatch(pattern, text) is not None

    def _transcribe_audio(self, path, seconds):
        options = dict(language=config.WHISPER_LANG, beam_size=1, best_of=1,
                       vad_filter=True, condition_on_previous_text=False,
                       without_timestamps=True,
                       vad_parameters={"threshold":0.35,"min_silence_duration_ms":400,
                                       "speech_pad_ms":300})
        if self._fast_model is not None and seconds <= 4.5:
            try:
                fast, fast_info = self._fast_model.transcribe(
                    path, initial_prompt=f"{config.PET_NAME}，请摇摇头。请点点头。向左看。向右看。前进。后退。",
                    **options)
                fast = list(fast)
                clear_command = self._clear_fast_command(fast)
                if clear_command or self._clear_fast_utterance(fast):
                    self.last_debug["decoder"] = "fast-command" if clear_command else "fast-short"
                    return fast
                if not fast and getattr(fast_info, "duration_after_vad", None) == 0:
                    self.last_debug["decoder"] = "silence"
                    return []
            except Exception as e:
                print(f"[ASR] 快速识别失败，改用主模型: {e}")
        segments, _ = self._model.transcribe(
            path, initial_prompt=f"这是中文对话，机器人的名字叫{config.PET_NAME}。",
            **options)
        self.last_debug["decoder"] = "main"
        return list(segments)

    @staticmethod
    def _clear_fast_utterance(segments):
        # Very clear short conversation can also avoid a second decoding pass.
        if not segments or any(s.avg_logprob < -0.45 or
                               getattr(s, "no_speech_prob", 1.0) > 0.2
                               for s in segments):
            return False
        text = "".join(s.text for s in segments).strip()
        if not 2 <= len(text) <= 24 or not re.search(r"[\u4e00-\u9fff]", text):
            return False
        if re.search(r"(.{2,6})\1", text) or re.search(r"不要|别|不能|不许", text):
            return False
        return True

    # ========================================================================
    def listen_loop(self, callback):
        """阻塞式: 持续 listen → 回调"""
        self._running = True
        while self._running:
            try:
                text = self.listen(timeout=10)
                if text:
                    callback(text)
            except KeyboardInterrupt:
                break
        self._running = False

    def stop(self):
        self._running = False
