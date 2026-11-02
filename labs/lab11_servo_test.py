#!/usr/bin/env python3
# -*- coding: utf-8 -*-


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

# ===========================================================================
# Example Code
# ===========================================================================

# Initialise the PWM device using the default address
# bmp = PWM(0x40, debug=True)
pwm = PWM(0x60,debug = False)

servoMin = 150  # Min pulse length out of 4096
servoMax = 600  # Max pulse length out of 4096

def setServoPulse(channel, pulse):
  pulseLength = 1000000.0                   # 1,000,000 us per second
  pulseLength /= 50.0                       # 60 Hz
  print("%d us per period" % pulseLength)
  pulseLength /= 4096.0                     # 12 bits of resolution
  print("%d us per bit" % pulseLength)
  pulse *= 1000.0
  pulse /= (pulseLength*1.0)
# pwmV=int(pluse)
  print("pluse: %f  " % (pulse))
  pwm.setPWM(channel, 0, int(pulse))


# Angle to PWM
def write(servonum,x):
  y=x/90.0+0.5
  y=max(y,0.5)
  y=min(y,2.5)
  setServoPulse(servonum,y)

pwm.setPWMFreq(50)                        # Set frequency to 60 Hz

write(0, 0)
time.sleep(1)
write(0,90)
time.sleep(1)
write(0,180)
time.sleep(1)
write(0,90)
time.sleep(1)
write(1, 0)
time.sleep(1)
write(1,90)
time.sleep(1)
write(1,180)
time.sleep(1)
write(1,90)



