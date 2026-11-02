# -*- coding: utf-8 -*-
#!/usr/bin/python

import sys, os
# 向上搜索 deps/ 目录, 兼容 labs/ 和 demos/*/ 两层结构
_here = os.path.dirname(os.path.abspath(__file__))
for _up in (1, 2, 3):
    _d = os.path.join(_here, '..' * _up, 'deps')
    if os.path.isdir(_d):
        if _d not in sys.path:
            sys.path.insert(0, _d)
        break
from Adafruit_MotorHAT import Adafruit_MotorHAT, Adafruit_DCMotor
import time
import atexit
import math
from getkey import getkey, keys

######################################
###      各变量对应关系
###     
###     _m2    \---------/  _m1   
###     _spd2   |       |   _spd1
###     _dir2   |       |   _dir1
###             |       |
###             |  _mh  |
###     _m3     |       |    _m4
###     _spd3   |       |    _spd4 
###     _dir3  /---------\   _dir4
######################################
_mh = Adafruit_MotorHAT(addr=0x60)        ### 初始化电机扩展板与I2C地址 为0x60

# 下面四行代码，定义了主板四个口，与四个电机的接线关系。需要按实物修改。
_m1 = _mh.getMotor(1)
_m2 = _mh.getMotor(2)
_m3 = _mh.getMotor(3)  
_m4 = _mh.getMotor(4) 

_dir1 = _dir2 = _dir3 = _dir4 = Adafruit_MotorHAT.FORWARD    #四个车轮转动方向
_spd1 = _spd2 = _spd3 = _spd4 = 0                            #四个车轮转速
_normalSpeed = 150                                        #定义一个速度常量

def MCInit():
    _mh = Adafruit_MotorHAT(addr=0x60)
    stop()
    
def setSpeed(spd):
    global _normalSpeed
    _normalSpeed = spd
    
### 小车运行的执行函数
def run():

    _m1.run(_dir1)
    _m1.setSpeed(_spd1)

    _m2.run(_dir2)
    _m2.setSpeed(_spd2)

    _m3.run(_dir3)
    _m3.setSpeed(_spd3)

    _m4.run(_dir4)
    _m4.setSpeed(_spd4)
    # 注意: run() 不再 sleep, 电机指令立即生效. 如需延时由调用方负责

### 关闭motor
def turnOffMotors():
    _m1.run(Adafruit_MotorHAT.RELEASE)
    _m2.run(Adafruit_MotorHAT.RELEASE)
    _m3.run(Adafruit_MotorHAT.RELEASE)
    _m4.run(Adafruit_MotorHAT.RELEASE)

### 用键盘控制小车运动
def keyctrl():
    while True:
        print("input small keyboard '1-9' keys, arrow key 'LEFT or RIGHT, 'q' for exit")
        key = getkey()
        if key == '8':               # 小键盘 8
            forward()
        elif key == '2':             # 小键盘 2
            backward()
        elif key == '4':
            leftSlide()
        elif key == '6':
            rightSlide()
        elif key == '7':
            forwardLeft()
        elif key == '9':
            forwardRight()
        elif key == '1':
            rotateCounterClockwise()
        elif key == '3':
            rotateClockwise()
        elif key == '5':
            stop()
        elif key == keys.LEFT:       # 方向键左
            turnLeft()
        elif key == keys.RIGHT:      # 方向键右
            turnRight()
        elif key == 'q':             # 终止循环，退出程序
            turnOffMotors()
            break
        else:
            time.sleep(0.05)

### 小车向前运动
def forward():
    global _spd1
    global _spd2
    global _spd3
    global _spd4
    global _dir1
    global _dir2
    global _dir3
    global _dir4
    _spd2 = _normalSpeed
    _spd3 = _normalSpeed
    _spd1 = _normalSpeed
    _spd4 = _normalSpeed
    _dir2 = Adafruit_MotorHAT.FORWARD
    _dir3 = Adafruit_MotorHAT.FORWARD
    _dir1 = Adafruit_MotorHAT.FORWARD
    _dir4 = Adafruit_MotorHAT.FORWARD
    run()

### 小车后退
def backward():
    global _spd1
    global _spd2
    global _spd3
    global _spd4
    global _dir1
    global _dir2
    global _dir3
    global _dir4
    _spd2 = _normalSpeed
    _spd3 = _normalSpeed
    _spd1 = _normalSpeed
    _spd4 = _normalSpeed
    _dir2 = Adafruit_MotorHAT.BACKWARD
    _dir3 = Adafruit_MotorHAT.BACKWARD
    _dir1 = Adafruit_MotorHAT.BACKWARD
    _dir4 = Adafruit_MotorHAT.BACKWARD
    run()

### 向左平移
def leftSlide():
    global _spd1
    global _spd2
    global _spd3
    global _spd4
    global _dir1
    global _dir2
    global _dir3
    global _dir4
    _spd2 = _normalSpeed
    _spd3 = _normalSpeed
    _spd1 = _normalSpeed
    _spd4 = _normalSpeed
    _dir2 = Adafruit_MotorHAT.BACKWARD
    _dir3 = Adafruit_MotorHAT.FORWARD
    _dir1 = Adafruit_MotorHAT.FORWARD
    _dir4 = Adafruit_MotorHAT.BACKWARD
    run()

### 向右平移
def rightSlide():
    global _spd1
    global _spd2
    global _spd3
    global _spd4
    global _dir1
    global _dir2
    global _dir3
    global _dir4
    _spd2 = _normalSpeed
    _spd3 = _normalSpeed
    _spd1 = _normalSpeed
    _spd4 = _normalSpeed
    _dir2 = Adafruit_MotorHAT.FORWARD
    _dir3 = Adafruit_MotorHAT.BACKWARD
    _dir1 = Adafruit_MotorHAT.BACKWARD
    _dir4 = Adafruit_MotorHAT.FORWARD
    run()

### 向左转
def turnLeft():
    global _spd1
    global _spd2
    global _spd3
    global _spd4
    global _dir1
    global _dir2
    global _dir3
    global _dir4    
    _spd2 = _normalSpeed
    _spd3 = _normalSpeed
    _spd1 = _normalSpeed
    _spd4 = _normalSpeed
    _dir2 = Adafruit_MotorHAT.BACKWARD
    _dir3 = Adafruit_MotorHAT.BACKWARD
    _dir1 = Adafruit_MotorHAT.FORWARD
    _dir4 = Adafruit_MotorHAT.FORWARD
    run() 

### 向右转
def turnRight():
    global _spd1
    global _spd2
    global _spd3
    global _spd4
    global _dir1
    global _dir2
    global _dir3
    global _dir4
    _spd2 = _normalSpeed
    _spd3 = _normalSpeed
    _spd1 = _normalSpeed
    _spd4 = _normalSpeed
    _dir2 = Adafruit_MotorHAT.FORWARD
    _dir3 = Adafruit_MotorHAT.FORWARD
    _dir1 = Adafruit_MotorHAT.BACKWARD
    _dir4 = Adafruit_MotorHAT.BACKWARD
    run() 

### 向左前运动
def forwardLeft():
    global _spd1
    global _spd2
    global _spd3
    global _spd4
    global _dir1
    global _dir2
    global _dir3
    global _dir4
    _spd2 = 0
    _spd3 = _normalSpeed
    _spd1 = _normalSpeed
    _spd4 = 0
    _dir2 = Adafruit_MotorHAT.FORWARD
    _dir3 = Adafruit_MotorHAT.FORWARD
    _dir1 = Adafruit_MotorHAT.FORWARD
    _dir4 = Adafruit_MotorHAT.FORWARD
    run()

### 向右前运动
def forwardRight():
    global _spd1
    global _spd2
    global _spd3
    global _spd4
    global _dir1
    global _dir2
    global _dir3
    global _dir4
    _spd2 = _normalSpeed
    _spd3 = 0
    _spd1 = 0
    _spd4 = _normalSpeed
    _dir2 = Adafruit_MotorHAT.FORWARD
    _dir3 = Adafruit_MotorHAT.FORWARD
    _dir1 = Adafruit_MotorHAT.FORWARD
    _dir4 = Adafruit_MotorHAT.FORWARD
    run()

### 顺时针旋转
def rotateClockwise():
    global _spd1
    global _spd2
    global _spd3
    global _spd4
    global _dir1
    global _dir2
    global _dir3
    global _dir4
    _spd2 = _normalSpeed
    _spd3 = _normalSpeed
    _spd1 = _normalSpeed
    _spd4 = _normalSpeed
    _dir2 = Adafruit_MotorHAT.FORWARD
    _dir3 = Adafruit_MotorHAT.FORWARD
    _dir1 = Adafruit_MotorHAT.BACKWARD
    _dir4 = Adafruit_MotorHAT.BACKWARD
    run()   

### 逆时针旋转
def rotateCounterClockwise():
    global _spd1
    global _spd2
    global _spd3
    global _spd4
    global _dir1
    global _dir2
    global _dir3
    global _dir4
    _spd2 = _normalSpeed
    _spd3 = _normalSpeed
    _spd1 = _normalSpeed
    _spd4 = _normalSpeed
    _dir2 = Adafruit_MotorHAT.BACKWARD
    _dir3 = Adafruit_MotorHAT.BACKWARD
    _dir1 = Adafruit_MotorHAT.FORWARD
    _dir4 = Adafruit_MotorHAT.FORWARD
    run()  

### 
def backwardLeft():
    global _spd1
    global _spd2
    global _spd3
    global _spd4
    global _dir1
    global _dir2
    global _dir3
    global _dir4
    _spd2 = _normalSpeed
    _spd3 = 0
    _spd1 = 0
    _spd4 = _normalSpeed

    _dir2 = Adafruit_MotorHAT.BACKWARD
    _dir3 = Adafruit_MotorHAT.BACKWARD
    _dir1 = Adafruit_MotorHAT.BACKWARD
    _dir4 = Adafruit_MotorHAT.BACKWARD
    run()

def backwardRight():
    global _spd1
    global _spd2
    global _spd3
    global _spd4
    global _dir1
    global _dir2
    global _dir3
    global _dir4
    _spd2 = 0
    _spd3 = _normalSpeed
    _spd1 = _normalSpeed
    _spd4 = 0
    _dir2 = Adafruit_MotorHAT.BACKWARD
    _dir3 = Adafruit_MotorHAT.BACKWARD
    _dir1 = Adafruit_MotorHAT.BACKWARD
    _dir4 = Adafruit_MotorHAT.BACKWARD
    run()

def stop():
    global _spd1
    global _spd2
    global _spd3
    global _spd4
    _spd2 = 0
    _spd3 = 0
    _spd1 = 0
    _spd4 = 0
    run()

if __name__ == '__main__':
    atexit.register(turnOffMotors)
    keyctrl()

