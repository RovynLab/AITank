# -*- coding: utf-8 -*-
"""drivers/gesture.py — 手势识别 (MediaPipe 优先, OpenCV 凸包兜底)
==================================================================
面板「对象识别 → 手势识别」使用本模块, 自动选择识别引擎:

1. MediaPipe HandLandmarker (Tasks API, 精度高)
   条件: CPU 支持 ARMv8 AES + mediapipe 可导入 + 模型存在
   模型: models/hand_landmarker.task (可用 PETCAR_HAND_MODEL 指定)
2. OpenCV 凸包缺陷法 (兜底, 树莓派 4B/3B 等无 AES 的板卡)
   肤色分割 → 最大轮廓 → 凸包缺陷数指缝 → 手势

注: 树莓派 4B (Cortex-A72) 没有 AES 指令, MediaPipe 1.x 预编译包初始化
会直接 SIGILL, 因此只能用 OpenCV 兜底; 树莓派 5 会走 MediaPipe。

输出与 detectors.py 统一: (x, y, w, h, score, 手势英文标签),
供视频流画框叠字 (cv2.putText 只能画 ASCII)。
"""

from __future__ import annotations

import math
import os
import platform
import time
from collections import Counter, deque
from pathlib import Path

import cv2
import numpy as np

# 视频叠加文字 (ASCII)
GESTURE_TEXT = {
    "fist": "FIST",
    "one": "ONE",
    "peace": "PEACE",
    "three": "THREE",
    "four": "FOUR",
    "open": "OPEN PALM",
    "thumbs_up": "THUMB UP",
    "thumbs_down": "THUMB DOWN",
    "ok": "OK",
    "unknown": "UNKNOWN",
}

# MediaPipe 关键点: 指尖 / 近端指节
FINGER_TIPS = {"thumb": (4, 2), "index": (8, 6), "middle": (12, 10),
               "ring": (16, 14), "pinky": (20, 18)}

MODEL_NAME = "hand_landmarker.task"


# ----------------------------------------------------------------------
# 环境探测
# ----------------------------------------------------------------------
def _board_model() -> str:
    """读板卡型号, 如 'Raspberry Pi 4 Model B Rev 1.1'"""
    try:
        with open("/proc/device-tree/model", "rb") as f:
            return f.read().decode("utf-8", errors="ignore").strip("\x00").strip()
    except OSError:
        return ""


def _cpu_ok() -> bool:
    """MediaPipe aarch64 包需要 AES 指令; 树莓派 4B/3B 都没有, 会 SIGILL"""
    if platform.machine().lower() not in ("aarch64", "arm64", "armv7l", "armv8l"):
        return True
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="ignore") as f:
            return "aes" in f.read()
    except OSError:
        return True


def _find_model() -> str | None:
    """按环境变量 → 仓库 models/ → ~/.opencv/models 顺序找模型"""
    candidates = []
    if os.environ.get("PETCAR_HAND_MODEL"):
        candidates.append(Path(os.environ["PETCAR_HAND_MODEL"]))
    root = Path(__file__).resolve().parents[2]
    candidates += [root / "models" / MODEL_NAME,
                   Path.home() / ".opencv" / "models" / MODEL_NAME,
                   Path.cwd() / "models" / MODEL_NAME]
    for p in candidates:
        if p.is_file():
            return str(p)
    return None


# ----------------------------------------------------------------------
# OpenCV 兜底算法
# ----------------------------------------------------------------------
def _skin_mask(frame):
    """YCrCb 肤色分割 + 去暗部 + 形态学去噪"""
    ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
    mask = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mask = cv2.bitwise_and(mask, cv2.inRange(gray, 40, 255))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    return cv2.GaussianBlur(mask, (5, 5), 0)


def _solidity(contour) -> float:
    """实心度 = 轮廓面积 / 凸包面积, 拳头≈0.95, 张开手掌≈0.7"""
    hull_area = cv2.contourArea(cv2.convexHull(contour))
    return cv2.contourArea(contour) / hull_area if hull_area > 1 else 0.0


def _count_gaps(contour) -> int:
    """数手指之间的凹槽 (凸包缺陷): 深度够 + 夹角 ≤ 90°"""
    if len(contour) < 5:
        return 0
    hull = cv2.convexHull(contour, returnPoints=False)
    if hull is None or len(hull) < 4:
        return 0
    try:
        defects = cv2.convexityDefects(contour, hull)
    except cv2.error:
        return 0
    if defects is None:
        return 0

    depth_min = max(12.0, 0.10 * math.sqrt(cv2.contourArea(contour)))
    gaps = 0
    for s, e, f, d in defects.reshape(-1, 4):
        if d / 256.0 < depth_min:
            continue
        p1 = contour[s][0].astype(float)
        p2 = contour[e][0].astype(float)
        pf = contour[f][0].astype(float)
        a = np.linalg.norm(p2 - p1)
        b = np.linalg.norm(pf - p1)
        c = np.linalg.norm(pf - p2)
        if a < 1e-6 or b * c < 1e-6:
            continue
        cos = (b * b + c * c - a * a) / (2 * b * c)
        if math.acos(max(-1.0, min(1.0, cos))) <= math.pi / 2:
            gaps += 1
    return gaps


def _classify_cv(contour):
    """指缝数 + 实心度 → 手势 (0 指缝时用实心度区分拳头/一指)"""
    sol = _solidity(contour)
    gaps = _count_gaps(contour)
    if gaps <= 0:
        return ("fist" if sol > 0.90 else "one"), sol
    return {1: "peace", 2: "three", 3: "four"}.get(gaps, "open"), sol


# ----------------------------------------------------------------------
# 检测器
# ----------------------------------------------------------------------
class GestureDetector:
    """手势检测器: MediaPipe 可用时优先, 否则 OpenCV 凸包兜底。

    - 每只手独立画框, 最多 2 只手 (仅 MediaPipe 支持多手)
    - 最近 smooth 帧多数投票, 抑制手势结果抖动
    - 引擎初始化失败自动降级, 不影响视频流和其他识别功能
    """

    def __init__(self, max_hands: int = 2, smooth: int = 5, log=None):
        self.max_hands = max_hands
        self.smooth = smooth
        self._log = log
        self._engine = None       # None / "mp" / "cv"
        self._mp = None
        self._landmarker = None
        self._last_ts = 0
        self._hist = {}           # MediaPipe: 左右手 → 最近手势
        self._cv_hist = deque(maxlen=smooth)

    # ------------------------------------------------------------------
    # 引擎选择: 优先 MediaPipe, 不满足条件就 OpenCV
    # ------------------------------------------------------------------
    def _init_engine(self):
        reason = ""
        if not _cpu_ok():
            reason = "CPU 无 ARMv8 AES 指令"
        elif _find_model() is None:
            reason = f"缺少 {MODEL_NAME}"
        else:
            try:
                import mediapipe as mp
                from mediapipe.tasks import python as mp_python
                from mediapipe.tasks.python import vision

                options = vision.HandLandmarkerOptions(
                    base_options=mp_python.BaseOptions(
                        model_asset_path=_find_model()),
                    running_mode=vision.RunningMode.VIDEO,
                    num_hands=self.max_hands,
                    min_hand_detection_confidence=0.5,
                    min_hand_presence_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
                self._landmarker = vision.HandLandmarker.create_from_options(options)
                self._mp = mp
                self._engine = "mp"
                if self._log:
                    self._log(f"手势识别引擎: MediaPipe {mp.__version__}")
                return
            except Exception as e:
                reason = str(e)

        self._engine = "cv"
        if self._log:
            self._log(f"手势识别引擎: OpenCV 凸包 (MediaPipe 不可用: {reason})")

    def close(self):
        if self._landmarker is not None:
            try:
                self._landmarker.close()
            except Exception:
                pass
            self._landmarker = None

    def detect(self, frame):
        """返回 [(x, y, w, h, score, text), ...]; 没检测到手返回 []"""
        if self._engine is None:
            self._init_engine()
        if self._engine == "mp":
            try:
                return self._detect_mp(frame)
            except Exception as e:
                if self._log:
                    self._log(f"MediaPipe 运行失败, 切换 OpenCV 兜底: {e}")
                self._engine = "cv"
                self._landmarker = None
        return self._detect_cv(frame)

    # ------------------------------------------------------------------
    # MediaPipe 实现
    # ------------------------------------------------------------------
    def _detect_mp(self, frame):
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        ts = int(time.monotonic() * 1000)
        if ts <= self._last_ts:            # 时间戳必须严格递增
            ts = self._last_ts + 1
        self._last_ts = ts

        result = self._landmarker.detect_for_video(image, ts)
        if not result.hand_landmarks:
            self._hist.clear()
            return []

        out = []
        for i, hand_lm in enumerate(result.hand_landmarks):
            lm = [(p.x, p.y, p.z) for p in hand_lm]
            pts = np.array([(p[0] * w, p[1] * h) for p in lm])
            x1, y1 = pts.min(axis=0).astype(int)
            x2, y2 = pts.max(axis=0).astype(int)
            pad = int(0.06 * max(x2 - x1, y2 - y1)) + 8
            x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
            x2, y2 = min(w - 1, x2 + pad), min(h - 1, y2 + pad)

            gesture = self._recognize(lm)
            # 按左右手分别平滑, 避免两只手结果串台
            key = "hand"
            if (result.handedness and i < len(result.handedness)
                    and result.handedness[i]):
                key = result.handedness[i][0].category_name
            buf = self._hist.setdefault(key, deque(maxlen=self.smooth))
            buf.append(gesture)
            stable = Counter(buf).most_common(1)[0][0]

            out.append((int(x1), int(y1), int(x2 - x1), int(y2 - y1),
                        buf.count(stable) / len(buf),
                        GESTURE_TEXT.get(stable, "UNKNOWN")))
        return out

    # ------------------------------------------------------------------
    # OpenCV 兜底实现
    # ------------------------------------------------------------------
    def _detect_cv(self, frame):
        h, w = frame.shape[:2]
        scale = 320.0 / w if w > 320 else 1.0
        small = cv2.resize(frame, None, fx=scale, fy=scale,
                           interpolation=cv2.INTER_AREA) if scale < 1.0 else frame
        sh, sw = small.shape[:2]

        cnts, _ = cv2.findContours(_skin_mask(small), cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
        cnts = [c for c in cnts if cv2.contourArea(c) >= 0.02 * sw * sh]
        if not cnts:
            self._cv_hist.clear()
            return []

        c = max(cnts, key=cv2.contourArea)
        gesture, sol = _classify_cv(c)
        self._cv_hist.append(gesture)
        stable = Counter(self._cv_hist).most_common(1)[0][0]

        x, y, bw, bh = cv2.boundingRect(c)
        if scale != 1.0:
            x, y, bw, bh = (int(x / scale), int(y / scale),
                            int(bw / scale), int(bh / scale))
        pad = int(0.05 * max(bw, bh)) + 8
        x1, y1 = max(0, x - pad), max(0, y - pad)
        x2, y2 = min(w - 1, x + bw + pad), min(h - 1, y + bh + pad)

        return [(x1, y1, x2 - x1, y2 - y1, sol,
                 GESTURE_TEXT.get(stable, "UNKNOWN"))]

    # ------------------------------------------------------------------
    # MediaPipe 手势判定: 指尖到手腕距离 > 指节到手腕 → 手指伸直
    # ------------------------------------------------------------------
    @staticmethod
    def _angle(a, b, c):
        """三点夹角 (弧度), 顶点是 b"""
        v1 = np.array(a[:2], dtype=float) - np.array(b[:2], dtype=float)
        v2 = np.array(c[:2], dtype=float) - np.array(b[:2], dtype=float)
        denom = np.linalg.norm(v1) * np.linalg.norm(v2)
        if denom < 1e-6:
            return math.pi
        cos = float(np.dot(v1, v2) / denom)
        return math.acos(max(-1.0, min(1.0, cos)))

    @staticmethod
    def _recognize(lm):
        wrist = np.array(lm[0][:2])
        palm = np.linalg.norm(np.array(lm[9][:2]) - wrist)  # 腕→中指根
        if palm < 1e-6:
            return "unknown"

        ext = {}
        for name, (tip, pip) in FINGER_TIPS.items():
            d_tip = np.linalg.norm(np.array(lm[tip][:2]) - wrist)
            d_pip = np.linalg.norm(np.array(lm[pip][:2]) - wrist)
            ext[name] = d_tip > d_pip + 0.15 * palm
        # 拇指: 指节伸直且指尖离开食指根部, 才算伸出 (握拳时拇指会收向掌心)
        thumb_straight = GestureDetector._angle(lm[2], lm[3], lm[4]) > 2.3
        thumb_away = np.linalg.norm(
            np.array(lm[4][:2]) - np.array(lm[5][:2])) > 0.65 * palm
        ext["thumb"] = bool(thumb_straight and thumb_away)

        n = sum(ext.values())

        # OK: 拇指尖与食指尖贴近, 中指/无名指/小指伸直
        d_thumb_index = np.linalg.norm(
            np.array(lm[4][:2]) - np.array(lm[8][:2]))
        if (d_thumb_index < 0.45 * palm and ext["middle"]
                and ext["ring"] and ext["pinky"]):
            return "ok"

        if n == 0:
            return "fist"
        if n == 5:
            return "open"

        # 只伸拇指: 按指尖相对手腕的方向区分点赞/踩
        if ext["thumb"] and n == 1:
            dy = lm[4][1] - lm[0][1]
            if dy < -0.5 * palm:
                return "thumbs_up"
            if dy > 0.5 * palm:
                return "thumbs_down"
            return "one"

        # 只伸食指 / 食指+中指 / 三指 / 四指
        if ext["index"] and not ext["middle"]:
            return "one"
        if ext["index"] and ext["middle"] and not ext["ring"]:
            return "peace"
        if ext["index"] and ext["middle"] and ext["ring"] and not ext["pinky"]:
            return "three"
        if ext["index"] and ext["middle"] and ext["ring"] and ext["pinky"]:
            return "four"

        return {1: "one", 2: "peace", 3: "three", 4: "four"}.get(n, "unknown")
