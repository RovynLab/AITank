# -*- coding: utf-8 -*-
"""
core/mood_engine.py — 情感状态机
================================
维护 valence (正负) + arousal (唤醒度) 二维情感，
外部触发 → 快速响应 → 自然衰减 → 随机空闲行为。
"""

from __future__ import annotations

import sys
import os
import time
import threading
import random
from dataclasses import dataclass, field
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar import config
from petcar.core.emotion_engine import EmotionEngine

# 情绪标签到 valence/arousal 的映射
EMOTION_VA_MAP = {
    # emotion_name: (valence, arousal)
    "happy":     (0.6, 0.6),
    "laugh":     (0.9, 0.9),
    "love":      (0.7, 0.3),
    "sad":       (-0.7, 0.3),
    "angry":     (-0.8, 0.9),
    "surprised": (0.1, 0.8),
    "scared":    (-0.6, 0.8),
    "sleepy":    (0.0, 0.1),
    "thinking":  (0.1, 0.4),
    "confused":  (-0.1, 0.3),
    "neutral":   (0.0, 0.5),
    "wink":      (0.5, 0.5),
}


@dataclass
class MoodState:
    valence: float = 0.0      # [-1, 1] 负性 ←→ 正性
    arousal: float = 0.5      # [0, 1]  平静 ←→ 激动
    intensity: float = 0.5    # [0, 1]  当前情绪强度

    # 根据 valence + arousal 推出表情
    def to_emotion(self) -> str:
        v, a = self.valence, self.arousal
        # 先做象限分块，再看 intensity
        if self.intensity < 0.15:
            return "sleepy" if a < 0.25 else "neutral"

        if v > 0.3:
            if a > 0.6:  return "laugh"   # 正+高唤醒
            if a > 0.3:  return "happy"   # 正+中
            return "love"                  # 正+低唤醒
        elif v < -0.3:
            if a > 0.6:  return "angry"   # 负+高
            if a > 0.4:  return "scared"
            return "sad"                   # 负+低
        else:
            if a > 0.6:  return "surprised"
            if a > 0.3:  return "thinking"
            if a < 0.2:  return "sleepy"
            return "neutral"


class MoodEngine:
    """情感引擎"""

    def __init__(self, emotion_engine: Optional[EmotionEngine] = None):
        self.emotion = emotion_engine
        self.state = MoodState()
        self._lock = threading.Lock()
        self._last_trigger = time.time()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ========================================================================
    # 外部接口
    # ========================================================================
    def trigger(self, emotion: str, intensity: float = 1.0):
        """
        外部触发: 比如 LLM 返回了 'happy', 或者用户说了句笑话。
        emotion: 从 EMOTION_VA_MAP 里选。
        intensity: 0.3 ~ 1.0, 越大越强烈。
        """
        v, a = EMOTION_VA_MAP.get(emotion, (0.0, 0.5))
        with self._lock:
            # 加权移动平均 (新值权重 intensity, 旧值权重 1-intensity)
            alpha = max(0.2, min(1.0, intensity))
            self.state.valence  = self.state.valence  * (1 - alpha) + v * alpha
            self.state.arousal  = self.state.arousal  * (1 - alpha) + a * alpha
            self.state.intensity = min(1.0, self.state.intensity + alpha * 0.5)
            # 限幅
            self.state.valence   = max(-1.0, min(1.0, self.state.valence))
            self.state.arousal   = max(0.0, min(1.0, self.state.arousal))
            self._last_trigger = time.time()

        # 同步表情
        self._sync_emotion(forced=emotion)

    def set_mood(self, valence: float, arousal: float, intensity: float = 1.0):
        """直接设置情感值 (学生 API)"""
        with self._lock:
            self.state.valence   = max(-1.0, min(1.0, valence))
            self.state.arousal   = max(0.0, min(1.0, arousal))
            self.state.intensity = max(0.0, min(1.0, intensity))
        self._sync_emotion()

    def get_state(self) -> MoodState:
        with self._lock:
            return MoodState(
                valence=self.state.valence,
                arousal=self.state.arousal,
                intensity=self.state.intensity,
            )

    # ========================================================================
    # 后台 tick
    # ========================================================================
    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._tick_loop, daemon=True)
        self._thread.start()
        print("[MoodEngine] 已启动")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _tick_loop(self):
        while self._running:
            time.sleep(1.0)
            self._tick()

    def _tick(self):
        with self._lock:
            old = (self.state.valence, self.state.arousal)

            # 自然衰减 → 向 neutral (0, 0.5) 回归
            self.state.valence   *= config.MOOD_DECAY_V
            self.state.arousal   = 0.5 + (self.state.arousal - 0.5) * config.MOOD_DECAY_A
            self.state.intensity *= config.MOOD_DECAY_I
            # 轻微随机游走 (增加真实感)
            self.state.valence  += random.gauss(0, 0.01)
            self.state.arousal  += random.gauss(0, 0.01)
            self.state.valence   = max(-1.0, min(1.0, self.state.valence))
            self.state.arousal   = max(0.0, min(1.0, self.state.arousal))

            now = time.time()
            idle_sec = now - self._last_trigger

        # 同步表情 (只有明显变化才通知 EmotionEngine)
        if abs(self.state.valence - old[0]) > 0.05 or abs(self.state.arousal - old[1]) > 0.05:
            self._sync_emotion()

        # 空闲行为
        self._idle_behavior(idle_sec)

    def _sync_emotion(self, forced: Optional[str] = None):
        if self.emotion is None:
            return
        with self._lock:
            emotion_name = forced if forced else self.state.to_emotion()
        self.emotion.set_emotion(emotion_name)

    def _idle_behavior(self, idle_sec: float):
        """空闲超过阈值时随机做些小动作"""
        if idle_sec < config.IDLE_SLEEPY_SEC:
            return
        if random.random() < 0.05:   # 5% 概率触发
            behaviors = [
                ("打哈欠", lambda: self._set_temporarily("sleepy", 1.5)),
                ("左顾右盼", lambda: None),
                ("哼歌", lambda: None),
                ("眨眼", lambda: self.emotion.blink_now() if self.emotion else None),
            ]
            name, fn = random.choice(behaviors)
            print(f"[Mood] 空闲行为: {name}")
            try:
                fn()
            except Exception:
                pass

    def _set_temporarily(self, emotion: str, seconds: float):
        self.trigger(emotion, intensity=0.5)
