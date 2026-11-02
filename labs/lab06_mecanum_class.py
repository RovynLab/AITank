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

class MecanumChasis(object):

    def __init__(self):
        self._mh = Adafruit_MotorHAT(addr=0x60) #主板I2C总线地址，无需修改
        
        # 下面四行代码，定义了主板四个口，与四个电机的接线关系。需要按实物修改。
        self._motorFL = self._mh.getMotor(2)    #Front_Left
        self._motorTL = self._mh.getMotor(3)    #Tail_Left
        self._motorFR = self._mh.getMotor(1)    #Front_Right
        self._motorTR = self._mh.getMotor(4)    #Tail_Right

        self._dirFL = Adafruit_MotorHAT.FORWARD
        self._dirTL = Adafruit_MotorHAT.FORWARD
        self._dirFR = Adafruit_MotorHAT.FORWARD
        self._dirTR = Adafruit_MotorHAT.FORWARD

        self._normalSpeed = 150

    def setSpeed(self, speed):
        """动态设置底盘运动速度 (供综合实验调用)"""
        self._normalSpeed = speed

    def run(self):
        self._motorFL.run(self._dirFL)
        self._motorFL.setSpeed(self._speedFL)

        self._motorTL.run(self._dirTL)
        self._motorTL.setSpeed(self._speedTL)

        self._motorFR.run(self._dirFR)
        self._motorFR.setSpeed(self._speedFR)

        self._motorTR.run(self._dirTR)
        self._motorTR.setSpeed(self._speedTR)
        # 注意: run() 不再 sleep, 电机指令立即生效. 如需延时由调用方负责

    def turnOffMotors(self):
        self._motorFL.run(Adafruit_MotorHAT.RELEASE)
        self._motorTL.run(Adafruit_MotorHAT.RELEASE)
        self._motorFR.run(Adafruit_MotorHAT.RELEASE)
        self._motorTR.run(Adafruit_MotorHAT.RELEASE)


    def keyctrl(self):

        while True:
            print("input small keyboard '1-9' keys,'q' for exit")
            key = getkey()
            if key == '8':
                self.forward()
            elif key == '2':
                self.backward()
            elif key == '4':
                self.leftSlide()
            elif key == '6':
                self.rightSlide()
            elif key == '7':
                self.forwardLeft()
            elif key == '9':
                self.forwardRight()
            elif key == '1':
                self.rotateCounterClockwise()
            elif key == '3':
                self.rotateClockwise()
            elif key == '5':
                self.stop()
            elif key == keys.LEFT:
                self.turnLeft()
            elif key == keys.RIGHT:
                self.turnRight()
            elif key == 'q':
                self.turnOffMotors()
                break
            else:
                time.sleep(0.05)

    def forward(self):
        print("forward")
        self._speedFL = self._normalSpeed
        self._speedTL = self._normalSpeed
        self._speedFR = self._normalSpeed
        self._speedTR = self._normalSpeed
        self._dirFL = Adafruit_MotorHAT.FORWARD
        self._dirTL = Adafruit_MotorHAT.FORWARD
        self._dirFR = Adafruit_MotorHAT.FORWARD
        self._dirTR = Adafruit_MotorHAT.FORWARD
        self.run()
        
    def backward(self):
        self._speedFL = self._normalSpeed
        self._speedTL = self._normalSpeed
        self._speedFR = self._normalSpeed
        self._speedTR = self._normalSpeed
        self._dirFL = Adafruit_MotorHAT.BACKWARD
        self._dirTL = Adafruit_MotorHAT.BACKWARD
        self._dirFR = Adafruit_MotorHAT.BACKWARD
        self._dirTR = Adafruit_MotorHAT.BACKWARD
        self.run()

    def leftSlide(self):
        self._speedFL = self._normalSpeed
        self._speedTL = self._normalSpeed
        self._speedFR = self._normalSpeed
        self._speedTR = self._normalSpeed
        self._dirFL = Adafruit_MotorHAT.BACKWARD
        self._dirTL = Adafruit_MotorHAT.FORWARD
        self._dirFR = Adafruit_MotorHAT.FORWARD
        self._dirTR = Adafruit_MotorHAT.BACKWARD
        self.run()

    def rightSlide(self):
        self._speedFL = self._normalSpeed
        self._speedTL = self._normalSpeed
        self._speedFR = self._normalSpeed
        self._speedTR = self._normalSpeed
        self._dirFL = Adafruit_MotorHAT.FORWARD
        self._dirTL = Adafruit_MotorHAT.BACKWARD
        self._dirFR = Adafruit_MotorHAT.BACKWARD
        self._dirTR = Adafruit_MotorHAT.FORWARD
        self.run()

    def turnLeft(self):
        self._speedFL = self._normalSpeed
        self._speedTL = self._normalSpeed
        self._speedFR = self._normalSpeed
        self._speedTR = self._normalSpeed
        self._dirFL = Adafruit_MotorHAT.BACKWARD
        self._dirTL = Adafruit_MotorHAT.BACKWARD
        self._dirFR = Adafruit_MotorHAT.FORWARD
        self._dirTR = Adafruit_MotorHAT.FORWARD
        self.run() 


    def turnRight(self):
        self._speedFL = self._normalSpeed
        self._speedTL = self._normalSpeed
        self._speedFR = self._normalSpeed
        self._speedTR = self._normalSpeed
        self._dirFL = Adafruit_MotorHAT.FORWARD
        self._dirTL = Adafruit_MotorHAT.FORWARD
        self._dirFR = Adafruit_MotorHAT.BACKWARD
        self._dirTR = Adafruit_MotorHAT.BACKWARD
        self.run() 


    def forwardLeft(self):

        self._speedFL = 0
        self._speedTL = self._normalSpeed
        self._speedFR = self._normalSpeed
        self._speedTR = 0
        self._dirFL = Adafruit_MotorHAT.FORWARD
        self._dirTL = Adafruit_MotorHAT.FORWARD
        self._dirFR = Adafruit_MotorHAT.FORWARD
        self._dirTR = Adafruit_MotorHAT.FORWARD
        self.run()

    def forwardRight(self):
        self._speedFL = self._normalSpeed
        self._speedTL = 0
        self._speedFR = 0
        self._speedTR = self._normalSpeed
        self._dirFL = Adafruit_MotorHAT.FORWARD
        self._dirTL = Adafruit_MotorHAT.FORWARD
        self._dirFR = Adafruit_MotorHAT.FORWARD
        self._dirTR = Adafruit_MotorHAT.FORWARD
        self.run()

    def rotateClockwise(self):
        self._speedFL = self._normalSpeed
        self._speedTL = self._normalSpeed
        self._speedFR = self._normalSpeed
        self._speedTR = self._normalSpeed
        self._dirFL = Adafruit_MotorHAT.FORWARD
        self._dirTL = Adafruit_MotorHAT.FORWARD
        self._dirFR = Adafruit_MotorHAT.BACKWARD
        self._dirTR = Adafruit_MotorHAT.BACKWARD
        self.run()   

    def rotateCounterClockwise(self):
        self._speedFL = self._normalSpeed
        self._speedTL = self._normalSpeed
        self._speedFR = self._normalSpeed
        self._speedTR = self._normalSpeed
        self._dirFL = Adafruit_MotorHAT.BACKWARD
        self._dirTL = Adafruit_MotorHAT.BACKWARD
        self._dirFR = Adafruit_MotorHAT.FORWARD
        self._dirTR = Adafruit_MotorHAT.FORWARD
        self.run()  

    def backwardLeft(self):
        self._speedFL = self._normalSpeed
        self._speedTL = 0
        self._speedFR = 0
        self._speedTR = self._normalSpeed

        self._dirFL = Adafruit_MotorHAT.BACKWARD
        self._dirTL = Adafruit_MotorHAT.BACKWARD
        self._dirFR = Adafruit_MotorHAT.BACKWARD
        self._dirTR = Adafruit_MotorHAT.BACKWARD
        self.run()

    def backwardRight(self):
        self._speedFL = 0
        self._speedTL = self._normalSpeed
        self._speedFR = self._normalSpeed
        self._speedTR = 0
        self._dirFL = Adafruit_MotorHAT.BACKWARD
        self._dirTL = Adafruit_MotorHAT.BACKWARD
        self._dirFR = Adafruit_MotorHAT.BACKWARD
        self._dirTR = Adafruit_MotorHAT.BACKWARD
        self.run()

    def stop(self):
        self._speedFL = 0
        self._speedTL = 0
        self._speedFR = 0
        self._speedTR = 0
        self.run()

def main():
    mecan = MecanumChasis()
    mecan.keyctrl()
    mecan.turnOffMotors()

if __name__ == '__main__':
    main()