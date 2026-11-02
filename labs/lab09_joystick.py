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
from exp3_1_2_MecanumChasis import _m1,_m2,_m3,_m4, stop
import exp3_2_kinematic as kin
import math
import time
import atexit
import os

# Bug #4 修复: pygame 无头模式兼容 —— SSH/后台运行时用 dummy 驱动避免崩溃
if os.environ.get('SDL_VIDEODRIVER') is None:
    os.environ['SDL_VIDEODRIVER'] = 'dummy'
try:
    import pygame
except ImportError:
    pygame = None
    print("请先安装 pygame: pip3 install pygame")

_Vx = _Vy = _Vw = 0.0              # 小车的世界坐标系速度，
_rpm1 = _rpm2 = _rpm3 = _rpm4 = 0  # 四个车轮的转速全局变量
_Kxy = 20                          # x y速度系数
_Kw = 30                           # w 角速度系数

# Bug #1 修复: turnOffMotors() 原来引用了不存在的 mh 变量
def turnOffMotors():
    _m1.run(Adafruit_MotorHAT.RELEASE)
    _m2.run(Adafruit_MotorHAT.RELEASE)
    _m3.run(Adafruit_MotorHAT.RELEASE)
    _m4.run(Adafruit_MotorHAT.RELEASE)
    
### 转速归一化
### MotorHAT最大转速值为255，按此对四个车轮转速按255归一处理， 

def RPMNormalize(rpm1,rpm2,rpm3,rpm4):
    maxw = max(abs(rpm1), abs(rpm2), abs(rpm3), abs(rpm4))
        
    if maxw > 255:
        r1 = rpm1 * 255 / maxw
        r2 = rpm2 * 255 / maxw
        r3 = rpm3 * 255 / maxw
        r4 = rpm4 * 255 / maxw
        return r1,r2,r3,r4
    else:
        return rpm1,rpm2,rpm3,rpm4


### 小车运动
def KinRun():
    global _rpm1
    global _rpm2
    global _rpm3
    global _rpm4
    
    if _rpm1 > 0:       
        _m1.run(Adafruit_MotorHAT.FORWARD)
    else:
        _m1.run(Adafruit_MotorHAT.BACKWARD)
    
    if _rpm2 > 0:       
        _m2.run(Adafruit_MotorHAT.FORWARD)
    else:
        _m2.run(Adafruit_MotorHAT.BACKWARD)

    if _rpm3 > 0:       
        _m3.run(Adafruit_MotorHAT.FORWARD)
    else:
        _m3.run(Adafruit_MotorHAT.BACKWARD)

    if _rpm4 > 0:       
        _m4.run(Adafruit_MotorHAT.FORWARD)
    else:
        _m4.run(Adafruit_MotorHAT.BACKWARD)

    #如果速度太低，则让小车停下来
    if abs(_rpm1) < 10:
        _rpm1 = 0

    if abs(_rpm2) < 10:
        _rpm2 = 0

    if abs(_rpm3) < 10:
        _rpm3 = 0

    if abs(_rpm4) < 10:
        _rpm4 = 0

    _m1.setSpeed(int(abs(_rpm1)))
    _m2.setSpeed(int(abs(_rpm2)))
    _m3.setSpeed(int(abs(_rpm3)))
    _m4.setSpeed(int(abs(_rpm4)))


# 更新速度，ax,ay,aw 为手柄轴传来数值
def updateSpeed(ax, ay, aw):
    global _rpm1
    global _rpm2
    global _rpm3
    global _rpm4
    global _Vx
    global _Vy
    global _Vw
    
    #如果放开手柄，则让小车减速停下来
    if(ax == 0 and ay == 0 and aw == 0):
        _Vx /= 2
        _Vy /= 2
        _Vw /= 2
    else:#更新速度值
        _Vx = _Vx + ax * _Kxy
        _Vy = _Vy + ay * _Kxy
        _Vw = _Vw + aw * _Kw
    #调用运动学公式，计算小车四轮速度
    v1, v2, v3, v4 = kin.Kin_Inverse(_Vx, _Vy, _Vw)
    #将小车线速度转为RPM,并归一处理
    _rpm1, _rpm2, _rpm3, _rpm4 = RPMNormalize(kin.vToRPM(v1),kin.vToRPM(v2),kin.vToRPM(v3),kin.vToRPM(v4))
   
    print("_rpm1=%.1f, _rpm2=%.1f, _rpm3=%.1f, _rpm4=%.1f"%( _rpm1, _rpm2, _rpm3, _rpm4))
    
def main():
    # 初始化手柄
    pygame.init()
    pygame.joystick.init()
    
    joystick_count = pygame.joystick.get_count()
    print("Number of joysticks:", joystick_count)
    
    if joystick_count == 0:       
        return
    
    for i in range(joystick_count):
        joystick = pygame.joystick.Joystick(i)
        joystick.init()
    
    while True:
        eventlist = pygame.event.get() # User did something.
        
        #如果x键被按下，退出程序
        button = joystick.get_button(2)
        if button == 1:
            break
        #获取游戏手柄的输出值
        x_axis = joystick.get_axis(0)  # 左摇杆横轴 x值，向右为正
        y_axis = joystick.get_axis(1) * -1 # 左摇杆纵轴 y ，因为手柄向下为正，因此乘以 -1
        w_axis = joystick.get_axis(3) * -1 # 右摇杆横轴，输出角速度w 
        print("x = %.1f,y = %.1f,w = %.1f"%(x_axis,y_axis,w_axis))

        updateSpeed(x_axis, y_axis, w_axis)
        #让车跑起来
        KinRun()
        time.sleep(0.5)
  
    stop()
    pygame.joystick.quit()
    pygame.quit()    

if __name__=="__main__":
    atexit.register(turnOffMotors)
    main()
    
   
