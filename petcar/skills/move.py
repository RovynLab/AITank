# -*- coding: utf-8 -*-
"""
skills/move.py — 底盘运动 Skill
"""

from __future__ import annotations

import sys
import os
import threading
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar.skills.base_skill import BaseSkill


class MoveSkill(BaseSkill):
    """控制小车底盘运动"""

    name = "move"
    description = "控制小车底盘运动。支持 forward(前进), backward(后退), leftSlide(左移), rightSlide(右移), turnLeft(左转), turnRight(右转), spin(原地旋转), stop(停止)"
    parameters = {
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "enum": ["forward", "backward", "leftSlide", "rightSlide",
                         "turnLeft", "turnRight", "spin", "stop"],
                "description": "运动方向",
            },
            "duration": {
                "type": "number",
                "description": "运动持续秒数, 默认 2 秒",
            },
        },
        "required": ["direction"],
    }

    def __init__(self, mecanum_driver=None):
        self.mecanum = mecanum_driver
        self._MOTION_MAP = {
            "forward":    lambda: self.mecanum.forward(),
            "backward":   lambda: self.mecanum.backward(),
            "leftSlide":  lambda: self.mecanum.leftSlide(),
            "rightSlide": lambda: self.mecanum.rightSlide(),
            "turnLeft":   lambda: self.mecanum.turnLeft(),
            "turnRight":  lambda: self.mecanum.turnRight(),
            "spin":       lambda: self.mecanum.spin(),
            "stop":       lambda: self.mecanum.stop(),
        }

    def execute(self, direction: str, duration: float = 2.0) -> str:
        if self.mecanum is None:
            return "底盘未连接，无法移动"
        direction = direction or "forward"
        duration = float(duration or 2.0)
        duration = max(0.5, min(30.0, duration))

        action = self._MOTION_MAP.get(direction, self.mecanum.stop)
        action()
        if direction != "stop":
            # duration 秒后自动停
            threading.Timer(duration, self.mecanum.stop).start()

        cn = {
            "forward": "前进", "backward": "后退",
            "leftSlide": "左移", "rightSlide": "右移",
            "turnLeft": "左转", "turnRight": "右转",
            "spin": "原地旋转", "stop": "停止",
        }.get(direction, direction)
        return f"好的，我{cn}{duration}秒！"
