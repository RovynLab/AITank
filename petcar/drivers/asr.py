# -*- coding: utf-8 -*-
"""
drivers/asr.py — 语音识别 (ASR)
=================================
录音在本进程 (sounddevice 必须跟物理设备同进程),
识别通过 localhost HTTP 调用独立的 whisper_service.

启动不再加载 faster-whisper 模型 (60s), 改成 health check (<10ms).
模型由 systemd 服务 aitank-whisper 开机预加载.
"""

from __future__ import annotations

import sys
import os
import time
import wave
import queue
import tempfile
import threading
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar import config


class ASRDriver:
    """语音识别 — 录音本地做, whisper 识别走 HTTP"""

    def __init__(self):
        self.mode = "service"          # 不再是 whisper, 而是 service
        self._input_device = None
        self.last_debug = {}
        self.paused = False
        self._lock = threading.Lock()
        self._abort = threading.Event()   # 打断正在进行的收音 (面板要独占麦克风)
        self._audio_queue: "queue.Queue[bytes]" = queue.Queue()
        self._running = False
        self._service_ok = False

        self._check_service()
        self._resolve_input_device()

    # ========================================================================
    def _check_service(self):
        """跟 whisper_service 打个招呼, 确认模型已加载"""
        import requests
        url = config.WHISPER_SERVICE_URL.rstrip("/") + "/health"
        try:
            r = requests.get(url, timeout=3)
            data = r.json()
            if data.get("ok") and data.get("loaded"):
                self._service_ok = True
                print(f"[ASR] whisper_service 就绪 "
                      f"(model={data.get('model')}, uptime={data.get('uptime')}s)")
            else:
                err = data.get("error", "模型未加载")
                print(f"[ASR] ⚠️ whisper_service 返回未就绪: {err}")
        except Exception as e:
            print(f"[ASR] ⚠️ whisper_service 不可达 ({url}): {e}")
            print("[ASR] 请检查: sudo systemctl status aitank-whisper")

    def _resolve_input_device(self):
        """选麦克风: 配置优先(序号或名字片段), 否则自动找 USB 麦克风"""
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            print(f"[ASR] 可用音频设备 ({len(devices)} 个):")
            for idx, dev in enumerate(devices):
                in_ch = dev.get("max_input_channels", 0)
                out_ch = dev.get("max_output_channels", 0)
                flag = ""
                if dev.get("default_input"):
                    flag += " [默认入]"
                if dev.get("default_output"):
                    flag += " [默认出]"
                print(f"  [{idx}] {dev['name']} (in={in_ch}, out={out_ch}){flag}")

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
            # 最后兜底: 用系统默认输入设备
            if self._input_device is None:
                for idx, dev in enumerate(devices):
                    if dev.get("default_input"):
                        self._input_device = idx
                        break
            info = (sd.query_devices(self._input_device)
                    if self._input_device is not None else None)
            print(f"[ASR] 选中麦克风: [{self._input_device}] "
                  f"{info['name'] if info else '系统默认'}")
        except Exception as e:
            self._input_device = None
            print(f"[ASR] 麦克风探测失败 ({e}), 用系统默认")

    # ========================================================================
    def apply_config(self):
        """面板改了麦克风配置后重新探测设备 (VAD 参数每次录音时现读)"""
        self._input_device = None
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
            return self._listen_whisper(timeout, force_auto=auto)

    def abort_listen(self):
        """打断当前这次收音, 让出麦克风 (面板点按钮时先调它, 不用等满超时)"""
        self._abort.set()

    def release(self):
        """面板用完麦克风, 恢复后台语音主循环收音"""
        self.paused = False
        self._abort.clear()

    def _listen_whisper(self, timeout: float, force_auto: bool = False) -> Optional[str]:
        """录音 + whisper 识别"""
        try:
            import sounddevice as sd
            import numpy as np

            # PortAudio ALSA backend 对 USB UAC 设备的枚举不稳定,
            # 有时会把 max_input_channels 误报为 0, 导致默认入变成 -1.
            # 每次录音前重新校验设备有效性, 坏了就重新探测.
            device = self._input_device
            try:
                if device is not None:
                    dev_info = sd.query_devices(device)
                    if dev_info.get("max_input_channels", 0) == 0:
                        print(f"[ASR] 设备 [{device}] max_input_channels=0, 重新探测")
                        self._resolve_input_device()
                        device = self._input_device
                # 兜底: 如果默认入是 -1 (无有效输入设备), 强制重新探测
                default_in = sd.default.device[0]
                if default_in < 0:
                    print(f"[ASR] 默认输入设备无效 (default_in={default_in}), 重新探测")
                    self._resolve_input_device()
                    device = self._input_device
            except Exception:
                self._resolve_input_device()
                device = self._input_device

            # 最后兜底: 设备还是 None 就用 None (让 sounddevice 自己选)
            if device is None:
                print("[ASR] 没有明确的麦克风设备, 尝试用系统默认")

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
                # 自动录音: 前 1s 采环境噪音定阈值, 听到人声才开始录,
                # 静音 1.2s 结束 (只留 0.3s 前置缓冲, 避免把整段静音丢给 whisper)
                speech_ms = silence_ms = 0
                baseline = []
                preroll = []
                threshold = 0.012
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
                        if len(baseline) < 10:   # 10 次 = 1s, 更稳定的环境噪音基线
                            baseline.append(rms)
                            threshold = min(config.VAD_THRESHOLD_MAX,
                                            max(0.005,
                                                sum(baseline) / len(baseline) * 1.8))
                            # baseline 还没采够时顺便把 preroll 也填满
                            preroll.append(data.copy())
                            if len(preroll) > 3:
                                preroll.pop(0)
                            continue
                        if not started:
                            preroll.append(data.copy())
                            if len(preroll) > 3:
                                preroll.pop(0)
                            speech_ms = speech_ms + 100 if rms > threshold else 0
                            if speech_ms >= config.VAD_SPEECH_MS:
                                started = True
                                recorded.extend(preroll)
                                preroll = []
                                speech_ms = config.VAD_SPEECH_MS
                            continue
                        recorded.append(data.copy())
                        if rms > threshold:
                            silence_ms = 0
                        else:
                            silence_ms += 100
                        if silence_ms >= config.VAD_SILENCE_MS:
                            break
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

            # InputStream 回调/读取的数据是 (frames, 1), 拉平成 1D
            audio = (np.concatenate(recorded, axis=0)
                     .astype(np.float32).reshape(-1) / 32768.0)
            # 麦克风音量偏低时 whisper 识别率很差, 先把峰值拉到 0.9
            peak = float(np.abs(audio).max()) if len(audio) else 0.0
            if peak > 0.001:
                audio = audio * (0.9 / peak)
            print("[ASR] 识别中...")

            # whisper 只吃 16k 单声道; USB 麦克风是 48k, 直接把数组喂进去会被当成
            # 16k 播放 (语速慢 3 倍) 从而识别不出内容。落成 wav 让 service 端的
            # faster-whisper 自己按文件头重采样到 16k。
            wav_path = os.path.join(tempfile.gettempdir(), "petcar_asr.wav")
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(np.clip(audio * 32768, -32768, 32767)
                               .astype(np.int16).tobytes())

            # ── HTTP POST 到 whisper_service ──────────────────
            import requests
            url = config.WHISPER_SERVICE_URL.rstrip("/") + "/transcribe"
            try:
                with open(wav_path, "rb") as f:
                    r = requests.post(
                        url,
                        files={"audio": ("petcar_asr.wav", f, "audio/wav")},
                        data={"language": config.WHISPER_LANG},
                        timeout=30,    # 单次识别不会太长
                    )
                if r.status_code == 200:
                    data = r.json()
                    text = data.get("text", "").strip()
                    self.last_debug.update({
                        "text": text,
                        "logprob": data.get("avg_logprob"),
                        "elapsed": data.get("elapsed"),
                        "language": data.get("language"),
                    })
                    return text if text else None
                elif r.status_code == 503:
                    print(f"[ASR] whisper_service 返回 503: {r.json().get('detail')}")
                    self._service_ok = False
                    return None
                else:
                    print(f"[ASR] whisper_service HTTP {r.status_code}: {r.text[:200]}")
                    return None
            except requests.ConnectionError:
                print(f"[ASR] whisper_service 连接失败 ({url}), "
                      f"请检查: sudo systemctl status aitank-whisper")
                self._service_ok = False
                return None
            except requests.Timeout:
                print(f"[ASR] whisper_service 超时 (30s)")
                return None
            except Exception as e:
                print(f"[ASR] 识别请求异常: {e}")
                return None
            finally:
                try:
                    os.remove(wav_path)
                except OSError:
                    pass

        except ImportError:
            print("[ASR] sounddevice 未安装, 无法录音")
            return None
        except Exception as e:
            print(f"[ASR] 录音异常: {e}")
            return None

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
