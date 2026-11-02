#!/usr/bin/python3
# encoding: utf-8

import RPi.GPIO as GPIO                 # 引入GPIO模块
import time                             # 引入time模块

LEDOut = 26

GPIO.setmode(GPIO.BCM)
GPIO.setup(LEDOut, GPIO.OUT)
GPIO.output(LEDOut, GPIO.LOW)
blinks = 0
print('开始闪烁')
while (blinks < 5):
    GPIO.output(LEDOut, GPIO.HIGH)
    time.sleep(1.0)
    GPIO.output(LEDOut, GPIO.LOW)
    time.sleep(1.0)
    blinks = blinks + 1
GPIO.output(LEDOut, GPIO.LOW)
GPIO.cleanup()
print('结束闪烁')