# -*- coding: utf-8 -*-
"""
skills/weather.py — 天气查询 Skill
=================================
使用 wttr.in 免费 API, 无需 Key。
"""

from __future__ import annotations

import sys
import os
import time
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar.skills.base_skill import BaseSkill


class WeatherSkill(BaseSkill):
    """查询城市天气"""

    name = "weather"
    description = "查询城市天气, 返回当前温度、天气状况"
    parameters = {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市名, 默认 '北京'",
            },
        },
        "required": [],
    }

    def execute(self, city: str = "北京") -> str:
        try:
            import requests
            # wttr.in 的简明格式
            resp = requests.get(
                f"https://wttr.in/{city}?format=j1",
                timeout=5,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            cur = data["current_condition"][0]
            temp = cur.get("temp_C", "?")
            desc_list = cur.get("lang_zh", cur.get("weatherDesc", [{"value": "?"}]))
            desc = desc_list[0].get("value", "?")
            humid = cur.get("humidity", "?")
            return f"{city}现在{temp}°C, {desc}, 湿度{humid}%"
        except Exception as e:
            return f"查天气失败了 {e}，要不稍后再试？"
