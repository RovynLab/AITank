#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
手势识别 v2 —— MediaPipe Hands 版 (带 OpenCV 降级)
================================================

优先使用 MediaPipe Hands (精度高), 没装 mediapipe 时自动降级到
OpenCV HandDetector (opencv-contrib-python, 精度略低但树莓派原生能跑)。

替代原来基于 OpenCV 凸包缺陷的 finger.py。

依赖:
    优先: pip install mediapipe opencv-python numpy
    降级: apt install python3-opencv-contrib (或 pip opencv-contrib-python)

使用:
    python3 finger_v2.py          # 自动选最优后端
    python3 finger_v2.py --demo  # 演示 + 手势色块
    按 q 退出
"""

import cv2
import numpy as np
import argparse
import time
import os

# ============================================================
# 后端选择: MediaPipe (优先) → OpenCV HandDetector (降级)
# ============================================================
USE_MEDIAPIPE = False
USE_OPENCV_HAND = False
mp = None
mp_hands = None
mp_drawing = None
mp_drawing_styles = None
hands = None
hand_detector = None

try:
    import mediapipe as mp
    mp_hands = mp.solutions.hands
    mp_drawing = mp.solutions.drawing_utils
    mp_drawing_styles = mp.solutions.drawing_styles
    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    USE_MEDIAPIPE = True
    print("✅ 后端: MediaPipe Hands (高精度)")
except Exception as e:
    # mediapipe 可能装上了但版本太新 (1.2.0+ 移除了 solutions API)
    print(f"⚠️  MediaPipe 不可用 ({type(e).__name__}: {e})")
    # 试 OpenCV HandDetector
    try:
        from cv2 import HandDetector  # opencv-contrib-python >= 4.5
        hand_detector = HandDetector(maxHands=2, detectionCon=0.5)
        USE_OPENCV_HAND = True
        print("✅ 后端: OpenCV HandDetector")
    except Exception:
        print("❌ 没有可用的手势检测后端 (MediaPipe 或 OpenCV HandDetector)")
        print("   - 树莓派 3B+ 可能需要降 OpenCV 到 4.8 恢复 HandDetector")
        print("   - 或换树莓派 4B/5 + MediaPipe 1.0 旧版")


# ============================================================
# 1. 手部检测统一接口 (两个后端共享 landmarks 格式)
# ============================================================
def detect_landmarks(frame: np.ndarray):
    """
    检测帧里的手, 返回 [(landmarks, handedness_label), ...]

    landmarks: 21 个 (x, y, z) 点, 归一化坐标 (0~1), 兼容 MediaPipe 格式
    handedness_label: "Left" / "Right" / "Unknown"
    """
    h, w = frame.shape[:2]

    if USE_MEDIAPIPE:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = hands.process(rgb)
        rgb.flags.writeable = True

        out = []
        if results.multi_hand_landmarks:
            for hand_lm, handedness in zip(
                results.multi_hand_landmarks,
                results.multi_handedness,
            ):
                lm_norm = [(lm.x, lm.y, lm.z) for lm in hand_lm.landmark]
                label = handedness.classification[0].label
                out.append((lm_norm, label, hand_lm))  # 3rd 元素用于 drawing
        return out

    elif USE_OPENCV_HAND:
        # OpenCV HandDetector 返回像素坐标, 需要转归一化
        hands_info = hand_detector.findHands(frame, draw=False)
        out = []
        if hands_info:
            for hand in hands_info:
                lm_list = hand.get("lmList", []) or []
                # lmList: [(cx, cy), ...] 像素坐标, 21 个点
                lm_norm = [(cx / w, cy / h, 0.0) for cx, cy, *_ in lm_list]
                handedness = hand.get("type", "Right")  # OpenCV 返回 "Left"/"Right"
                out.append((lm_norm, handedness, lm_list))
        return out

    return []


def draw_overlay(bg, frame, detections, stable_gesture_map):
    """在画面上画 landmark + 骨架 + 手势标签"""
    h, w = frame.shape[:2]
    for idx, (landmarks, handedness, raw) in enumerate(detections):
        # 画骨架
        if USE_MEDIAPIPE:
            mp_drawing.draw_landmarks(
                bg, raw,
                mp_hands.HAND_CONNECTIONS,
                mp_drawing_styles.get_default_hand_landmarks_style(),
                mp_drawing_styles.get_default_hand_connections_style(),
            )
        elif USE_OPENCV_HAND:
            # OpenCV HandDetector 没有 HAND_CONNECTIONS, 画圆点就行
            for cx, cy, *_ in raw:
                cv2.circle(bg, (int(cx), int(cy)), 4, (0, 255, 255), -1)

        # 手势标签
        gesture = stable_gesture_map.get(idx, "unknown")
        color = GESTURE_COLORS.get(gesture, (128, 128, 128))
        label = f"{handedness}: {GESTURE_CN.get(gesture, gesture)}"
        # 手腕位置
        wrist_x = int(landmarks[0][0] * w)
        wrist_y = int(landmarks[0][1] * h)

        cv2.putText(
            bg, label,
            (wrist_x + 10, wrist_y - 10),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2, cv2.LINE_AA,
        )
        cv2.circle(bg, (wrist_x, wrist_y), 5, color, -1)


# ============================================================
# 2. 手势识别核心 (两个后端共享)
# ============================================================

def count_extended_fingers(landmarks):
    """
    用 21 个归一化关键点判断伸出了几根手指。
    MediaPipe 和 OpenCV HandDetector 的 landmark 编号一致, 可共享。
    """
    if not landmarks or len(landmarks) < 21:
        return -1

    finger_tips = [8, 12, 16, 20]
    pip_joints = [6, 10, 14, 18]
    count = 0

    # 拇指
    thumb_tip = landmarks[4]
    thumb_mcp = landmarks[2]
    wrist = landmarks[0]
    d_tip = np.hypot(thumb_tip[0] - wrist[0], thumb_tip[1] - wrist[1])
    d_mcp = np.hypot(thumb_mcp[0] - wrist[0], thumb_mcp[1] - wrist[1])
    if d_tip > d_mcp * 1.1:
        count += 1

    # 其他 4 指
    for tip_idx, pip_idx in zip(finger_tips, pip_joints):
        tip = landmarks[tip_idx]
        pip = landmarks[pip_idx]
        if tip[1] < pip[1] - 0.02:
            count += 1

    return count


def recognize_gesture(landmarks):
    """识别具体手势名称"""
    n = count_extended_fingers(landmarks)
    if n < 0:
        return "unknown"

    wrist = landmarks[0]
    thumb_tip = landmarks[4]
    index_tip = landmarks[8]
    index_pip = landmarks[6]

    # OK 手势: 拇指尖+食指尖靠得近 + 中指/无名指/小指伸直
    dist_thumb_index = np.hypot(thumb_tip[0] - index_tip[0], thumb_tip[1] - index_tip[1])
    palm_size = np.hypot(landmarks[5][0] - wrist[0], landmarks[5][1] - wrist[1])
    if dist_thumb_index < palm_size * 0.3:
        if (landmarks[12][1] < landmarks[10][1] - 0.02 and
            landmarks[16][1] < landmarks[14][1] - 0.02 and
            landmarks[20][1] < landmarks[18][1] - 0.02):
            return "ok"

    # 拇指单独
    if n == 1:
        if index_tip[1] > index_pip[1] + 0.02:
            if thumb_tip[1] < wrist[1] - 0.05:
                return "thumbs_up"
            elif thumb_tip[1] > wrist[1] + 0.05:
                return "thumbs_down"
            return "thumbs_side"
        else:
            return "one"

    mapping = {0: "fist", 2: "peace", 3: "three", 4: "four", 5: "open_palm"}
    return mapping.get(n, "unknown")


GESTURE_COLORS = {
    "fist": (0, 255, 0), "one": (255, 255, 0), "peace": (0, 255, 255),
    "three": (255, 0, 255), "four": (255, 128, 0), "open_palm": (255, 255, 255),
    "thumbs_up": (0, 0, 255), "thumbs_down": (128, 0, 255), "ok": (0, 165, 255),
    "unknown": (128, 128, 128),
}
GESTURE_CN = {
    "fist": "拳头", "one": "一指", "peace": "剪刀", "three": "三指",
    "four": "四指", "open_palm": "张开手掌", "thumbs_up": "点赞",
    "thumbs_down": "踩", "ok": "OK", "unknown": "未识别",
}


# ============================================================
# 3. 主循环
# ============================================================

def main():
    if not (USE_MEDIAPIPE or USE_OPENCV_HAND):
        print("❌ 没有可用的手部检测后端, 请装 mediapipe 或 opencv-contrib-python")
        return

    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true', help='黑色背景 + 手势色块')
    parser.add_argument('--no-show', action='store_true', help='无显示 (headless)')
    parser.add_argument('--camera', type=int, default=0, help='摄像头编号')
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"❌ 摄像头 {args.camera} 打不开")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    backend = "MediaPipe" if USE_MEDIAPIPE else "OpenCV HandDetector"
    print(f"🤚 手势识别已启动 (后端: {backend})")
    print("   支持:", ", ".join(GESTURE_CN.values()))
    print("   按 q 退出")

    recent = {}  # hand_idx -> [gestures]
    STABLE = 5
    fps_start = time.time()
    fps_frames = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        bg = np.zeros_like(frame) if args.demo else frame.copy()

        # 检测
        detections = detect_landmarks(frame)

        fps_frames += 1
        now = time.time()
        if now - fps_start >= 2.0:
            print(f"   FPS: {fps_frames / (now - fps_start):.1f}", end='\r')
            fps_start = now; fps_frames = 0

        # 每只手手势 + 稳定化
        stable_map = {}
        for idx, (lm, handedness, raw) in enumerate(detections):
            gesture = recognize_gesture(lm)
            buf = recent.setdefault(idx, [])
            buf.append(gesture)
            if len(buf) > STABLE:
                buf.pop(0)
            stable_map[idx] = max(set(buf), key=buf.count)

        draw_overlay(bg, frame, detections, stable_map)

        # 状态
        status = "✋ 检测到手" if detections else "🔍 等待手势..."
        cv2.putText(
            bg, status, (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA,
        )
        if detections:
            flat = [GESTURE_CN.get(g, g) for g in stable_map.values()]
            cv2.putText(
                bg, f"手势: {' | '.join(flat)}", (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA,
            )

        if not args.no_show:
            cv2.imshow('Hand Gesture', bg)

        if cv2.waitKey(10) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    if hands:
        hands.close()
    print("\n👋 已退出")


if __name__ == '__main__':
    main()
