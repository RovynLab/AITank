# 导入所需的python包
import numpy as np
import imutils
import cv2

# 定义绿色物体（即球）的HSV颜色空间上下界限，过滤颜色范围，并初始化追踪点的列表

#蓝色
#colorLower = (100, 100, 100)
#colorUpper = (124, 255, 255)

#红色
#colorLower = (156, 100, 100)
#colorUpper = (180, 255, 255)

#绿色
colorLower = (35, 100, 100)
colorUpper = (77, 255, 255)

camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)



while True:  # 保持循环
    (grabbed, frame) = camera.read()  # 抓取当前帧
    (H, W) = frame.shape[:2]  # 计算帧的中心点坐标以保持对物体的追踪
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)  # 将色彩从RGB颜色空间转为HSV颜色空间

    # 为绿色空间创建一个蒙版mask，然后进行一系列扩张和腐蚀，以去除mask中残留的任何小斑点
    mask = cv2.inRange(hsv, colorLower, colorUpper)
    cv2.imshow("mask", mask)
    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)

    # 在蒙版mask中找到轮廓并初始化球的当前中心坐标(x,y)
    cnts = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL,
                            cv2.CHAIN_APPROX_SIMPLE)[-2]
    center = None

    if len(cnts) > 0:  # 只有在至少找到一个轮廓时才能继续
        # 找到蒙版mask中最大的轮廓线，然后用它来计算最小包围圆和质心
        c = max(cnts, key=cv2.contourArea)  # 求连续区域内最大的块
        # 最小的外包圆包住颜色块，圆心xy单位是像素，radius为半径，需注意y往下为正
        ((x, y), radius) = cv2.minEnclosingCircle(c)
        M = cv2.moments(c)
        center = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))

        # 仅当半径满足最小尺寸时才继续
        if radius > 10:
            # 在帧上绘制圆和质心
            cv2.circle(frame, (int(x), int(y)), int(radius),
                       (0, 255, 255), 2)  # 在帧上画圆
            cv2.circle(frame, center, 5, (0, 0, 255), -1)

    # 将帧显示在屏幕上
    cv2.imshow("Frame", frame)
    key = cv2.waitKey(1) & 0xFF

    # 若按下q键，停止循环
    if key == ord("q"):
        break

# 释放摄像机并关闭所有打开的摄像窗口
camera.release()
cv2.destroyAllWindows()
