# -*- coding: utf-8 -*-
"""
简单球追踪 (headless 兼容版)
============================
OpenCV 5.0 / opencv-python-headless 下也能跑，只做追踪不弹窗显示。
加 --show 参数才开启 GUI 显示 (需要有显示器 + GTK)。
"""
import sys
import numpy as np
import cv2
import argparse

# ---------- headless 检测 ----------
# opencv-python-headless 没有 GUI 支持
try:
    cv2.namedWindow("_test_")
    cv2.destroyWindow("_test_")
    HAS_GUI = True
except Exception:
    HAS_GUI = False
    print("ℹ️  headless OpenCV, 无 GUI 显示 (加 --show 参数开启, 需显示器)")

# ---------- HSV 颜色范围 ----------
# 绿色球 (根据实际球颜色调整)
colorLower = (35, 100, 100)
colorUpper = (77, 255, 255)

# ---------- 摄像头 ----------
camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

if not camera.isOpened():
    print("❌ 摄像头打不开")
    sys.exit(1)

print("🎥 球追踪启动 (按 q 退出)")
frame_count = 0

while True:
    (grabbed, frame) = camera.read()
    if not grabbed:
        print("⚠️  帧抓取失败")
        break

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    mask = cv2.inRange(hsv, colorLower, colorUpper)
    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)

    cnts = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL,
                            cv2.CHAIN_APPROX_SIMPLE)[-2]
    center = None

    if len(cnts) > 0:
        c = max(cnts, key=cv2.contourArea)
        ((x, y), radius) = cv2.minEnclosingCircle(c)
        M = cv2.moments(c)
        center = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))

        if radius > 10:
            cv2.circle(frame, (int(x), int(y)), int(radius),
                       (0, 255, 255), 2)
            cv2.circle(frame, center, 5, (0, 0, 255), -1)
            if HAS_GUI:
                print(f"  球位置: ({center[0]}, {center[1]}), 半径: {radius:.0f}")

    # 只在有 GUI 时显示
    if HAS_GUI:
        cv2.imshow("Frame", frame)
        cv2.imshow("mask", mask)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
    else:
        # headless: 纯追踪, 跑 300 帧退出
        frame_count += 1
        if frame_count % 50 == 0:
            print(f"\n  已处理 {frame_count} 帧")
        if frame_count >= 300:
            print(f"\n  headless 完成 ({frame_count} 帧)")
            break

camera.release()
if HAS_GUI:
    cv2.destroyAllWindows()
print("\n👋 已退出")
