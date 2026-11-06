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
import queue
import threading
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar import config


class ASRDriver:
    """语音识别"""

    def __init__(self, mode: str = config.ASR_MODE):
        self.mode = mode
        self._model = None
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
                                       compute_type=compute_type)
            print("[ASR] whisper 加载成功")
        except ImportError:
            print("[ASR] faster-whisper 未安装, 退回 mock")
            self.mode = "mock"
        except Exception as e:
            print(f"[ASR] whisper 加载失败 ({e}), 退回 mock")
            self.mode = "mock"

    # ========================================================================
    def listen(self, timeout: float = 5.0) -> Optional[str]:
        """录音识别一段语音。超时或没听清返回 None。"""
        if self.mode == "mock":
            return self._listen_mock(timeout)
        elif self.mode == "whisper":
            return self._listen_whisper(timeout)
        return None

    def _listen_mock(self, timeout: float) -> Optional[str]:
        """Mock 模式: 直接从命令行输入"""
        try:
            text = input(f"[ASR Mock] ({timeout}s) 你说: ").strip()
            return text if text else None
        except (EOFError, KeyboardInterrupt):
            return None

    def _listen_whisper(self, timeout: float) -> Optional[str]:
        """录音 + whisper 识别"""
        try:
            import sounddevice as sd
            import numpy as np

            # 简单录音: 按回车键开始, 再按一次停止 (或 timeout 自动停)
            print("[ASR] 按 Enter 开始录音...")
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                return None

            # 注意: 树莓派板载 USB 麦克风通常只支持 48000 Hz!
            # 如果 48kHz 不行就回退 16kHz
            import sounddevice as _sd
            sample_rate = 48000
            try:
                # 快速试 48k 能不能开
                _sd.check_input_settings(samplerate=sample_rate, channels=1)
            except Exception:
                sample_rate = 16000
            chunk = int(sample_rate * 0.1)   # 100ms 一块
            recorded = []

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

            with sd.InputStream(samplerate=sample_rate, channels=1,
                                dtype='int16', blocksize=chunk,
                                callback=callback):
                while not stop.is_set() and (time.time() - start) < timeout:
                    time.sleep(0.05)

            if not recorded:
                return None

            audio = np.concatenate(recorded, axis=0).astype(np.float32) / 32768.0
            print("[ASR] 识别中...")

            segments, info = self._model.transcribe(
                audio, language=config.WHISPER_LANG, beam_size=1, vad_filter=True,
            )
            text = "".join(seg.text for seg in segments).strip()
            return text if text else None

        except ImportError:
            print("[ASR] sounddevice 未安装, 退回 mock")
            return self._listen_mock(timeout)
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
