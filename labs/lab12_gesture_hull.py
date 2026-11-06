# -*- coding: utf-8 -*-
"""
Lab 12 —— 手势识别 (凸包缺陷法, 纯 OpenCV)
==========================================
不依赖 MediaPipe: 肤色分割 → 最大轮廓 → 凸包缺陷数指缝 → 手势类别。
作为算法教学示例保留; 面板里的「手势识别」走 MediaPipe
(见 petcar/drivers/gesture.py), 精度更高。

局限: 手指并齐等高时凸包会把多个指缝合并成一个, 适合手指张开/有间隙的手势;
肤色分割也容易把脸一起框进来, 课堂演示时尽量让手靠近镜头。

运行:
    python3 lab12_gesture_hull.py              # 默认摄像头 0
    python3 lab12_gesture_hull.py --camera 1
按 q 退出。无显示器环境自动跳过 imshow, 只在终端打印结果。
"""
import argparse
import math

import cv2
import numpy as np

GESTURE_TEXT = {
    "fist": "FIST", "one": "ONE", "peace": "PEACE",
    "three": "THREE", "four": "FOUR", "open": "OPEN PALM",
}


def skin_mask(frame):
    """YCrCb 肤色分割 + 去暗部 + 形态学去噪"""
    ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
    mask = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mask = cv2.bitwise_and(mask, cv2.inRange(gray, 40, 255))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)
    return cv2.GaussianBlur(mask, (5, 5), 0)


def solidity(contour):
    """实心度 = 轮廓面积 / 凸包面积, 拳头≈0.95, 张开手掌≈0.7"""
    hull_area = cv2.contourArea(cv2.convexHull(contour))
    return cv2.contourArea(contour) / hull_area if hull_area > 1 else 0.0


def count_gaps(contour):
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
    # OpenCV 4 返回 (N,1,4), OpenCV 5 返回 (N,4), 统一成行
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


def classify(contour):
    """指缝数 + 实心度 → 手势 (0 指缝时用实心度区分拳头/一指)"""
    sol = solidity(contour)
    gaps = count_gaps(contour)
    if gaps <= 0:
        return ("fist" if sol > 0.90 else "one"), sol
    return {1: "peace", 2: "three", 3: "four"}.get(gaps, "open"), sol


def detect(frame):
    """返回 [(x, y, w, h, solidity, text), ...]"""
    h, w = frame.shape[:2]
    cnts, _ = cv2.findContours(skin_mask(frame), cv2.RETR_EXTERNAL,
                               cv2.CHAIN_APPROX_SIMPLE)
    cnts = [c for c in cnts if cv2.contourArea(c) >= 0.02 * w * h]
    if not cnts:
        return []
    c = max(cnts, key=cv2.contourArea)
    gesture, sol = classify(c)
    x, y, bw, bh = cv2.boundingRect(c)
    return [(x, y, bw, bh, sol, GESTURE_TEXT.get(gesture, "UNKNOWN"))]


def main():
    parser = argparse.ArgumentParser(description="Lab12 凸包缺陷手势识别")
    parser.add_argument("--camera", type=int, default=0, help="摄像头编号")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"❌ 摄像头 {args.camera} 打不开")
        return

    try:
        cv2.namedWindow("Lab12 Gesture (Hull)")
        has_gui = True
    except cv2.error:
        has_gui = False
        print("ℹ️  headless OpenCV, 只在终端打印结果")

    print("🤚 凸包法手势识别启动 (按 q 退出)")
    last = None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)

        hands = detect(frame)
        text = None
        for (x, y, w, h, score, text) in hands:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 200), 2)
            cv2.putText(frame, f"{text} {score:.2f}", (x, max(12, y - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 200), 1)

        if text != last:
            print(f"  手势: {text or '等待手势...'}")
            last = text

        if has_gui:
            cv2.imshow("Lab12 Gesture (Hull)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        elif cv2.waitKey(1) & 0xFF == ord("q"):   # 有些后端没有窗口也能收键
            break

    cap.release()
    if has_gui:
        cv2.destroyAllWindows()
    print("👋 已退出")


if __name__ == "__main__":
    main()
