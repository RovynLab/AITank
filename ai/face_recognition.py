import numpy as np
import cv2
# 加载Haar特征分类器，即xml文件，该文件中会描述人体相应部位的Haar特征值，此处包括人脸和眼睛
face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')
eye_cascade = cv2.CascadeClassifier('haarcascade_eye.xml')

cap = cv2.VideoCapture(0)  # 设置摄像头

while 1:
    ret, img = cap.read()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  # 灰度图
    # 检测出图片中所有的人脸，并将人脸用vector保存各个人脸的坐标、大小（用矩形表示）
    # gray：传入图片
    # 1.3: scaleFactor：表示在前后两次相继的扫描中，搜索窗口的比例系数。默认为1.1即每次搜索窗口依次扩大10%
    # 5:minNeighbors：构成检测目标的相邻矩形的最小个数(默认3)，如组成检测目标的小矩形的个数和小于min_neighbors-1都会被排除。
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

    # 在图像中找到面孔后，若能找到人脸，则将检测到的人脸位置返回为Rect(x,y,w,h)
    # 一旦获得这些位置，就可以为面部创建ROI，并在此ROI上进行眼睛检测（因为眼睛始终在脸上）
    for (x, y, w, h) in faces:
        # 为脸画蓝色矩形框，这里的颜色表示为(B, G, R)
        cv2.rectangle(img, (x, y), (x + w, y + h), (255, 0, 0), 2)
        roi_gray = gray[y:y + h, x:x + w]
        roi_color = img[y:y + h, x:x + w]
        print(int(x + w / 2), int(y + h / 2))
        eyes = eye_cascade.detectMultiScale(roi_gray)
        for (ex, ey, ew, eh) in eyes:
                # 为眼睛画绿色矩形框
            cv2.rectangle(roi_color, (ex, ey),
                          (ex + ew, ey + eh), (0, 255, 0), 2)
    cv2.imshow('img', img)  # 显示图像
    k = cv2.waitKey(30) & 0xff
    if k == 27:  # press 'ESC' to quit
        break

cap.release()
cv2.destroyAllWindows()
