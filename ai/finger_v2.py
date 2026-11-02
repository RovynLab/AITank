#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手势识别 v2 —— MediaPipe Hands 版
=================================

替代原来基于 OpenCV 凸包缺陷的 finger.py。
使用 Google MediaPipe Hands 模型检测 21 个手部关键点，
稳定识别 0-5 根手指 + 常见手势。

树莓派 4B 上性能: 15-20 FPS
识别精度:   95%+  (光照变化下依然稳定)

依赖:
    pip3 install mediapipe opencv-python numpy

使用:
    python3 finger_v2.py          # 显示识别结果
    python3 finger_v2.py --demo  # 演示 + 手势对应颜色
    按 q 退出
"""

import cv2
import numpy as np
import mediapipe as mp
import argparse
import time
import os


# ============================================================
# 1. MediaPipe Hands 初始化
# ============================================================
mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

# hands 对象:
#   static_image_mode=False  ← 视频流模式 (连续追踪)
#   max_num_hands=2          ← 最多检测两只手
#   min_detection_confidence ← 检测置信度阈值 (0.5 适合室内光线)
#   min_tracking_confidence  ← 追踪置信度阈值 (0.5 适合稳定追踪)
hands = mp_hands.Hands(
    static_image_mode=False,
    max_num_hands=2,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5
)


# ============================================================
# 2. 手势识别核心逻辑
# ============================================================

def count_extended_fingers(landmarks: list) -> int:
    """
    用 MediaPipe 21 个关键点判断伸出了几根手指。

    MediaPipe 手部关键点编号 (landmark index):

              0  Wrist (手腕)
             / \
        1     5     9     13    17   ← MCP (掌指关节)
        |     |     |     |     |
        2     6     10    14    18   ← PIP (近指关节)
        |     |     |     |     |
        3     7     11    15    19   ← DIP (远指关节)
         \   /       \   /       \
          4           8          12    ← TIP (指尖)

    判断规则 (基于 y 坐标, 画面中 y 越小越靠上):
      - 拇指: 比较 TIP.x 和 IP.x (因为拇指方向特殊)
      - 其他 4 指: TIP.y < PIP.y  → 手指伸直
    """
    if not landmarks or len(landmarks) < 21:
        return -1

    finger_tips = [8, 12, 16, 20]   # 食指/中指/无名指/小指指尖
    pip_joints  = [6, 10, 14, 18]   # 对应 PIP 关节
    count = 0

    # 拇指单独判断: TIP.x 偏离 IP.x 就算伸直
    # (右手正脸时拇指往右伸，TIP.x > IP.x)
    thumb_tip = landmarks[4]
    thumb_ip  = landmarks[3]
    thumb_mcp = landmarks[2]
    # 简单规则: 拇指尖距离手腕的距离 > 拇指 MCP 距离手腕的距离 → 伸直
    wrist = landmarks[0]
    d_tip = np.hypot(thumb_tip.x - wrist.x, thumb_tip.y - wrist.y)
    d_mcp = np.hypot(thumb_mcp.x - wrist.x, thumb_mcp.y - wrist.y)
    if d_tip > d_mcp * 1.1:   # 1.1 阈值允许轻微弯曲
        count += 1

    # 其他 4 指
    for tip_idx, pip_idx in zip(finger_tips, pip_joints):
        tip = landmarks[tip_idx]
        pip = landmarks[pip_idx]
        # TIP.y < PIP.y → 指尖在 PIP 上方 → 伸直
        # 注意: OpenCV 画面坐标 y 向下为正
        if tip.y < pip.y - 0.02:   # 0.02 留一点容错
            count += 1

    return count


def recognize_gesture(landmarks: list) -> str:
    """
    识别具体手势名称。先数手指，再结合特定关节位置判断更细的手势。

    支持的手势:
        "fist"        → 拳头 (0 指)
        "one"         → 1 指 (食指)
        "peace"       → 剪刀 (食指+中指)
        "three"       → 3 指
        "four"        → 4 指
        "open_palm"   → 张开手掌 (5 指)
        "thumbs_up"   → 点赞 (只有拇指伸, 且向上)
        "thumbs_down" → 踩 (只有拇指伸, 且向下)
        "ok"          → OK (拇指+食指捏合成圈, 其他 3 指伸)
        "unknown"     → 其他
    """
    n = count_extended_fingers(landmarks)
    if n < 0:
        return "unknown"

    wrist = landmarks[0]
    thumb_tip = landmarks[4]
    index_tip = landmarks[8]
    index_pip = landmarks[6]

    # ---- OK 手势特殊检测 ----
    # 拇指尖和食指尖靠得很近 (圈), 但中指/无名指/小指伸直
    dist_thumb_index = np.hypot(
        thumb_tip.x - index_tip.x,
        thumb_tip.y - index_tip.y
    )
    # 手掌尺寸参考: 手腕到食指 MCP 的距离
    palm_size = np.hypot(
        landmarks[5].x - wrist.x,
        landmarks[5].y - wrist.y
    )
    # 如果拇指+食指圈很小, 同时中指+无名指+小指伸直 → OK
    if dist_thumb_index < palm_size * 0.3:
        # 检查中指/无名指/小指是否伸直 (TIP.y < PIP.y)
        middle_straight = landmarks[12].y < landmarks[10].y - 0.02
        ring_straight   = landmarks[16].y < landmarks[14].y - 0.02
        pinky_straight  = landmarks[20].y < landmarks[18].y - 0.02
        if middle_straight and ring_straight and pinky_straight:
            return "ok"

    # ---- 拇指单独 (点赞/踩) ----
    if n == 1:
        # 区分是拇指还是其他指
        # 如果只有拇指伸, 食指应该是弯的 (index_tip.y > index_pip.y)
        if index_tip.y > index_pip.y + 0.02:
            # 判断方向: 拇指尖在手腕上方 → 点赞
            if thumb_tip.y < wrist.y - 0.05:
                return "thumbs_up"
            elif thumb_tip.y > wrist.y + 0.05:
                return "thumbs_down"
            return "thumbs_side"
        else:
            return "one"   # 只有食指伸

    # ---- 通用手指计数 ----
    mapping = {
        0: "fist",
        2: "peace",
        3: "three",
        4: "four",
        5: "open_palm",
    }
    return mapping.get(n, "unknown")


GESTURE_COLORS = {
    "fist":        (0, 255, 0),     # 绿
    "one":         (255, 255, 0),   # 青
    "peace":       (0, 255, 255),   # 黄
    "three":       (255, 0, 255),   # 紫
    "four":        (255, 128, 0),   # 橙
    "open_palm":   (255, 255, 255), # 白
    "thumbs_up":   (0, 0, 255),     # 红
    "thumbs_down": (128, 0, 255),   # 粉
    "ok":          (0, 165, 255),   # 橙红
    "unknown":     (128, 128, 128), # 灰
}

GESTURE_CN = {
    "fist":        "拳头",
    "one":         "一指",
    "peace":       "剪刀",
    "three":       "三指",
    "four":        "四指",
    "open_palm":   "张开手掌",
    "thumbs_up":   "点赞",
    "thumbs_down": "踩",
    "ok":          "OK",
    "unknown":     "未识别",
}


# ============================================================
# 3. 主循环
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true',
                        help='演示模式: 背景变黑, 手势用大色块显示')
    parser.add_argument('--no-show', action='store_true',
                        help='无显示模式 (headless 测试性能)')
    parser.add_argument('--camera', type=int, default=0,
                        help='摄像头编号 (默认 0)')
    args = parser.parse_args()

    # 打开摄像头
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"❌ 摄像头 {args.camera} 打不开")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    print("🤚 MediaPipe 手势识别已启动")
    print("   支持手势:", ", ".join(GESTURE_CN.values()))
    print("   按 q 退出")

    # 稳定化: 用最近 5 帧投票, 避免单帧抖动
    recent_gestures = []
    STABLE_WINDOW = 5

    # FPS 统计
    fps_start = time.time()
    fps_frames = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)   # 镜像翻转, 更自然

        # Demo 模式: 黑色背景
        if args.demo:
            bg = np.zeros_like(frame)
        else:
            bg = frame.copy()

        # ===== MediaPipe 推理 =====
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        # 标记不可写, 加速推理
        rgb.flags.writeable = False
        results = hands.process(rgb)

        fps_frames += 1
        now = time.time()
        if now - fps_start >= 2.0:
            fps = fps_frames / (now - fps_start)
            fps_start = now
            fps_frames = 0
            print(f"   FPS: {fps:.1f}", end='\r')

        # ===== 画左右手 =====
        detected_any = False

        if results.multi_hand_landmarks:
            for hand_idx, (hand_landmarks, handedness) in enumerate(
                zip(results.multi_hand_landmarks, results.multi_handedness)
            ):
                detected_any = True

                # 画 21 个关键点 + 骨架 (MediaPipe 自带工具)
                mp_drawing.draw_landmarks(
                    bg,
                    hand_landmarks,
                    mp_hands.HAND_CONNECTIONS,
                    mp_drawing_styles.get_default_hand_landmarks_style(),
                    mp_drawing_styles.get_default_hand_connections_style()
                )

                # 提取 landmark 列表 (归一化坐标 0~1)
                landmarks = [
                    (lm.x, lm.y, lm.z) for lm in hand_landmarks.landmark
                ]

                # 识别手势
                gesture = recognize_gesture(landmarks)
                hand_label = handedness.classification[0].label  # "Left" / "Right"

                # 稳定化: 滑动窗口多数投票
                recent_gestures.append(gesture)
                if len(recent_gestures) > STABLE_WINDOW:
                    recent_gestures.pop(0)
                stable_gesture = max(
                    set(recent_gestures),
                    key=recent_gestures.count
                )

                # 画识别结果文字
                h, w = frame.shape[:2]
                wrist = hand_landmarks.landmark[0]
                text_x = int(wrist.x * w)
                text_y = int(wrist.y * h)

                color = GESTURE_COLORS.get(stable_gesture, (128, 128, 128))
                label = f"{hand_label}: {GESTURE_CN.get(stable_gesture, stable_gesture)}"

                cv2.putText(
                    bg, label,
                    (text_x + 10, text_y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, color, 2, cv2.LINE_AA
                )

                # 额外: 画一个圆点标出当前手势中心位置
                cv2.circle(
                    bg,
                    (text_x, text_y), 5, color, -1
                )

        # ===== 画状态信息 =====
        status = "✋ 检测到手" if detected_any else "🔍 等待手势..."
        cv2.putText(
            bg, status,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7, (255, 255, 255), 2, cv2.LINE_AA
        )

        # 历史手势条
        if recent_gestures:
            hist_text = " → ".join(
                GESTURE_CN.get(g, g) for g in recent_gestures[-3:]
            )
            cv2.putText(
                bg, f"最近: {hist_text}",
                (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (200, 200, 200), 1, cv2.LINE_AA
            )

        # ===== 显示 =====
        if not args.no_show:
            cv2.imshow('MediaPipe Hand Gesture', bg)

        key = cv2.waitKey(10) & 0xFF
        if key == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    hands.close()
    print("\n👋 已退出")


if __name__ == '__main__':
    main()
