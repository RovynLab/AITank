# -*- coding: utf-8 -*-
"""
skills/photo.py — 拍照 Skill
"""

from __future__ import annotations

import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar.skills.base_skill import BaseSkill


class PhotoSkill(BaseSkill):
    """用摄像头拍一张照片"""

    name = "take_photo"
    description = "用摄像头拍一张照片，保存到本地并返回文件路径"
    parameters = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, camera_driver=None):
        self.camera = camera_driver

    def execute(self) -> str:
        if self.camera is None:
            return "(Mock) 咔嚓！照片会保存在 photos/ 目录下"
        path = self.camera.take_photo()
        if path:
            return f"咔嚓！照片已保存: {path}"
        return "哎呀，拍照失败了...摄像头好像不太工作"
