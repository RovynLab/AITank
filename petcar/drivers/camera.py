# -*- coding: utf-8 -*-
"""
drivers/camera.py — 摄像头 + 人脸检测 + 追踪
=============================================
用 OpenCV 打开 USB 摄像头。
人脸检测优先用 FaceDetectorYN (OpenCV 5.0 YuNet), 退回 Haar。
"""

from __future__ import annotations

import sys
import os
import time
import threading
import numpy as np
from typing import List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar import config

import cv2

FaceBox = Tuple[int, int, int, int, float]  # (cx, cy, w, h, score)


class CameraDriver:
    """摄像头封装"""

    def __init__(self,
                 index: int = config.CAMERA_INDEX,
                 width: int = config.CAMERA_WIDTH,
                 height: int = config.CAMERA_HEIGHT):
        self.index = index
        self.width = width
        self.height = height
        self.cap: Optional[cv2.VideoCapture] = None
        self._lock = threading.Lock()
        self._running = False
        self._latest_frame = None
        self._frame_thread: Optional[threading.Thread] = None

        # 人脸检测
        self._yunet = None
        self._haar = None
        self._det_lock = threading.Lock()  # 检测器非线程安全, 多线程调用必须串行
        self._init_detector()

        # 人脸追踪状态
        self._tracking = False
        self._tracking_thread: Optional[threading.Thread] = None
        self._tracking_stop = threading.Event()

    # ========================================================================
    # 初始化摄像头 + 人脸模型
    # ========================================================================
    def open(self) -> bool:
        """打开摄像头"""
        self.cap = cv2.VideoCapture(self.index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if not self.cap.isOpened():
            print(f"[Camera] 打不开 index={self.index}")
            self.cap = None
            return False
        self._running = True
        self._frame_thread = threading.Thread(target=self._frame_loop, daemon=True)
        self._frame_thread.start()
        print("[Camera] 已打开，开始采集帧")
        return True

    def close(self):
        self._running = False
        self.stop_face_tracking()
        if self._frame_thread:
            self._frame_thread.join(timeout=2)
        if self.cap:
            self.cap.release()
            self.cap = None
        with self._lock:
            self._latest_frame = None

    def _frame_loop(self):
        while self._running:
            if self.cap is None:
                time.sleep(0.1)
                continue
            try:
                ret, frame = self.cap.read()
            except Exception:
                # USB 摄像头偶发读帧异常: 别让线程死掉
                time.sleep(0.5)
                continue
            if ret and frame is not None:
                with self._lock:
                    self._latest_frame = frame
            else:
                time.sleep(0.05)

    # ========================================================================
    # 帧获取 / 拍照
    # ========================================================================
    @property
    def is_open(self) -> bool:
        return self.cap is not None

    @property
    def tracking(self) -> bool:
        return self._tracking

    def latest_frame(self) -> Optional[np.ndarray]:
        """取最新一帧 (不等待, 没有就返回 None)。给视频流用。"""
        with self._lock:
            return None if self._latest_frame is None else self._latest_frame.copy()

    def capture(self) -> Optional[np.ndarray]:
        """取最新一帧 (阻塞直到有帧)"""
        # 若摄像头未开，尝试开
        if self.cap is None:
            if not self.open():
                return None
        # 最多等 1 秒
        deadline = time.time() + 1.0
        while time.time() < deadline:
            with self._lock:
                if self._latest_frame is not None:
                    return self._latest_frame.copy()
            time.sleep(0.02)
        return None

    def take_photo(self, save_path: Optional[str] = None) -> Optional[str]:
        """拍照并保存。返回文件路径。"""
        frame = self.capture()
        if frame is None:
            return None
        if save_path is None:
            save_path = os.path.join(config.PHOTO_DIR, f"{int(time.time())}.jpg")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        cv2.imwrite(save_path, frame)
        return save_path

    # ========================================================================
    # 人脸检测
    # ========================================================================
    def _init_detector(self):
        """尝试多种方式初始化人脸检测器"""
        # 方案 1: OpenCV 5.0 FaceDetectorYN
        yunet_path = os.path.join(os.path.expanduser("~"), ".opencv", "models",
                                  "face_detection_yunet_2023mar.onnx")
        if os.path.exists(yunet_path):
            try:
                self._yunet = cv2.FaceDetectorYN_create(
                    model=yunet_path, config="",
                    input_size=(320, 320), score_threshold=0.9,
                    nms_threshold=0.3, top_k=5000,
                )
                print("[Camera] FaceDetectorYN 加载成功")
                return
            except Exception as e:
                print(f"[Camera] YuNet 加载失败: {e}")

        # 方案 2: Haar 级联
        cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        if os.path.exists(cascade_path):
            try:
                self._haar = cv2.CascadeClassifier(cascade_path)
                print("[Camera] Haar 级联加载成功")
                return
            except Exception:
                pass

        print("[Camera] 未找到任何人脸检测器, detect_faces 将返回空")

    def detect_faces(self, frame: Optional[np.ndarray] = None) -> List[FaceBox]:
        """检测当前帧中的所有人脸。返回 [(cx, cy, w, h, score), ...]"""
        if frame is None:
            frame = self.capture()
        if frame is None:
            return []

        h, w = frame.shape[:2]

        with self._det_lock:
            if self._yunet is not None:
                self._yunet.setInputSize((w, h))
                _, faces = self._yunet.detect(frame)
                if faces is None:
                    return []
                result = []
                for f in faces:
                    fx, fy, fw, fh = int(f[0]), int(f[1]), int(f[2]), int(f[3])
                    cx, cy = fx + fw // 2, fy + fh // 2
                    result.append((cx, cy, fw, fh, float(f[4])))
                return result

            elif self._haar is not None:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                rects = self._haar.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
                return [(x + w // 2, y + h // 2, w, h, 0.99) for (x, y, w, h) in rects]

        return []

    # ========================================================================
    # 人脸追踪
    # ========================================================================
    def start_face_tracking(self, ptz_driver, stop_after: float = 30.0):
        """启动后台线程，自动让云台追踪最大的人脸"""
        if self._tracking:
            return
        self._tracking = True
        self._tracking_stop.clear()
        self._tracking_thread = threading.Thread(
            target=self._face_tracking_loop,
            args=(ptz_driver, stop_after), daemon=True,
        )
        self._tracking_thread.start()
        print("[Camera] 开始追踪人脸")

    def stop_face_tracking(self):
        if self._tracking:
            self._tracking_stop.set()
            self._tracking = False
            if self._tracking_thread:
                self._tracking_thread.join(timeout=2)
            print("[Camera] 停止追踪")

    def _face_tracking_loop(self, ptz_driver, stop_after: float):
        """追踪循环: 检测最大人脸 → 算画面中心偏差 → 调整云台"""
        start = time.time()
        img_cx = self.width // 2
        img_cy = self.height // 2
        dead_zone_x = 40   # 像素
        dead_zone_y = 30

        while not self._tracking_stop.is_set():
            if time.time() - start > stop_after:
                break

            faces = self.detect_faces()
            if faces:
                # 找最大的
                biggest = max(faces, key=lambda f: f[2] * f[3])
                cx, cy = biggest[0], biggest[1]

                err_x = cx - img_cx
                err_y = cy - img_cy

                # 比例 → 角度偏差
                # 画面宽 640px → 云台水平 180°, 约 3.5 px/°
                scale_x = 640.0 / 180.0
                scale_y = 480.0 / 90.0   # 垂直可用范围约 90°

                if abs(err_x) > dead_zone_x:
                    delta_h = -err_x / scale_x  # 偏差偏右 → 云台向左转
                    ptz_driver.h_increase(delta_h)
                if abs(err_y) > dead_zone_y:
                    delta_v = -err_y / scale_y
                    ptz_driver.v_increase(delta_v)

            time.sleep(0.15)

        self._tracking = False


if __name__ == "__main__":
    cam = CameraDriver()
    print("拍照测试...")
    p = cam.take_photo()
    print(f"照片: {p}")
    print("人脸检测测试 (10 秒)...")
    t0 = time.time()
    while time.time() - t0 < 10:
        faces = cam.detect_faces()
        if faces:
            print(f"  检测到 {len(faces)} 张脸: {[(f[0], f[1]) for f in faces]}")
        time.sleep(1)
    cam.close()
