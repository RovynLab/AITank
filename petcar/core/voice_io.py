# -*- coding: utf-8 -*-
"""
core/voice_io.py — 语音交互主循环
=================================
把 ASR → ChatAgent → TTS + EmotionEngine 串起来。
"""

from __future__ import annotations

import sys
import os
import time
import threading
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar.drivers.asr import ASRDriver
from petcar.drivers.tts import TTSDriver
from petcar.core.chat_agent import ChatAgent
from petcar.core.emotion_engine import EmotionEngine


class VoiceIO:
    """语音交互主循环"""

    def __init__(self,
                 asr: Optional[ASRDriver] = None,
                 tts: Optional[TTSDriver] = None,
                 chat: Optional[ChatAgent] = None,
                 emotion: Optional[EmotionEngine] = None):
        from petcar.drivers.asr import ASRDriver
        from petcar.drivers.tts import TTSDriver

        self.asr = asr or ASRDriver()
        self.tts = tts or TTSDriver()
        self.chat = chat
        self.emotion = emotion

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """后台线程启动"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[VoiceIO] 已启动")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self):
        """阻塞式主循环"""
        print("\n========== PetCar 语音交互 ==========")
        print("输入文字回车 (MockASR) 或说话, 输入 'quit' 退出")
        print("======================================\n")

        while self._running:
            try:
                # 1. 思考表情
                if self.emotion:
                    self.emotion.start_think(duration=3.0)

                # 2. 监听用户
                text = self.asr.listen(timeout=15.0)

                if text is None:
                    continue
                text = text.strip()
                if not text:
                    continue
                if text.lower() in ("quit", "exit", "退出"):
                    print("[VoiceIO] 退出")
                    break

                print(f"\n[你] {text}")

                # 3. 调 LLM
                if self.chat:
                    resp = self.chat.chat(text)
                else:
                    resp = type("Resp", (), {
                        "reply": f"(ChatAgent 未配置) 你说的是「{text}」呀",
                        "emotion": "neutral",
                        "tools_called": [],
                    })()

                # 4. 同步表情
                if self.emotion:
                    self.emotion.set_emotion(resp.emotion)

                # 5. 播放语音 + 嘴巴动画
                reply_text = resp.reply or ""
                if reply_text:
                    if self.emotion:
                        self.emotion.start_speak(duration=max(2, len(reply_text) * 0.15))
                    print(f"[{resp.emotion}] {reply_text}")
                    self.tts.speak(reply_text, emotion=resp.emotion)

            except KeyboardInterrupt:
                print("\n[VoiceIO] Ctrl+C, 退出")
                break
            except Exception as e:
                print(f"[VoiceIO] 异常: {e}")

        self._running = False
