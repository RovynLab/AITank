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
        print(f"直接说话即可 (ASR={self.asr.mode}), 输入 'quit' 退出")
        print("======================================\n")

        _paused_since = 0.0   # 记录 asr.paused 什么时候开始的, 超时自动恢复
        while self._running:
            # TTS 还在播 / 面板正在做对话测试时不要收音
            while self._running:
                if self.tts.is_speaking():
                    _paused_since = 0.0
                    time.sleep(0.2)
                    continue
                if self.asr.paused:
                    if _paused_since == 0.0:
                        _paused_since = time.time()
                    elapsed = time.time() - _paused_since
                    # 面板用完麦克风后应恢复 paused=False, 但如果面板线程异常
                    # 退出没走到 finally, paused 会一直卡住 → 等 20 秒后自动恢复
                    if elapsed > 20.0:
                        print("[VoiceIO] asr.paused 超时, 自动恢复收音")
                        self.asr.release()
                        _paused_since = 0.0
                    else:
                        time.sleep(0.2)
                        continue
                _paused_since = 0.0
                break

            # 1. 等待表情 (在 VAD 静音期间显示, 让用户知道小车在听)
            if self.emotion:
                self.emotion.set_emotion("neutral")
                self.emotion.start_think(duration=12.0)
                self.emotion.text_bubble("我在听...", duration=6.0)

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

            # 3. 调 LLM — 期间一直显示 "思考中..."
            response_started = time.monotonic()
            if self.emotion:
                self.emotion.start_think(duration=60.0)   # 足够覆盖 LLM 最长延迟
                self.emotion.text_bubble("思考中...", duration=60.0)

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

            # 4. LLM 返回后, 清掉 "思考中", 切换到对应情绪
            if self.emotion:
                self.emotion.clear_text()
                self.emotion.set_emotion(resp.emotion, duration=2.0)

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
                # 也避免喇叭回声抬高 VAD baseline
                time.sleep(1.0)
            elif reply_text:
                self._last_spoken = reply_text
                time.sleep(0.5)

        self._running = False

    def _speak_before_action(self, text, emotion):
        if self.emotion:
            self.emotion.set_emotion(emotion)
            self.emotion.start_speak(duration=max(2, len(text) * 0.15))
        started = time.monotonic()
        self.tts.speak(text, emotion)
        print(f"[Latency] 动作前播报耗时 {time.monotonic() - started:.2f}s")
