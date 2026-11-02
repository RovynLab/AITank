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



def wheeltest():

    print("Front Right")
    _m1.run(Adafruit_MotorHAT.FORWARD)
    _m1.setSpeed(50)
    time.sleep(2)
    _m1.setSpeed(0)
    
    print("Front Left")
    _m2.run(Adafruit_MotorHAT.FORWARD)
    _m2.setSpeed(50)
    time.sleep(2)
    _m2.setSpeed(0)

    print("Trail Left")
    _m3.run(Adafruit_MotorHAT.FORWARD)
    _m3.setSpeed(50)
    time.sleep(2)
    _m3.setSpeed(0)

    print("Trail Right")
    _m4.run(Adafruit_MotorHAT.FORWARD)
    _m4.setSpeed(50)
    time.sleep(2)
    _m4.setSpeed(0)
    
def main():
    wheeltest()
    
if __name__ == '__main__':
    main()

