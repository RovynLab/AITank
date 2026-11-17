# -*- coding: utf-8 -*-
"""
skills/ptz.py — 云台舵机 Skill
"""

from __future__ import annotations

import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar.skills.base_skill import BaseSkill


class PTZSkill(BaseSkill):
    """云台运动"""

    name = "look"
    description = "控制云台摄像头转动。direction: up/down/left/right/center"
    parameters = {
        "type": "object",
        "properties": {
            "direction": {
                "type": "string",
                "enum": ["up", "down", "left", "right", "center"],
                "description": "云台方向",
            },
            "delta": {
                "type": "number",
                "description": "转动角度 (度数), 默认 10",
            },
        },
        "required": ["direction"],
    }

    def __init__(self, ptz_driver=None):
        self.ptz = ptz_driver

    def execute(self, direction: str, delta: float = 10.0) -> str:
        if self.ptz is None:
            return "云台未连接，无法转动"
        delta = float(delta or 10.0)
        delta = max(1.0, min(45.0, delta))

        if direction == "up":
            self.ptz.look_up(delta)
            return f"好的，我抬头看~"
        elif direction == "down":
            self.ptz.look_down(delta)
            return f"好的，我低头看~"
        elif direction == "left":
            self.ptz.look_left(delta)
            return f"好的，我往左看~"
        elif direction == "right":
            self.ptz.look_right(delta)
            return f"好的，我往右看~"
        elif direction == "center":
            self.ptz.look_center()
            return f"好的，我回到中间~"
        else:
            return f"我不太懂这个方向 '{direction}' 呢"
