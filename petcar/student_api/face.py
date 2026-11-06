# -*- coding: utf-8 -*-
"""
student_api/face.py — 学生友好的 Face 数据类
=============================================
让学生能用 `Face(left_eye=..., right_eye=..., mouth=...)` 来画自定义表情。
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional


class EyeStyle(Enum):
    """眼睛形状"""
    CIRCLE   = "circle"    # 普通圆形
    ARC      = "arc"       # 弯月眼 (笑)
    HEART    = "heart"     # 爱心
    LINE     = "line_h"    # 眯缝 / 闭眼
    BIG      = "big"       # 大圆 (惊讶)
    QUESTION = "question"  # 问号


class MouthStyle(Enum):
    """嘴巴形状"""
    LINE       = "line"         # 直线
    SMILE      = "arc_top"      # 上弧 = 笑
    SAD        = "arc_bottom"   # 下弧 = 难过
    OPEN       = "open"         # 张嘴 O
    OPEN_BIG   = "open_big"     # 大笑张嘴
    SKEW       = "skew"         # 歪嘴
    WAVE       = "wave"         # 波浪


class BrowStyle(Enum):
    """眉毛"""
    FLAT      = "flat"       # 平 (不画)
    HAPPY     = "happy"      # 弯眉
    ANGRY     = "angry"      # 倒八字
    SURPRISED = "surprised"  # 高挑
    SAD       = "sad"        # 八字眉


@dataclass
class Face:
    """一张脸 — 可以用 EmotionEngine 渲染"""
    left_eye: EyeStyle = EyeStyle.CIRCLE
    right_eye: EyeStyle = EyeStyle.CIRCLE
    mouth: MouthStyle = MouthStyle.LINE
    brows: BrowStyle = BrowStyle.FLAT
    decor: List[str] = field(default_factory=list)  # "tear_l", "tear_r", "zzz", "sweat", "question"

    def to_dict(self) -> dict:
        """转换成 EmotionEngine 能用的 dict"""
        return {
            "left_eye":  self.left_eye.value,
            "right_eye": self.right_eye.value,
            "mouth":     self.mouth.value,
            "brows":     self.brows.value,
            "decor":     list(self.decor),
        }

    @classmethod
    def happy(cls) -> "Face":
        return cls(left_eye=EyeStyle.ARC, right_eye=EyeStyle.ARC,
                   mouth=MouthStyle.SMILE, brows=BrowStyle.HAPPY)

    @classmethod
    def sad(cls) -> "Face":
        return cls(left_eye=EyeStyle.CIRCLE, right_eye=EyeStyle.CIRCLE,
                   mouth=MouthStyle.SAD, brows=BrowStyle.SAD,
                   decor=["tear_l", "tear_r"])

    @classmethod
    def love(cls) -> "Face":
        return cls(left_eye=EyeStyle.HEART, right_eye=EyeStyle.HEART,
                   mouth=MouthStyle.SMILE, brows=BrowStyle.HAPPY)

    @classmethod
    def wink(cls) -> "Face":
        return cls(left_eye=EyeStyle.ARC, right_eye=EyeStyle.LINE,
                   mouth=MouthStyle.SMILE, brows=BrowStyle.HAPPY)

    @classmethod
    def thinking(cls) -> "Face":
        return cls(left_eye=EyeStyle.CIRCLE, right_eye=EyeStyle.QUESTION,
                   mouth=MouthStyle.SKEW, brows=BrowStyle.FLAT,
                   decor=["question"])

    @classmethod
    def sleepy(cls) -> "Face":
        return cls(left_eye=EyeStyle.LINE, right_eye=EyeStyle.LINE,
                   mouth=MouthStyle.LINE, brows=BrowStyle.FLAT,
                   decor=["zzz"])
