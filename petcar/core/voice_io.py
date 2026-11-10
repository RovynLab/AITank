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
        self._last_spoken = ""

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
        if self.asr.mode == "mock":
            print("输入文字回车 (MockASR), 输入 'quit' 退出")
        else:
            print(f"直接说话即可 (ASR={self.asr.mode}), 输入 'quit' 退出")
        print("======================================\n")

        while self._running:
            try:
                # TTS 还在播 / 面板正在做对话测试时不要收音
                while self._running and (self.tts.is_speaking()
                                         or self.asr.paused):
                    time.sleep(0.2)

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

                # 回声保护: 识别结果跟自己刚说的话高度重合就丢掉
                if self._last_spoken and (text in self._last_spoken
                                          or text[:6] in self._last_spoken):
                    print("[VoiceIO] 忽略回声")
                    continue

                # 3. 调 LLM
                response_started = time.monotonic()
                if self.chat:
                    resp = self.chat.chat(text, before_action=self._speak_before_action)
                else:
                    resp = type("Resp", (), {
                        "reply": f"(ChatAgent 未配置) 你说的是「{text}」呀",
                        "emotion": "neutral",
                        "tools_called": [],
                    })()
                print(f"[Latency] 对话/指令处理耗时 "
                      f"{time.monotonic() - response_started:.2f}s")

                # 4. 同步表情
                if self.emotion:
                    self.emotion.set_emotion(resp.emotion)

                # 5. 播放语音 + 嘴巴动画
                reply_text = resp.reply or ""
                if reply_text and not getattr(resp, "reply_spoken", False):
                    if self.emotion:
                        self.emotion.start_speak(duration=max(2, len(reply_text) * 0.15))
                    print(f"[{resp.emotion}] {reply_text}")
                    speech_started = time.monotonic()
                    self.tts.speak(reply_text, emotion=resp.emotion)
                    print(f"[Latency] 回复播放耗时 {time.monotonic() - speech_started:.2f}s")
                    self._last_spoken = reply_text
                    # 等扬声器余音消散, 免得下一轮把自己的声音当成用户说话
                    time.sleep(0.5)
                elif reply_text:
                    self._last_spoken = reply_text
                    time.sleep(0.5)

            except KeyboardInterrupt:
                print("\n[VoiceIO] Ctrl+C, 退出")
                break
            except Exception as e:
                print(f"[VoiceIO] 异常: {e}")

        self._running = False

    def _speak_before_action(self, text, emotion):
        if self.emotion:
            self.emotion.set_emotion(emotion)
            self.emotion.start_speak(duration=max(2, len(text) * 0.15))
        started = time.monotonic()
        self.tts.speak(text, emotion)
        print(f"[Latency] 动作前播报耗时 {time.monotonic() - started:.2f}s")
