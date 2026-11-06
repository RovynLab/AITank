# -*- coding: utf-8 -*-
"""
skills/face_detect.py — 人脸检测 Skill
"""

from __future__ import annotations

import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar.skills.base_skill import BaseSkill


class FaceDetectSkill(BaseSkill):
    """检测画面中的人脸"""

    name = "detect_face"
    description = "用摄像头检测画面中有几个人脸"
    parameters = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, camera_driver=None):
        self.camera = camera_driver

    def execute(self) -> str:
        if self.camera is None:
            return "(Mock) 我好像看到有个人哦~"
        faces = self.camera.detect_faces()
        if not faces:
            return "我没看到有人哦"
        cx, cy = faces[0][0], faces[0][1]
        return f"我看到了{len(faces)}个人，正中间那个在({cx},{cy})"
