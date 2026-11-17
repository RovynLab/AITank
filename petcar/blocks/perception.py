# -*- coding: utf-8 -*-
"""petcar/blocks/perception.py — 积木用的感知快照
=================================================
后台低频采样，把结果缓存成快照；解释器只读快照，避免检测阻塞控制循环。

第一版支持：人脸、网球、多颜色（从 color_cfg 读阈值，支持迟滞）。
"""

from __future__ import annotations

import threading
import time


# 颜色单个 key 的默认条目（未请求时填充，避免前端 KeyError）
def _color_entry() -> dict:
    return {
        "visible": False,   # 迟滞后对外结论
        "hit": False,       # 本帧是否命中
        "miss": 0,          # 连续未命中次数
        "box": None,        # [x, y, w, h] 或 None
        "area": 0,
        "cx": None,
    }


class PerceptionCache:
    """3~4Hz 的目标检测缓存"""

    INTERVAL = 0.3
    STALE_AFTER = 1.2
    HYSTERESIS_MISS = 2   # 连续多少次未命中才判 "看不到"

    def __init__(self, camera, log=None):
        self.camera = camera
        self._log = log or (lambda level, msg: None)
        self._lock = threading.Lock()
        self._snap = {
            "face": False,
            "tennis": False,
            "colors": {},
            "ts": 0.0,
            # 兼容旧前端的冗余字段：等于 colors.custom.visible
            "color": False,
        }
        self._needed_colors: set[str] = set()
        self._running = False
        self._thread = None
        self._last_warn = 0.0

    # ---------- 按需配置 ----------
    def set_needed_colors(self, keys: list[str] | set[str] | None):
        """告诉感知线程当前程序关心哪些颜色；其他颜色不会计算"""
        with self._lock:
            if keys is None:
                self._needed_colors = set()
            else:
                self._needed_colors = {k for k in keys if k}
            # 确保快照里至少有个 custom key（兼容旧前端）
            if "custom" not in self._needed_colors:
                self._needed_colors.add("custom")

    def needed_colors(self) -> set:
        with self._lock:
            return set(self._needed_colors)

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
        """兼容旧接口: target ∈ {face, tennis, color}。
        新代码请用 sees_color(key)"""
        with self._lock:
            if target == "face":
                return bool(self._snap.get("face", False))
            if target == "tennis":
                return bool(self._snap.get("tennis", False))
            if target == "color":
                # 旧的 "颜色" 积木 → 等同于 custom
                colors = self._snap.get("colors") or {}
                return bool(colors.get("custom", {}).get("visible", False))
            # 新：直接按颜色 key 查
            colors = self._snap.get("colors") or {}
            return bool(colors.get(target, {}).get("visible", False))

    def sees_color(self, key: str) -> bool:
        with self._lock:
            colors = self._snap.get("colors") or {}
            return bool(colors.get(key, {}).get("visible", False))

    def color_box(self, key: str) -> list | None:
        with self._lock:
            colors = self._snap.get("colors") or {}
            return colors.get(key, {}).get("box")

    # ---------- 采样 ----------
    def _warn(self, msg: str):
        now = time.time()
        if now - self._last_warn > 8:
            self._last_warn = now
            self._log("warn", msg)

    @staticmethod
    def _camera_is_open(cam) -> bool:
        """CameraDriver.is_open 是方法, 部分摄像头可能是属性"""
        try:
            value = getattr(cam, "is_open", False)
            return bool(value() if callable(value) else value)
        except Exception:
            return False

    def _loop(self):
        try:
            from ..drivers.detectors import (detect_tennis_ball,
                                             detect_color_blob)
            from ..core import color_cfg as cc
        except Exception as e:
            self._warn(f"识别模块不可用: {e}")
            detect_tennis_ball = detect_color_blob = cc = None

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

                frame = (cam.latest_frame()
                         if hasattr(cam, "latest_frame") else None)
                if frame is None:
                    time.sleep(0.2)
                    continue

                import cv2
                # HSV 只算一次，多颜色共用
                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

                face = bool(cam.detect_faces(frame))
                tennis = (bool(detect_tennis_ball(frame))
                          if detect_tennis_ball else False)

                # 按需颜色检测
                colors_out: dict[str, dict] = {}
                needed = self.needed_colors()
                if detect_color_blob and cc:
                    for key in needed:
                        cfg = cc.get_cfg(key)
                        blob = detect_color_blob(frame, cfg, hsv=hsv)
                        self._apply_color_sample(colors_out, key, blob)

                # 合并旧的 "color" 兼容（用 custom 的结论）
                custom_vis = colors_out.get("custom", {}).get("visible", False)

                with self._lock:
                    self._snap = {
                        "face": face,
                        "tennis": tennis,
                        "color": custom_vis,
                        "colors": colors_out,
                        "ts": time.time(),
                    }
            except Exception as e:
                self._warn(f"识别异常: {e}")
                time.sleep(0.3)
                continue

            time.sleep(self.INTERVAL)

    def _apply_color_sample(self, out: dict, key: str, blob: dict | None):
        """处理一帧颜色样本，做迟滞更新 out[key]"""
        prev = out.get(key) or _color_entry()
        if blob is not None:
            new_vis = True
            miss = 0
            box = [int(blob["x"]), int(blob["y"]),
                   int(blob["w"]), int(blob["h"])]
            area = int(blob["area"])
            cx = float(blob["cx"])
        else:
            new_vis = False
            miss = prev["miss"] + 1
            # 连续 miss 少的时候仍保留上次 box 供调试
            box = prev["box"] if prev["miss"] < self.HYSTERESIS_MISS else None
            area = prev["area"]
            cx = prev["cx"]

        visible = new_vis or (miss < self.HYSTERESIS_MISS)
        out[key] = {
            "visible": visible,
            "hit": new_vis,
            "miss": miss,
            "box": box,
            "area": area,
            "cx": cx,
        }
