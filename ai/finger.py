import cv2
import numpy as np
import copy
import math

# 起始点/总宽度
cap_region_x_begin = 0.5
cap_region_y_end = 0.8
threshold = 60  # 阈值
blurValue = 41  # 高斯模糊参数
bgSubThreshold = 50
learningRate = 0
isBgCaptured = 0   # 布尔值，背景图是否被捕捉
triggerSwitch = False  # 若为真，则键盘模拟器生效

# 打印阈值
def printThreshold(thr):
    print("! Changed threshold to " + str(thr))

# 去除背景
def removeBG(frame):
    fgmask = bgModel.apply(frame, learningRate=learningRate)
    kernel = np.ones((3, 3), np.uint8)
    fgmask = cv2.erode(fgmask, kernel, iterations=1)
    res = cv2.bitwise_and(frame, frame, mask=fgmask)
    return res

# 计算手指数
def calculateFingers(res, drawing):
    # 计算凸度缺陷
    hull = cv2.convexHull(res, returnPoints=False)
    if len(hull) > 3:
        defects = cv2.convexityDefects(res, hull)
        if type(defects) != type(None):  # 防止类型错误

            cnt = 0
            for i in range(defects.shape[0]):  # 计算角度
                s, e, f, d = defects[i][0]
                start = tuple(res[s][0])
                end = tuple(res[e][0])
                far = tuple(res[f][0])
                a = math.sqrt((end[0] - start[0]) ** 2 +
                              (end[1] - start[1]) ** 2)
                b = math.sqrt((far[0] - start[0]) ** 2 +
                              (far[1] - start[1]) ** 2)
                c = math.sqrt((end[0] - far[0]) ** 2 + (end[1] - far[1]) ** 2)
                angle = math.acos((b ** 2 + c ** 2 - a ** 2) /
                                  (2 * b * c))  # cosine函数原理
                if angle <= math.pi / 2:  # 角度小于90度则认为是手指
                    cnt += 1
                    cv2.circle(drawing, far, 8, [211, 84, 0], -1)
            return True, cnt
    return False, 0

# 设置摄像头参数
camera = cv2.VideoCapture(0)
camera.set(10, 200)
cv2.namedWindow('trackbar')
cv2.createTrackbar('trh1', 'trackbar', threshold, 100, printThreshold)

while camera.isOpened():
    ret, frame = camera.read()
    threshold = cv2.getTrackbarPos('trh1', 'trackbar')
    frame = cv2.bilateralFilter(frame, 5, 50, 100)  # 平滑过渡
    frame = cv2.flip(frame, 1)  # 水平翻转帧
    cv2.rectangle(frame, (int(cap_region_x_begin * frame.shape[1]), 0),
                  (frame.shape[1], int(cap_region_y_end * frame.shape[0])), (255, 0, 0), 2)
    cv2.imshow('original', frame)

    #  主要操作
    if isBgCaptured == 1:  # 若背景已捕捉
        img = removeBG(frame)
        img = img[0:int(cap_region_y_end * frame.shape[0]),
                  int(cap_region_x_begin * frame.shape[1]):frame.shape[1]]  # 修剪
        cv2.imshow('mask', img)

        # 二值化图片
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (blurValue, blurValue), 0)
        cv2.imshow('blur', blur)
        ret, thresh = cv2.threshold(blur, threshold, 255, cv2.THRESH_BINARY)
        cv2.imshow('ori', thresh)

        # 得到轮廓
        thresh1 = copy.deepcopy(thresh)
        # OpenCV 3.x 返回 (image, contours, hierarchy), 4.x 返回 (contours, hierarchy)
        # 取倒数第二个元素, 两个版本都兼容
        contours = cv2.findContours(
            thresh1, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)[-2]
        length = len(contours)
        maxArea = -1
        if length > 0:
            for i in range(length):  # 找到区域内的最大轮廓
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
            if triggerSwitch is True:
                if isFinishCal is True and cnt <= 2:
                    print(cnt)

        cv2.imshow('output', drawing)

    # 键盘指令
    k = cv2.waitKey(10)
    if k == 27:  # 按ESC推出
        camera.release()
        cv2.destroyAllWindows()
        break
    elif k == ord('b'):  # 按b键捕捉背景
        bgModel = cv2.createBackgroundSubtractorMOG2(0, bgSubThreshold)
        isBgCaptured = 1
        print('!!!已捕捉背景!!!')
    elif k == ord('r'):  # 按r键重置背景
        bgModel = None
        triggerSwitch = False
        isBgCaptured = 0
        print('!!!背景重置!!!')
    elif k == ord('n'):
        triggerSwitch = True
        print('!!!Trigger On!!!')
