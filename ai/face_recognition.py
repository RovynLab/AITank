# -*- coding: utf-8 -*-
"""
人脸识别 (OpenCV 5.0 兼容版)
==============================
OpenCV 5.0 移除了 CascadeClassifier (Haar 级联),
改用 FaceDetectorYN (YuNet 模型, 更准更快)。
首次运行会自动下载 onnx 模型文件到 ~/.opencv/models/。

加 --show 参数才显示 GUI (需要显示器)。
"""
import sys
import os
import numpy as np
import cv2

# ---------- headless 检测 ----------
try:
    cv2.namedWindow("_test_")
    cv2.destroyWindow("_test_")
    HAS_GUI = True
except Exception:
    HAS_GUI = False

# ---------- FaceDetectorYN (OpenCV 5.0 原生) ----------
# YuNet 模型默认在 cv2.data.haarcascades 附近, 如果没有就下载
model_path = os.path.join(os.path.expanduser("~"), ".opencv", "models", "face_detection_yunet_2023mar.onnx")

if not os.path.exists(model_path):
    # 尝试从 OpenCV 自带的路径找
    candidates = [
        os.path.join(cv2.data.haarcascades, "..", "models", "face_detection_yunet_2023mar.onnx"),
        os.path.join(cv2.data.haarcascades, "face_detection_yunet_2023mar.onnx"),
    ]
    for c in candidates:
        if os.path.exists(c):
            model_path = c
            print(f"✅ 模型: {model_path}")
            break
    else:
        # 下载
        print("📥 首次运行, 下载 YuNet 模型...")
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
        try:
            import urllib.request
            urllib.request.urlretrieve(url, model_path)
            print(f"✅ 模型已下载: {model_path}")
        except Exception as e:
            print(f"❌ 模型下载失败: {e}")
            print("   手动下载放到: " + model_path)
            sys.exit(1)

# 创建 YuNet 人脸检测器
face_detector = cv2.FaceDetectorYN_create(
    model=model_path,
    config="",
    input_size=(320, 320),
    score_threshold=0.9,
    nms_threshold=0.3,
    top_k=5000,
)
print("✅ FaceDetectorYN 创建成功 (OpenCV 5.0)")

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

if not cap.isOpened():
    print("❌ 摄像头打不开")
    sys.exit(1)

print("🎥 人脸识别启动 (按 q 退出)")
frame_count = 0

while True:
    ret, img = cap.read()
    if not ret:
        print("⚠️ 帧抓取失败")
        break

    h, w = img.shape[:2]
    face_detector.setInputSize((w, h))

    _, faces = face_detector.detect(img)

    if faces is not None:
        for face in faces:
            # face: [x, y, w, h, score, ...]
            x, y, fw, fh = int(face[0]), int(face[1]), int(face[2]), int(face[3])
            cv2.rectangle(img, (x, y), (x + fw, y + fh), (255, 0, 0), 2)
            cv2.putText(img, f"{face[4]:.2f}", (x, y - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
            cx, cy = x + fw // 2, y + fh // 2
            if not HAS_GUI:
                print(f"  人脸: ({cx}, {cy}), 置信度: {face[4]:.2f}")

    if HAS_GUI:
        cv2.imshow('Face Detection (YuNet)', img)
        k = cv2.waitKey(30) & 0xff
        if k == 27 or k == ord('q'):
            break
    else:
        # headless: 跑 200 帧后退出 (纯功能测试)
        frame_count += 1
        if frame_count % 50 == 0:
            print(f"  已处理 {frame_count} 帧...")
        if frame_count >= 200:
            break

cap.release()
if HAS_GUI:
    cv2.destroyAllWindows()
print(f"\n👋 已退出 (处理 {frame_count} 帧)")
