# -*- coding: utf-8 -*-
"""
core/emotion_engine.py — 表情渲染引擎
======================================
提供 set_emotion() / text_bubble() 接口，后台线程驱动帧动画
(眨眼、说话嘴动、思考摇头、开心跳动)。
"""

from __future__ import annotations

import sys
import os
import time
import random
import threading
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar.drivers.oled import (
    create_oled_driver, ALL_EMOTIONS, EXPRESSIONS,
)


class EmotionEngine:
    """表情引擎 + 后台动画线程"""

    # 动画帧状态
    ANIM_NONE = "none"
    ANIM_BLINK = "blink"          # 眨眼
    ANIM_SPEAK = "speak"          # 说话 (嘴巴动)
    ANIM_THINK = "think"          # 思考 (眼睛左右看 + 问号闪烁)
    ANIM_HAPPY_BOUNCE = "happy_bounce"  # 开心跳动

    def __init__(self, oled_driver=None):
        self.oled = oled_driver or create_oled_driver()
        self._lock = threading.Lock()

        # 当前状态
        self._emotion = "neutral"
        self._emotion_expire_at = 0.0   # 表情过期时间 (0=持久)
        self._anim = self.ANIM_NONE
        self._anim_until = 0.0

        # 空闲定时行为
        self._last_blink = time.time()
        self._blink_next = random.uniform(4, 8)

        # 文字气泡
        self._text_bubble = None
        self._text_bubble_until = 0.0

        # 动画帧步进
        self._anim_frame = 0
        self._frame_start = time.time()

        # 渲染去重: 画面没变化时不重复推 I2C (否则 8FPS 全帧重绘会打满总线,
        # 电机指令的每个 smbus 写都要排队等一帧, 表现为 4 个轮子间隔 ~1s 依次启动)
        self._last_render_key = None

        # 后台线程
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ========================================================================
    # 控制接口
    # ========================================================================
    def start(self):
        """启动后台渲染线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print("[EmotionEngine] 已启动")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def set_emotion(self, emotion: str, duration: float = 0):
        """
        设置表情。
        duration=0 → 持续显示直到被覆盖
        duration>0 → duration 秒后自动回到 neutral
        """
        if emotion not in ALL_EMOTIONS:
            emotion = "neutral"
        with self._lock:
            self._emotion = emotion
            self._emotion_expire_at = time.time() + duration if duration > 0 else 0
            self._anim = self.ANIM_NONE
            self._anim_until = 0.0

    def get_emotion(self) -> str:
        with self._lock:
            return self._emotion

    def blink_now(self):
        """立即触发一次眨眼动画"""
        with self._lock:
            self._anim = self.ANIM_BLINK
            self._anim_until = time.time() + 0.25
            self._anim_frame = 0

    def start_speak(self, duration: float = 5.0):
        """说话动画 (嘴巴一张一合)"""
        with self._lock:
            self._anim = self.ANIM_SPEAK
            self._anim_until = time.time() + duration

    def start_think(self, duration: float = 3.0):
        """思考动画 (眼睛左右看 + 问号闪烁)"""
        with self._lock:
            self._anim = self.ANIM_THINK
            self._anim_until = time.time() + duration
            self._anim_frame = 0

    def start_happy_bounce(self, duration: float = 3.0):
        with self._lock:
            self._anim = self.ANIM_HAPPY_BOUNCE
            self._anim_until = time.time() + duration

    def text_bubble(self, text: str, duration: float = 3.0):
        """在表情下方叠加文字"""
        with self._lock:
            self._text_bubble = text[:21]
            self._text_bubble_until = time.time() + duration

    def clear_text(self):
        with self._lock:
            self._text_bubble = None

    # ========================================================================
    # 后台渲染循环
    # ========================================================================
    def _loop(self):
        FPS = 8
        frame_interval = 1.0 / FPS

        while self._running:
            t0 = time.time()

            self._tick()

            # 渲染
            self._render()

            # 帧间隔
            dt = time.time() - t0
            if dt < frame_interval:
                time.sleep(frame_interval - dt)

    def _tick(self):
        """定时任务: 眨眼、表情过期"""
        now = time.time()

        # 表情过期
        if self._emotion_expire_at > 0 and now > self._emotion_expire_at:
            self._emotion = "neutral"
            self._emotion_expire_at = 0
            self._anim = self.ANIM_NONE

        # 动画过期
        if self._anim_until > 0 and now > self._anim_until:
            self._anim = self.ANIM_NONE
            self._anim_until = 0

        # 文字气泡过期
        if self._text_bubble_until > 0 and now > self._text_bubble_until:
            self._text_bubble = None
            self._text_bubble_until = 0

        # 空闲眨眼
        if (self._anim == self.ANIM_NONE
                and (now - self._last_blink) > self._blink_next):
            self.blink_now()
            self._last_blink = now
            self._blink_next = random.uniform(4, 8)

        self._anim_frame += 1

    def _render(self):
        """根据当前状态绘制一帧"""
        with self._lock:
            face = EXPRESSIONS.get(self._emotion, EXPRESSIONS["neutral"]).copy()
            offset_y = 0

            # 根据当前动画调整 face
            anim = self._anim
            if anim == self.ANIM_BLINK:
                # 用闭眼替换, 持续 0.25s 内分 3 帧
                face["left_eye"] = "line_h"
                face["right_eye"] = "line_h"

            elif anim == self.ANIM_SPEAK:
                # 嘴巴在 open / arc_top 之间切换
                if self._anim_frame % 2 == 0:
                    face["mouth"] = "open"
                else:
                    face["mouth"] = "arc_top"

            elif anim == self.ANIM_THINK:
                # 眼睛在 circle / circle 基础上加一个水平偏移的视觉效果
                if self._anim_frame % 4 < 2:
                    face["left_eye"] = "circle"
                    face["right_eye"] = "question"

            elif anim == self.ANIM_HAPPY_BOUNCE:
                # 整体上下跳动
                cycle = self._anim_frame % 8
                if cycle < 2:
                    offset_y = -2
                elif cycle < 4:
                    offset_y = 0
                elif cycle < 6:
                    offset_y = 2
                else:
                    offset_y = 0

        # 渲染去重: 无动画时 anim_frame 不参与 key, 画面没变就不推 I2C
        render_key = (
            self._emotion, anim,
            self._anim_frame if anim != self.ANIM_NONE else 0,
            offset_y, self._text_bubble,
        )
        if render_key == self._last_render_key:
            return
        self._last_render_key = render_key

        # 绘制
        self.oled.show_custom_face(face, offset_y=offset_y)

        # 文字气泡 (在表情下方覆盖)
        if self._text_bubble:
            self.oled.show_text(self._text_bubble)
