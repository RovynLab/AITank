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
from Adafruit_MotorHAT.Adafruit_PWM_Servo_Driver import PWM
import time
from getkey import getkey, keys
import threading

_pwm = PWM(0x60,debug = False) # 初始化 MotorHat PWM 
_pwm.setPWMFreq(50)            # 设置 PWM 频率为 50 赫兹


_VerServoNum = 1              # 水平舵机连接在HAT板上的端口号
_HorServoNum = 0               # 垂直舵机连接在HAT板上的端口号

_VerCurrent = 90               # 保存垂直舵机当前角度 (中位)
_HorCurrent = 90               # 保存水平舵机当前角度 (中位)


# 将目标脉冲宽度转为一个周期内的脉冲个数，并驱动硬件发出脉冲。MotorHAT为12位(2^12=4096)精度，最小精度为 周期(毫秒)/4096 
# pulse 脉冲宽度，单位是毫秒
def setServoPulse(channel, pulse):
    pulseLength = 1000000.0                   # 1 秒 1000 * 1000 微秒
    pulseLength /= 50.0                       # 频率位50Hz下，计算每个周期 微秒 数
    pulseLength /= 4096.0                     # pulseLength 得到1个脉冲的脉冲宽度，即单位脉冲宽度
    print("%d us per bit" % pulseLength)
    pulse *= 1000.0                           # pulse：目标脉冲宽度，单位是毫秒，换算为 微秒
    pulse /= (pulseLength*1.0)                # 目标脉冲宽度 / 单位脉冲宽度 = 每周期脉冲个数
    print("pluse: %f  channel： %d" % (pulse, channel)) 
    _pwm.setPWM(channel, 0, int(pulse))
    time.sleep(0.1)

# 在周期20ms下：
#   脉冲宽度           角度    占空比　　　　　　　　 　　　　
#   0.5ms-------------0度；   2.5% 
#   1.0ms------------45度；   5.0% 
#   1.5ms------------90度；   7.5%
#   2.0ms-----------135度；  10.0%
#   2.5ms-----------180度；  12.5%
# 将目标角度转为脉冲宽度并驱动舵机运动
# x 角度
def ServerRotate(servonum,x):
    # y 脉冲宽度 单位是 ms，x 角度 0-180 之间
    # y 需要在 [0.5, 2.5] 区间
    y = x / 90.0 + 0.5
    y = max(y , 0.5)
    y = min(y , 2.5)
    setServoPulse(servonum,y)


# 将水平舵机旋转到固定角度,水平舵机旋转范围为 0 ~ 180
def HorRotate(d):
    global _HorCurrent
    if d < 0:
        d = 0
    if d > 180:
        d = 180
    _HorCurrent = d
    ServerRotate(_HorServoNum,d)
    print("Horizonal rotate to %d " %(_HorCurrent))

# 将垂直舵机旋转到固定角度,转动范围为45~135
def VerRotate(d):
    global _VerCurrent
    if d < 45:
        d = 45
    if d > 135:
        d = 135
    _VerCurrent = d
    ServerRotate(_VerServoNum,d)
    print("Vertical rotate to %d " %(_VerCurrent))

# 垂直舵机转动 delta 度
def VerIncrease(delta = 5):
    global _VerCurrent
    d = _VerCurrent + delta
    if d < 45:
        d = 45
    if d > 135:
        d = 135
    _VerCurrent = d
    ServerRotate(_VerServoNum,d)
    print("Vertical rotate to %d " %(_VerCurrent))

# 水平舵机转动 delta 度
def HorIncrease(delta = 5):
    global _HorCurrent
    d = _HorCurrent + delta
    if d < 0:
        d = 0
    if d > 180:
        d = 180
    _HorCurrent = d
    ServerRotate(_HorServoNum,d)
    print("Horizonal rotate to %d " %(_HorCurrent))

def PTZInit():
    global _pwm
    _pwm = PWM(0x60,debug = False)
    _pwm.setPWMFreq(50)
    HorRotate(90)
    VerRotate(90)

    
# 使用方向键控制云台转动
def keyctrl():

    while True:#making a loop
        key = getkey('input arrow keys, q for exit')
        if key == keys.UP:  
            VerIncrease(5)
        elif key == keys.DOWN:
            VerIncrease(-5)
        elif key == keys.LEFT:
            HorIncrease(5)
        elif key == keys.RIGHT:
            HorIncrease(-5)
        elif key == 'q':
            break
        else:
             pass

if __name__ == '__main__':
    
    #让云台自己转动
    # HorRotate(0)
    # time.sleep(1)
    # HorRotate(180)
    # time.sleep(1)
    # HorRotate(90)
    # time.sleep(1)
    # VerRotate(45)
    # time.sleep(1)
    # VerRotate(135)
    # time.sleep(1)
    # VerRotate(90)
    # time.sleep(1)
    
    PTZInit()
    #方向键控制云台
    keyctrl()



