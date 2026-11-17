# -*- coding: utf-8 -*-
"""
drivers/ptz.py — 二自由度云台驱动
=================================
包装原 PTZControl.py，做成类接口。水平舵机(Ch0) 0-180°, 垂直舵机(Ch1) 45-135°。
"""

from __future__ import annotations

import sys
import os
import time
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar import config

try:
    _deps = os.path.join(_ROOT, "deps")
    if _deps not in sys.path:
        sys.path.insert(0, _deps)
    from Adafruit_MotorHAT.Adafruit_PWM_Servo_Driver import PWM
    _HAS_PWM = True
except ImportError:
    _HAS_PWM = False


class PTZDriver:
    """水平 + 垂直 两轴云台"""

    def __init__(self):
        self._lock = threading.Lock()
        self.h_cur = config.SERVO_INIT_H   # 90
        self.v_cur = config.SERVO_INIT_V   # 90

        if _HAS_PWM:
            self._pwm = PWM(config.PCA9685_ADDR, debug=False)
            self._pwm.setPWMFreq(config.PWM_FREQ)  # 50Hz
        else:
            self._pwm = None
            print("[PTZ] Adafruit PWM 库未安装, 云台不可用")

    # ---- 底层: 角度 → 脉冲 ----
    def _set_pulse(self, channel: int, pulse_ms: float):
        """pulse_ms: 0.5 ~ 2.5 ms。调用方须已持有 self._lock。"""
        if self._pwm is None:
            return
        # 0.5ms → 204, 2.5ms → 1024  (12-bit, 20ms 周期)
        pulse_ms = max(0.5, min(2.5, pulse_ms))
        # 50Hz: 每周期 20ms = 4096 tick → 1ms = 204.8 tick
        tick = int(pulse_ms * 204.8)
        self._pwm.setPWM(channel, 0, tick)

    def _angle_to_pulse(self, angle: float) -> float:
        """0-180° → 0.5-2.5ms"""
        return angle / 90.0 + 0.5

    # ---- 锁内核心 (调用方须已持 self._lock, 不要直接调用) ----
    def _h_rotate_locked(self, angle: float):
        angle = max(config.SERVO_H_MIN, min(config.SERVO_H_MAX, angle))
        self.h_cur = angle
        self._set_pulse(config.SERVO_H, self._angle_to_pulse(angle))

    def _v_rotate_locked(self, angle: float):
        angle = max(config.SERVO_V_MIN, min(config.SERVO_V_MAX, angle))
        self.v_cur = angle
        self._set_pulse(config.SERVO_V, self._angle_to_pulse(angle))

    # ---- 绝对角度 (对外) ----
    def h_rotate(self, angle: float):
        """水平转到 angle (0-180)"""
        with self._lock:
            self._h_rotate_locked(angle)

    def v_rotate(self, angle: float):
        """垂直转到 angle (45-135)"""
        with self._lock:
            self._v_rotate_locked(angle)

    # ---- 相对增量 (整个 读-改-写 事务在锁内) ----
    def h_increase(self, delta: float = 5):
        with self._lock:
            self._h_rotate_locked(self.h_cur + delta)

    def v_increase(self, delta: float = 5):
        with self._lock:
            self._v_rotate_locked(self.v_cur + delta)

    # ---- 语义化接口 ----
    def look_left(self, delta: float = 10):    self.h_increase(delta)
    def look_right(self, delta: float = 10):   self.h_increase(-delta)
    def look_up(self, delta: float = 10):      self.v_increase(delta)   # 实测: 垂直轴角度增大=向上
    def look_down(self, delta: float = 10):    self.v_increase(-delta)
    def look_center(self):
        with self._lock:
            self._h_rotate_locked(config.SERVO_INIT_H)
            self._v_rotate_locked(config.SERVO_INIT_V)

    # ---- 初始化 ----
    def init(self):
        self.look_center()
        time.sleep(0.2)


if __name__ == "__main__":
    ptz = PTZDriver()
    ptz.init()
    print("云台初始化中...")
    time.sleep(1)
    ptz.h_rotate(0); time.sleep(0.5)
    ptz.h_rotate(180); time.sleep(0.5)
    ptz.v_rotate(45); time.sleep(0.5)
    ptz.v_rotate(135); time.sleep(0.5)
    ptz.look_center()
    print("Done")
