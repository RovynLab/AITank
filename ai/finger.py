# -*- coding: utf-8 -*-
"""
手势识别 - 凸包缺陷法 (headless 兼容版)
========================================
纯 OpenCV 实现 (不依赖 mediapipe/HandDetector),
headless 环境下也能跑 (只做计算不弹窗)。

trackbar 阈值从命令行参数传:  python3 finger.py --threshold 60
"""
import sys
import cv2
import numpy as np
import copy
import math
import argparse

# ---------- headless 检测 ----------
try:
    cv2.namedWindow("_test_")
    cv2.destroyWindow("_test_")
    HAS_GUI = True
except Exception:
    HAS_GUI = False
    print("ℹ️  headless OpenCV, 无 GUI 显示")

# ---------- 参数 ----------
parser = argparse.ArgumentParser()
parser.add_argument('--threshold', type=int, default=60, help='二值化阈值 (默认 60)')
parser.add_argument('--no-show', action='store_true', help='强制 headless 模式')
args = parser.parse_args()

cap_region_x_begin = 0.5
cap_region_y_end = 0.8
threshold = args.threshold
blurValue = 41
bgSubThreshold = 50
learningRate = 0
isBgCaptured = 0
triggerSwitch = False

def printThreshold(thr):
    print(f"! 阈值改变为 {thr}")

def removeBG(frame):
    fgmask = bgModel.apply(frame, learningRate=learningRate)
    kernel = np.ones((3, 3), np.uint8)
    fgmask = cv2.erode(fgmask, kernel, iterations=1)
    return cv2.bitwise_and(frame, frame, mask=fgmask)

def calculateFingers(res, drawing):
    hull = cv2.convexHull(res, returnPoints=False)
    if len(hull) > 3:
        defects = cv2.convexityDefects(res, hull)
        if defects is not None:
            cnt = 0
            for i in range(defects.shape[0]):
                s, e, f, d = defects[i][0]
                start = tuple(res[s][0])
                end = tuple(res[e][0])
                far = tuple(res[f][0])
                a = math.sqrt((end[0]-start[0])**2 + (end[1]-start[1])**2)
                b = math.sqrt((far[0]-start[0])**2 + (far[1]-start[1])**2)
                c = math.sqrt((end[0]-far[0])**2 + (end[1]-far[1])**2)
                angle = math.acos((b**2 + c**2 - a**2) / (2*b*c))
                if angle <= math.pi / 2:
                    cnt += 1
                    cv2.circle(drawing, far, 8, [211, 84, 0], -1)
            return True, cnt
    return False, 0

# ---------- 摄像头 ----------
camera = cv2.VideoCapture(0)
camera.set(10, 200)

if not camera.isOpened():
    print("❌ 摄像头打不开")
    sys.exit(1)

# GUI 初始化 (仅在有显示器时)
if HAS_GUI:
    cv2.namedWindow('trackbar')
    cv2.createTrackbar('trh1', 'trackbar', threshold, 100, printThreshold)

print(f"🎥 手势识别启动 (阈值={threshold}, 按 b 捕捉背景, r 重置, q 退出)")
frame_count = 0

while camera.isOpened():
    ret, frame = camera.read()
    threshold = cv2.getTrackbarPos('trh1', 'trackbar') if HAS_GUI else threshold
    frame = cv2.bilateralFilter(frame, 5, 50, 100)
    frame = cv2.flip(frame, 1)

    # 画区域框
    cv2.rectangle(frame, (int(cap_region_x_begin * frame.shape[1]), 0),
                  (frame.shape[1], int(cap_region_y_end * frame.shape[0])), (255, 0, 0), 2)
    if HAS_GUI:
        cv2.imshow('original', frame)

    if isBgCaptured == 1:
        img = removeBG(frame)
        img = img[0:int(cap_region_y_end * frame.shape[0]),
                  int(cap_region_x_begin * frame.shape[1]):frame.shape[1]]

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (blurValue, blurValue), 0)
        ret, thresh = cv2.threshold(blur, threshold, 255, cv2.THRESH_BINARY)

        contours = cv2.findContours(
            thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)[-2]
        length = len(contours)
        maxArea = -1
        if length > 0:
            for i in range(length):
                temp = contours[i]
                area = cv2.contourArea(temp)
                if area > maxArea:
                    maxArea = area
                    ci = i
            res = contours[ci]
            hull = cv2.convexHull(res)
            drawing = np.zeros(img.shape, np.uint8)
            cv2.drawContours(drawing, [res], 0, (0, 255, 0), 2)
            cv2.drawContours(drawing, [hull], 0, (0, 0, 255), 3)
            isFinishCal, cnt = calculateFingers(res, drawing)
            if triggerSwitch:
                if isFinishCal and cnt <= 2:
                    print(f"  手指数: {cnt}")
            elif isFinishCal and not HAS_GUI:
                print(f"  手指数: {cnt}")

        if HAS_GUI:
            cv2.imshow('output', drawing)
            cv2.imshow('mask', img)
            cv2.imshow('blur', blur)
            cv2.imshow('ori', thresh)

    # 键盘指令
    k = cv2.waitKey(10) & 0xFF if HAS_GUI else 0
    if k == 27 or k == ord('q'):
        break
    elif k == ord('b'):
        bgModel = cv2.createBackgroundSubtractorMOG2(0, bgSubThreshold)
        isBgCaptured = 1
        print('✓ 已捕捉背景')
    elif k == ord('r'):
        bgModel = None
        triggerSwitch = False
        isBgCaptured = 0
        print('✓ 背景重置')
    elif k == ord('n'):
        triggerSwitch = True
        print('✓ Trigger On')

    # headless: 自动捕捉背景 + 跑 300 帧退出
    if not HAS_GUI:
        if frame_count == 30:
            bgModel = cv2.createBackgroundSubtractorMOG2(0, bgSubThreshold)
            isBgCaptured = 1
            print('✓ 自动捕捉背景')
        frame_count += 1
        if frame_count >= 300:
            break

camera.release()
if HAS_GUI:
    cv2.destroyAllWindows()
print(f"\n👋 已退出 (处理 {frame_count} 帧)")
