# -*- coding: utf-8 -*-
"""
skills/alarm.py — 闹钟 / 倒计时 Skill
"""

from __future__ import annotations

import sys
import os
import threading
import time
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar.skills.base_skill import BaseSkill


class AlarmSkill(BaseSkill):
    """倒计时 / 闹钟"""

    name = "set_alarm"
    description = "设置倒计时或闹钟。seconds: 倒计时秒数; time_str: 绝对时间 HH:MM"
    parameters = {
        "type": "object",
        "properties": {
            "seconds": {
                "type": "number",
                "description": "倒计时秒数",
            },
            "time_str": {
                "type": "string",
                "description": "绝对时间 HH:MM (24小时制)",
            },
        },
        "required": [],
    }

    def __init__(self):
        self._alarms: list = []

    def execute(self, seconds: Optional[float] = None, time_str: Optional[str] = None) -> str:
        if seconds is not None:
            seconds = float(seconds)
            if seconds <= 0:
                return "时间得大于 0 哦"
            t = threading.Timer(seconds, self._fire, args=(f"倒计时结束啦！已经过了{int(seconds)}秒~",))
            t.daemon = True
            t.start()
            self._alarms.append(t)
            return f"好的，{int(seconds)}秒后提醒你！"

        if time_str:
            # HH:MM → 计算今天的目标时间
            try:
                hh, mm = time_str.split(":")
                hh, mm = int(hh), int(mm)
                now = time.localtime()
                target = time.mktime((now.tm_year, now.tm_mon, now.tm_mday,
                                       hh, mm, 0, now.tm_wday, now.tm_yday, now.tm_isdst))
                delay = target - time.time()
                if delay < 0:
                    delay += 86400  # 明天
                t = threading.Timer(delay, self._fire, args=(f"叮咚！现在是 {time_str} 啦~",))
                t.daemon = True
                t.start()
                self._alarms.append(t)
                mins = int(delay / 60)
                return f"好的,我会在 {time_str} 提醒你! (还有{mins}分钟)"
            except Exception as e:
                return f"时间格式不对呢: {e}, 要用 HH:MM 或秒数"

        return "你还没告诉我多少秒或什么时间呢~"

    def _fire(self, msg: str):
        print(f"[Alarm] 响啦! {msg}")
        # TODO: 可以通知 EmotionEngine + TTS
