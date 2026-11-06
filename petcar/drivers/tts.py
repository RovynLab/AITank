# -*- coding: utf-8 -*-
"""
drivers/tts.py — 语音合成 (TTS)
=================================
三种实现: espeak (系统), pyttsx3, mock (只打印)
"""

from __future__ import annotations

import sys
import os
import subprocess
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar import config


class TTSDriver:
    """语音合成"""

    def __init__(self, mode: str = config.TTS_MODE):
        self.mode = mode
        self._engine = None

        if mode == "espeak":
            self._test_espeak()
        elif mode == "pyttsx3":
            self._init_pyttsx3()
        elif mode == "mock":
            print("[TTS] Mock 模式 (只打印文本)")
        else:
            print(f"[TTS] 未知模式 {mode}, 退回 mock")
            self.mode = "mock"

    def _test_espeak(self):
        try:
            result = subprocess.run(["espeak", "--version"],
                                    capture_output=True, text=True, timeout=5)
            print(f"[TTS] espeak 可用: {result.stdout.strip()[:60]}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print("[TTS] espeak 未安装, 退回 mock (sudo apt install espeak)")
            self.mode = "mock"

    def _init_pyttsx3(self):
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            # 尝试设中文语音
            try:
                voices = self._engine.getProperty('voices')
                for v in voices:
                    if 'zh' in (v.language or '').lower():
                        self._engine.setProperty('voice', v.id)
                        break
            except Exception:
                pass
            self._engine.setProperty('rate', 150)
            print("[TTS] pyttsx3 初始化成功")
        except ImportError:
            print("[TTS] pyttsx3 未安装, 退回 espeak")
            self.mode = "espeak"
            self._test_espeak()
        except Exception as e:
            print(f"[TTS] pyttsx3 初始化失败 ({e}), 退回 mock")
            self.mode = "mock"

    # ========================================================================
    def speak(self, text: str, emotion: str = "neutral"):
        """同步播放语音"""
        if not text:
            return
        # 截断避免说太长
        text = text[:100]

        if self.mode == "espeak":
            self._speak_espeak(text)
        elif self.mode == "pyttsx3":
            self._speak_pyttsx3(text)
        elif self.mode == "mock":
            print(f"[TTS Mock] ({emotion}) {text}")

    def speak_async(self, text: str, emotion: str = "neutral"):
        """异步播放 (后台线程)"""
        threading.Thread(target=self.speak, args=(text, emotion),
                         daemon=True).start()

    # ========================================================================
    def _speak_espeak(self, text: str):
        # -v zh: 中文语音 (-v zh+m 男, -v zh+f 女), -s 速度
        try:
            subprocess.run(["espeak", "-v", "zh+f", "-s", "150", text],
                           timeout=30, capture_output=True)
        except Exception as e:
            print(f"[TTS] espeak 播放失败: {e}")

    def _speak_pyttsx3(self, text: str):
        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception as e:
            print(f"[TTS] pyttsx3 播放失败: {e}")


if __name__ == "__main__":
    print("测试 TTS...")
    tts = TTSDriver(mode="mock")
    tts.speak("你好呀，我是小宝！")
    tts.speak("今天天气怎么样？", emotion="happy")
