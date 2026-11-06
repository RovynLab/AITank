# -*- coding: utf-8 -*-
"""petcar/blocks/perception.py — 积木用的感知快照
=================================================
后台低频采样，把结果缓存成快照；解释器只读快照，避免检测阻塞控制循环。
第一版支持：人脸、网球（颜色阈值）、颜色块。
"""

from __future__ import annotations

import threading
import time

DEFAULT_COLOR_CFG = {
    "h_min": 25, "h_max": 45,
    "s_min": 90, "s_max": 255,
    "v_min": 90, "v_max": 255,
}


class PerceptionCache:
    """3~4Hz 的目标检测缓存"""

    INTERVAL = 0.3
    STALE_AFTER = 1.2

    def __init__(self, camera, log=None):
        self.camera = camera
        self._log = log or (lambda level, msg: None)
        self._lock = threading.Lock()
        self._snap = {
            "face": False,
            "tennis": False,
            "color": False,
            "ts": 0.0,
        }
        self._running = False
        self._thread = None
        self._last_warn = 0.0

    # ---------- 生命周期 ----------
    def start(self):
        if self._running:
            return
        self._running = True
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.5)
            self._thread = None

    def abort(self):
        """急停用: 只置位, 不等待采样线程退出"""
        self._running = False

    def snapshot(self) -> dict:
        with self._lock:
            snap = dict(self._snap)
        snap["stale"] = (time.time() - snap.get("ts", 0)) > self.STALE_AFTER
        return snap

    def sees(self, target: str) -> bool:
        with self._lock:
            return bool(self._snap.get(target, False))

    # ---------- 采样 ----------
    def _warn(self, msg: str):
        now = time.time()
        if now - self._last_warn > 8:
            self._last_warn = now
            self._log("warn", msg)

    @staticmethod
    def _camera_is_open(cam) -> bool:
        """CameraDriver.is_open 是方法, Mock 摄像头可能是属性"""
        try:
            value = getattr(cam, "is_open", False)
            return bool(value() if callable(value) else value)
        except Exception:
            return False

    def _loop(self):
        # 延迟导入，避免没有 OpenCV 时影响模块导入
        try:
            from ..drivers.detectors import detect_tennis_ball, detect_color
        except Exception as e:
            self._warn(f"识别模块不可用: {e}")
            detect_tennis_ball = detect_color = None

        while self._running:
            try:
                cam = self.camera
                if cam is None:
                    time.sleep(0.5)
                    continue

                if not self._camera_is_open(cam):
                    try:
                        cam.open()
                    except Exception:
                        pass

                frame = cam.latest_frame() if hasattr(cam, "latest_frame") else None
                if frame is None:
                    time.sleep(0.2)
                    continue

                face = bool(cam.detect_faces(frame))
                tennis = bool(detect_tennis_ball(frame)) if detect_tennis_ball else False
                color = bool(detect_color(frame, DEFAULT_COLOR_CFG)) if detect_color else False

                with self._lock:
                    self._snap = {
                        "face": face,
                        "tennis": tennis,
                        "color": color,
                        "ts": time.time(),
                    }
            except Exception as e:
                self._warn(f"识别异常: {e}")
                time.sleep(0.3)
                continue

            time.sleep(self.INTERVAL)
