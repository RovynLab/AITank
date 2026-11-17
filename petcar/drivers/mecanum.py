# -*- coding: utf-8 -*-
"""
drivers/mecanum.py — 麦轮底盘驱动 (包装原 MecanumChasis)
========================================================

把原来一堆全局函数封装成一个 MecanumDriver 类，方便多线程调用。
"""

from __future__ import annotations

import sys
import os
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar import config

# 导入 Adafruit 库
try:
    _deps = os.path.join(_ROOT, "deps")
    if _deps not in sys.path:
        sys.path.insert(0, _deps)
    from Adafruit_MotorHAT import Adafruit_MotorHAT
    _HAS_MOTORHAT = True
except ImportError:
    _HAS_MOTORHAT = False


class MecanumDriver:
    """麦轮四驱底盘驱动"""

    # 四电机的运动方向组合表
    # motor1~4 对应 Adafruit_MotorHAT 1~4
    # 按 AITank 的接线: _m1=FR(1), _m2=FL(2), _m3=TL(3), _m4=TR(4)
    _MOTION_TABLE = {
        # name: (m1_dir, m2_dir, m3_dir, m4_dir)
        "forward":         ("F", "F", "F", "F"),
        "backward":        ("B", "B", "B", "B"),
        "leftSlide":       ("B", "F", "F", "B"),  # 左移
        "rightSlide":      ("F", "B", "B", "F"),  # 右移
        "turnLeft":        ("F", "B", "B", "F"),  # 左转
        "turnRight":       ("B", "F", "F", "B"),  # 右转
        "forwardLeft":     ("F", "F", "B", "F"),
        "forwardRight":    ("B", "F", "F", "F"),
        "backwardLeft":    ("B", "B", "F", "B"),
        "backwardRight":   ("B", "F", "B", "B"),
        "spin":            ("B", "F", "F", "B"),  # 顺时针旋转 (用 turnRight)
    }

    def __init__(self, normal_speed: int = config.MOTOR_NORMAL_SPEED):
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self.normal_speed = normal_speed
        self._current_motion = None
        self._current_name = None

        if _HAS_MOTORHAT:
            self._mh = Adafruit_MotorHAT(addr=config.PCA9685_ADDR)
            self._motors = [
                self._mh.getMotor(1),
                self._mh.getMotor(2),
                self._mh.getMotor(3),
                self._mh.getMotor(4),
            ]
            self._dir_map = {"F": Adafruit_MotorHAT.FORWARD, "B": Adafruit_MotorHAT.BACKWARD}
            self._release = Adafruit_MotorHAT.RELEASE
        else:
            self._motors = None
            print("[Mecanum] Adafruit_MotorHAT 未安装, 底盘不可用")

    # ---- 底层 ----
    def _apply(self, dirs, name: str = None):
        """把 (m1~m4 的方向) 应用到电机"""
        with self._lock:
            if _HAS_MOTORHAT and self._motors:
                for m, d in zip(self._motors, dirs):
                    m.run(self._dir_map[d])
                    m.setSpeed(self.normal_speed)
            self._current_motion = dirs
            self._current_name = name

    @property
    def current_command(self) -> str | None:
        """当前正在执行的运动指令名, 停止时为 None"""
        return self._current_name

    def _release_all(self):
        if _HAS_MOTORHAT and self._motors:
            with self._lock:
                for m in self._motors:
                    m.run(self._release)
        self._current_motion = None
        self._current_name = None

    # ---- 运动接口 ----
    def forward(self):        self._apply(self._MOTION_TABLE["forward"], "forward")
    def backward(self):       self._apply(self._MOTION_TABLE["backward"], "backward")
    def leftSlide(self):      self._apply(self._MOTION_TABLE["leftSlide"], "leftSlide")
    def rightSlide(self):     self._apply(self._MOTION_TABLE["rightSlide"], "rightSlide")
    def turnLeft(self):       self._apply(self._MOTION_TABLE["turnLeft"], "turnLeft")
    def turnRight(self):      self._apply(self._MOTION_TABLE["turnRight"], "turnRight")
    def forwardLeft(self):    self._apply(self._MOTION_TABLE["forwardLeft"], "forwardLeft")
    def forwardRight(self):   self._apply(self._MOTION_TABLE["forwardRight"], "forwardRight")
    def spin(self):           self._apply(self._MOTION_TABLE["spin"], "spin")
    def stop(self):           self._release_all()

    def move_for_duration(self, direction: str, duration: float):
        """朝某方向运动 duration 秒后自动 stop (不阻塞)"""
        motion_map = {
            "forward": self.forward,
            "backward": self.backward,
            "leftSlide": self.leftSlide,
            "rightSlide": self.rightSlide,
            "turnLeft": self.turnLeft,
            "turnRight": self.turnRight,
            "spin": self.spin,
            "stop": self.stop,
        }
        fn = motion_map.get(direction, self.stop)
        fn()
        threading.Timer(duration, self.stop).start()

    def set_speed(self, speed: int):
        """动态调整速度"""
        self.normal_speed = max(0, min(255, speed))

    def shutdown(self):
        self._release_all()


# ============================================================================
# 测试入口
# ============================================================================
if __name__ == "__main__":
    print("测试 MecanumDriver 1秒 后停止...")
    m = MecanumDriver()
    m.forward()
    time.sleep(1.5)
    m.stop()
    m.shutdown()
    print("Done")
