# -*- coding: utf-8 -*-
"""
deps —— 统一底层依赖入口
========================

把 deps/ 目录加到 sys.path, 让下面三个模块能被任何位置的脚本 import:

    from Adafruit_MotorHAT import Adafruit_MotorHAT, Adafruit_DCMotor
    from Adafruit_MotorHAT.Adafruit_PWM_Servo_Driver import PWM

依赖链:
    Adafruit_MotorHAT  →  Adafruit_GPIO.I2C  →  Adafruit_PureIO.smbus

用法:
    # 方式 A (推荐): 在脚本开头 import deps, 然后正常 import 子模块
    import deps
    from Adafruit_MotorHAT import Adafruit_MotorHAT, Adafruit_DCMotor

    # 方式 B: 直接 sys.path 注入 (效果相同, 写在文件顶部)
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'deps'))
    from Adafruit_MotorHAT import ...
"""

import sys
import os

# deps/ 自己就是存放 Adafruit_MotorHAT / Adafruit_GPIO / Adafruit_PureIO 的顶层包目录
# 把它加到 sys.path[0] 让下面的 import 语句能正确解析
_DEPS_DIR = os.path.dirname(os.path.abspath(__file__))
if _DEPS_DIR not in sys.path:
    sys.path.insert(0, _DEPS_DIR)
