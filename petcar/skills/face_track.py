# -*- coding: utf-8 -*-
"""
skills/face_track.py — 人脸追踪 Skill
"""

from __future__ import annotations

import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar.skills.base_skill import BaseSkill


class FaceTrackSkill(BaseSkill):
    """让云台自动追踪最大人脸"""

    name = "track_face"
    description = "让云台自动追踪画面中最大的人脸 (持续30秒)"
    parameters = {
        "type": "object",
        "properties": {},
    }

    def __init__(self, camera_driver=None, ptz_driver=None):
        self.camera = camera_driver
        self.ptz = ptz_driver

    def execute(self) -> str:
        if self.camera is None or self.ptz is None:
            return "(Mock) 好的，我来追踪你~"
        self.camera.start_face_tracking(self.ptz, stop_after=30.0)
        return "好的，我来追踪你~ 30秒后自动停止"
