from collections import deque
import numpy as np
import argparse
import imutils
import cv2
import PTZControl as PTZ
import math
import  MecanumChasis as Mecan
import time


_R_MIN = 50         # 小球的半径阈值
_SpeedChase = 50    # 小车追小球的速度

#目标追踪算法函数(x,y) 为目标坐标，width，height为图像长宽像素值,r为识别出来的小球的半径
def tracking(x,y,width,height, r):
    #global PTZ._HorCurrent   #水平舵机的当前角度
    # 目标坐标为 (x,y) 
    # 求出 屏幕 中心点 坐标 (Ox, Oy)
    Ox =  width / 2
    Oy =  height / 2

    # 找出 目标对屏幕中心点的偏离 deltaX，deltaY
    deltaX = width / 2 - x
    deltaY = height / 2 - y
   
    # 当目标位于 视频中心 长宽各一半区域内，云台不追踪。小车向前追踪小球
    if abs(deltaX) < width/4 and abs(deltaY) < height/4: 
        # 如果 r 小于 _R_MIN，则说明 车距离小球 比较大，控制底盘向小球方向运动
        if PTZ._HorCurrent > 80 and PTZ._HorCurrent < 100 and r < _R_MIN:
            Mecan.forward()
            time.sleep(0.05)
            Mecan.stop()
        return
    
    # 当发现目标偏离中心，则控制云台转动，每次转动3度，直到对准目标
    if deltaX > 0:
        PTZ.HorIncrease(-3)

    if deltaX < 0:
        PTZ.HorIncrease(3)

    if deltaY > 0:
        PTZ.VerIncrease(-3)

    if deltaY < 0:
        PTZ.VerIncrease(3)

# define the lower and upper boundaries of the "yellow object"
# (or "ball") in the HSV color space, then initialize the
# list of tracked points

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

# 初始化云台
PTZ.PTZInit()
Mecan.setSpeed(_SpeedChase)
# keep looping
while True:
    # grab the current frame
    (grabbed, frame) = camera.read()

    # calculate the center of the frame as this is where we will
    # try to keep the object
    (H, W) = frame.shape[:2]
    # resize the frame, inverted ("vertical flip" w/ 180degrees),
    # blur it, and convert it to the HSV color space
    #frame = imutils.rotate(frame, angle=180)
    # blurred = cv2.GaussianBlur(frame, (11, 11), 0)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)  # rgb 2 hsv

    # construct a mask for the color "green", then perform
    # a series of dilations and erosions to remove any small
    # blobs left in the mask
    mask = cv2.inRange(hsv, colorLower, colorUpper)
    cv2.imshow("hsv", mask)
    mask = cv2.erode(mask, None, iterations=2)
    mask = cv2.dilate(mask, None, iterations=2)

    # find contours in the mask and initialize the current
    # (x, y) center of the ball
    cnts = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL,
                            cv2.CHAIN_APPROX_SIMPLE)[-2]  # 找出连续区域
    center = None

    # only proceed if at least one contour was found
    if len(cnts) > 0:
        # find the largest contour in the mask, then use
        # it to compute the minimum enclosing circle and
        # centroid
        c = max(cnts, key=cv2.contourArea)  # 求连续区域内最大的块
        ((x, y), radius) = cv2.minEnclosingCircle(
            c)  # 最小的外包圆包住颜色块 圆心xy单位像素，半径 y往下为正
        M = cv2.moments(c)
        center = (int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"]))

        # tracking the target
        tracking(x,y,W,H,radius )
        
        # only proceed if the radius meets a minimum size
        if radius > 10:
            # draw the circle and centroid on the frame,
            # then update the list of tracked points
            cv2.circle(frame, (int(x), int(y)), int(radius), (0, 255, 255), 2)  # 在frame上画圆
            cv2.circle(frame, center, 5, (0, 0, 255), -1)
        
        # 从图像中点到目标中点，绘制一条直线
        cv2.line(frame, (int(W/2),int(H/2)), (int(x),int(y)), (0, 0, 255), 3)
        
    cv2.circle(frame,(int(W/2),int(H/2)),_R_MIN,(0, 0, 255))
    cv2.line(frame, (int(W/4),int(H/4)), (int(W*3/4),int(H/4)), (0, 0, 255))
    cv2.line(frame, (int(W*3/4),int(H/4)), (int(W*3/4),int(H*3/4)), (0, 0, 255))
    cv2.line(frame, (int(W*3/4),int(H*3/4)), (int(W*1/4),int(H*3/4)), (0, 0, 255))
    cv2.line(frame, (int(W*1/4),int(H*3/4)), (int(W/4),int(H/4)), (0, 0, 255))
    # show the frame to our screen
    cv2.imshow("Frame", frame)
    key = cv2.waitKey(1) & 0xFF

    # if the 'q' key is pressed, stop the loop
    if key == ord("q"):
        break

# cleanup the camera and close any open windows
camera.release()
cv2.destroyAllWindows()
