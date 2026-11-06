# -*- coding: utf-8 -*-
"""
skills/express.py — 宠物动作库
================================
把云台和底盘的短指令组合成一组拟态动作，每个动作 4~16 步。

动作表是纯数据，播放器负责按顺序执行:
  ("ptz_h", 角度, 保持秒)       云台水平轴绝对角度
  ("ptz_v", 角度, 保持秒)       云台垂直轴绝对角度
  ("ptz_hv", 水平, 垂直, 保持)  两轴同时动
  ("chassis", 方向, 速度, 秒)   底盘短脉冲，结束后立即停
  ("wait", 秒)                  停顿

用法:
    player = ExpressionPlayer(mecanum, ptz)
    player.play("nod")     # 后台线程播放，不阻塞
    player.stop()          # 中断并回中

注意:
    横移动作依赖 MecanumDriver._MOTION_TABLE 的 leftSlide/rightSlide。
    若实车发现横移变成原地转，先核对该表，应与 labs/lab06 的横移方向一致。
"""

from __future__ import annotations

import sys
import os
import time
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar.skills.base_skill import BaseSkill


# spin 速度 120 转一圈的秒数，实车需要标定
SPIN_360_S = 2.0


ACTIONS = {
    "nod": {
        "label": "点头",
        "emotion": "happy",
        "steps": [
            ("ptz_v", 82, 0.12), ("wait", 0.06),
            ("ptz_v", 96, 0.15), ("wait", 0.04),
            ("ptz_v", 84, 0.14), ("wait", 0.04),
            ("ptz_v", 90, 0.18),
        ],
    },
    "shake": {
        "label": "摇头",
        "emotion": "confused",
        "steps": [
            ("ptz_h", 78, 0.11), ("wait", 0.05),
            ("ptz_h", 102, 0.16), ("wait", 0.04),
            ("ptz_h", 80, 0.15), ("wait", 0.04),
            ("ptz_h", 100, 0.16), ("wait", 0.04),
            ("ptz_h", 90, 0.18),
        ],
    },
    "tilt": {
        "label": "歪头",
        "emotion": "thinking",
        "steps": [
            ("ptz_hv", 74, 96, 0.18), ("wait", 0.45),
            ("ptz_hv", 90, 90, 0.22),
        ],
    },
    "wag": {
        "label": "摆尾",
        "emotion": "happy",
        "steps": [
            ("chassis", "leftSlide", 100, 0.11), ("ptz_h", 98, 0.05),
            ("chassis", "rightSlide", 100, 0.11), ("ptz_h", 82, 0.05),
            ("chassis", "leftSlide", 100, 0.11), ("ptz_h", 98, 0.05),
            ("chassis", "rightSlide", 100, 0.11), ("ptz_h", 82, 0.05),
            ("chassis", "leftSlide", 100, 0.11), ("ptz_h", 98, 0.05),
            ("chassis", "rightSlide", 100, 0.11), ("ptz_h", 90, 0.05),
        ],
    },
    "twist": {
        "label": "扭腰",
        "emotion": "wink",
        "steps": [
            ("chassis", "turnLeft", 100, 0.13), ("ptz_h", 100, 0.02),
            ("chassis", "rightSlide", 100, 0.13), ("ptz_h", 80, 0.02),
            ("chassis", "turnRight", 100, 0.13), ("ptz_h", 100, 0.02),
            ("chassis", "leftSlide", 100, 0.13), ("ptz_h", 80, 0.02),
            ("chassis", "turnLeft", 100, 0.13), ("ptz_h", 100, 0.02),
            ("chassis", "rightSlide", 100, 0.13), ("ptz_h", 80, 0.02),
            ("chassis", "turnRight", 100, 0.13), ("ptz_h", 100, 0.02),
            ("chassis", "leftSlide", 100, 0.13), ("ptz_h", 90, 0.02),
        ],
    },
    "spin": {
        "label": "转圈",
        "emotion": "laugh",
        "steps": [
            ("ptz_hv", 70, 104, 0.30),
            ("chassis", "spin", 120, SPIN_360_S),
            ("ptz_hv", 90, 90, 0.30),
        ],
    },
    "nuzzle": {
        "label": "蹭蹭",
        "emotion": "love",
        "steps": [
            ("chassis", "forward", 90, 0.12), ("wait", 0.08),
            ("ptz_v", 83, 0.15),
            ("ptz_h", 80, 0.14), ("wait", 0.06),
            ("ptz_h", 100, 0.18), ("wait", 0.06),
            ("ptz_h", 90, 0.16),
            ("chassis", "backward", 90, 0.10), ("wait", 0.08),
        ],
    },
    "hop": {
        "label": "蹦跳",
        "emotion": "laugh",
        "steps": [
            ("chassis", "forward", 95, 0.08), ("ptz_v", 99, 0.08),
            ("chassis", "backward", 95, 0.08), ("ptz_v", 90, 0.08),
            ("chassis", "forward", 95, 0.08), ("ptz_v", 99, 0.08),
            ("chassis", "backward", 95, 0.08), ("ptz_v", 90, 0.08),
        ],
    },
    "droop": {
        "label": "委屈低头",
        "emotion": "sad",
        "steps": [
            ("ptz_hv", 83, 72, 0.50), ("wait", 0.10),
            ("chassis", "backward", 80, 0.15), ("wait", 0.50),
            ("ptz_hv", 90, 90, 0.70),
        ],
    },
    "lean_in": {
        "label": "好奇凑近",
        "emotion": "surprised",
        "steps": [
            ("ptz_v", 102, 0.25), ("wait", 0.10),
            ("chassis", "forward", 100, 0.22), ("wait", 0.50),
            ("chassis", "backward", 100, 0.18), ("wait", 0.10),
            ("ptz_v", 90, 0.30),
        ],
    },
    "look_around": {
        "label": "左顾右盼",
        "emotion": "neutral",
        "steps": [
            ("ptz_hv", 62, 94, 0.25), ("wait", 0.20),
            ("ptz_hv", 118, 94, 0.40), ("wait", 0.20),
            ("ptz_hv", 90, 90, 0.25),
        ],
    },
    "stretch": {
        "label": "伸懒腰",
        "emotion": "sleepy",
        "steps": [
            ("ptz_hv", 80, 118, 0.70), ("wait", 0.50),
            ("chassis", "backward", 80, 0.14), ("wait", 0.10),
            ("ptz_hv", 90, 90, 0.60),
        ],
    },
}


def action_duration(steps) -> float:
    """按动作表估算总时长（秒）"""
    total = 0.0
    for step in steps:
        kind = step[0]
        if kind in ("ptz_h", "ptz_v"):
            total += step[2]
        elif kind in ("ptz_hv", "chassis"):
            total += step[3]
        elif kind == "wait":
            total += step[1]
    return round(total, 2)


def list_actions() -> list:
    """给 Web API / 面板用的动作清单"""
    return [
        {
            "name": name,
            "label": meta["label"],
            "emotion": meta["emotion"],
            "duration": action_duration(meta["steps"]),
        }
        for name, meta in ACTIONS.items()
    ]


class ExpressionPlayer:
    """动作播放器: 串行执行动作表，支持打断和自动回中"""

    def __init__(self, mecanum=None, ptz=None):
        self.mecanum = mecanum
        self.ptz = ptz
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread = None
        self._name = None

    @property
    def current(self):
        with self._lock:
            return self._name

    def is_busy(self) -> bool:
        with self._lock:
            t = self._thread
            return bool(t and t.is_alive())

    def play(self, name: str) -> bool:
        """播放一个动作（后台线程，立即返回）"""
        name = (name or "").strip().lower()
        if name == "stop":
            self.stop()
            return True
        if name not in ACTIONS:
            return False

        # 先让上一个动作停稳，避免两个线程抢底盘
        self._halt(wait=True)

        cancel = threading.Event()
        with self._lock:
            self._cancel = cancel
            self._name = name
            self._thread = threading.Thread(
                target=self._run, args=(name, cancel),
                daemon=True, name=f"express-{name}")
            self._thread.start()
        return True

    def stop(self):
        """中断当前动作并回到中位"""
        self._halt(wait=False)

    # ------------------------------------------------------------------
    def _halt(self, wait: bool):
        with self._lock:
            self._cancel.set()
            thread = self._thread
            self._name = None
        if wait and thread and thread is not threading.current_thread():
            thread.join(timeout=0.6)
        self._safe_stop()

    def _safe_stop(self):
        if self.mecanum is not None:
            try:
                self.mecanum.stop()
            except Exception:
                pass
        if self.ptz is not None:
            try:
                self.ptz.look_center()
            except Exception:
                pass

    def _run(self, name: str, cancel: threading.Event):
        speed0 = getattr(self.mecanum, "normal_speed", 150)
        try:
            for step in ACTIONS[name]["steps"]:
                if cancel.is_set():
                    break
                kind = step[0]

                if kind == "chassis":
                    _, direction, speed, duration = step
                    if self.mecanum is not None:
                        try:
                            self.mecanum.set_speed(int(speed))
                            fn = getattr(self.mecanum, direction, None)
                            if fn:
                                fn()
                        except Exception:
                            pass
                    self._sleep(duration, cancel)
                    if self.mecanum is not None:
                        try:
                            self.mecanum.stop()
                        except Exception:
                            pass

                elif kind == "ptz_h":
                    if self.ptz is not None:
                        try:
                            self.ptz.h_rotate(step[1])
                        except Exception:
                            pass
                    self._sleep(step[2], cancel)

                elif kind == "ptz_v":
                    if self.ptz is not None:
                        try:
                            self.ptz.v_rotate(step[1])
                        except Exception:
                            pass
                    self._sleep(step[2], cancel)

                elif kind == "ptz_hv":
                    if self.ptz is not None:
                        try:
                            self.ptz.h_rotate(step[1])
                            self.ptz.v_rotate(step[2])
                        except Exception:
                            pass
                    self._sleep(step[3], cancel)

                elif kind == "wait":
                    self._sleep(step[1], cancel)
        finally:
            if self.mecanum is not None:
                try:
                    self.mecanum.stop()
                    self.mecanum.set_speed(speed0)
                except Exception:
                    pass
            if self.ptz is not None:
                try:
                    self.ptz.look_center()
                except Exception:
                    pass
            with self._lock:
                if self._thread is threading.current_thread():
                    self._thread = None
                    self._name = None

    @staticmethod
    def _sleep(seconds: float, cancel: threading.Event) -> bool:
        """可被取消的 sleep，返回 True 表示正常结束"""
        end = time.monotonic() + max(0.0, seconds)
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return True
            if cancel.wait(min(left, 0.05)):
                return False


class ExpressSkill(BaseSkill):
    """让机器人做一组宠物动作"""

    name = "express"
    description = (
        "用云台和底盘做宠物动作表达情绪。支持: "
        "nod(点头), shake(摇头), tilt(歪头), wag(摆尾), twist(扭腰), "
        "spin(转圈), nuzzle(蹭蹭), hop(蹦跳), droop(委屈低头), "
        "lean_in(好奇凑近), look_around(左顾右盼), stretch(伸懒腰), stop(停止)"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(ACTIONS) + ["stop"],
                "description": "要做的动作",
            },
        },
        "required": ["action"],
    }

    def __init__(self, player: ExpressionPlayer | None = None):
        self.player = player

    def execute(self, action: str = "nod") -> str:
        name = (action or "nod").strip().lower()

        if name == "stop":
            if self.player is not None:
                self.player.stop()
            return "好，停下来~"

        meta = ACTIONS.get(name)
        if meta is None:
            return f"我还不会 '{action}' 这个动作呢"

        if self.player is None:
            return f"(Mock) 我想{meta['label']}~"

        self.player.play(name)
        return f"好呀，我{meta['label']}给你看~"
