# -*- coding: utf-8 -*-
"""
skills/emote.py — 直接控制表情 Skill
"""

from __future__ import annotations

import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar.skills.base_skill import BaseSkill

VALID_EMOTIONS = [
    "happy", "sad", "angry", "surprised", "sleepy",
    "love", "neutral", "wink", "laugh", "thinking", "scared", "confused",
]


class EmoteSkill(BaseSkill):
    """让机器人显示指定表情"""

    name = "show_emotion"
    description = "让我显示指定表情。支持: happy(开心), sad(难过), angry(生气), surprised(惊讶), love(爱心), sleepy(困), neutral(平静), wink(眨眼), laugh(大笑), thinking(思考), scared(害怕), confused(困惑)"
    parameters = {
        "type": "object",
        "properties": {
            "emotion": {
                "type": "string",
                "enum": VALID_EMOTIONS,
                "description": "要显示的表情",
            },
        },
        "required": ["emotion"],
    }

    def __init__(self, emotion_engine=None):
        self.emotion = emotion_engine

    def execute(self, emotion: str) -> str:
        emotion = (emotion or "").lower()
        if emotion not in VALID_EMOTIONS:
            return f"我不太会 '{emotion}' 这个表情呢"
        if self.emotion is not None:
            self.emotion.set_emotion(emotion, duration=5)
        cn = {
            "happy": "开心", "sad": "难过", "angry": "生气",
            "surprised": "惊讶", "love": "爱心", "sleepy": "困",
            "neutral": "平静", "wink": "眨眼", "laugh": "大笑",
            "thinking": "思考", "scared": "害怕", "confused": "困惑",
        }.get(emotion, emotion)
        return f"好的，我现在{cn}了~"
