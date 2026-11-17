# -*- coding: utf-8 -*-
"""petcar/blocks/runtime.py — 积木设备运行时
=============================================
把驱动包装成解释器友好的接口，并负责运动租约（看门狗）。
"""

from __future__ import annotations

import threading
import time

from .perception import PerceptionCache

MOTION_LEASE_S = 0.6
WATCHDOG_INTERVAL = 0.2


class BlockRuntime:
    """解释器只通过这个门面操作硬件"""

    def __init__(self, mecanum=None, ptz=None, camera=None,
                 emotion=None, tts=None, log=None,
                 pid_tracker=None):
        self.mecanum = mecanum
        self.ptz = ptz
        self.camera = camera
        self.emotion = emotion
        self.tts = tts
        self._log = log or (lambda level, msg: None)
        self.pid_tracker = pid_tracker   # 外部注入，保证只有一个实例

        self._lock = threading.Lock()
        self._moving = False
        self._owner = None
        self._direction = None
        self._speed = 150
        self._lease_until = 0.0

        self.perception = PerceptionCache(camera, log=self._log)

        self._watchdog_stop = threading.Event()
        self._watchdog = threading.Thread(
            target=self._watchdog_loop, daemon=True)
        self._watchdog.start()

    # ========================================================================
    # 运动
    # ========================================================================
    def move_start(self, direction: str, speed: int, owner: object):
        with self._lock:
            self._moving = True
            self._owner = owner
            self._direction = direction
            self._speed = int(speed)
            self._lease_until = time.monotonic() + MOTION_LEASE_S

            if self.mecanum is not None:
                try:
                    self.mecanum.set_speed(self._speed)
                except Exception:
                    pass
                fn = getattr(self.mecanum, direction, None)
                if fn:
                    fn()

    def renew_motion_lease(self, owner: object):
        with self._lock:
            if self._moving and self._owner is owner:
                self._lease_until = time.monotonic() + MOTION_LEASE_S

    def stop_if_owner(self, owner: object):
        with self._lock:
            if self._moving and self._owner is owner:
                self._stop_locked()

    def stop_motion(self):
        with self._lock:
            self._stop_locked()

    def _stop_locked(self):
        self._moving = False
        self._owner = None
        self._direction = None
        if self.mecanum is not None:
            try:
                self.mecanum.stop()
            except Exception:
                pass

    def motion_state(self) -> dict:
        with self._lock:
            return {
                "moving": self._moving,
                "direction": self._direction,
                "speed": self._speed,
                "lease_ms": max(
                    0, int((self._lease_until - time.monotonic()) * 1000)),
            }

    # ========================================================================
    # 云台
    # ========================================================================
    def look(self, direction: str, degrees: float):
        if self.ptz is None:
            return
        try:
            if direction == "center":
                self.ptz.look_center()
            elif direction == "up":
                self.ptz.look_up(degrees)
            elif direction == "down":
                self.ptz.look_down(degrees)
            elif direction == "left":
                self.ptz.look_left(degrees)
            elif direction == "right":
                self.ptz.look_right(degrees)
        except Exception as e:
            self._log("warn", f"云台动作失败: {e}")

    # ========================================================================
    # 表情 / 语音
    # ========================================================================
    def set_emotion(self, name: str):
        if self.emotion is not None:
            try:
                self.emotion.set_emotion(name)
            except Exception as e:
                self._log("warn", f"表情设置失败: {e}")

    def say(self, text: str) -> float:
        """说一句话，返回估算的等待秒数"""
        text = str(text)[:100]
        duration = max(1.0, min(30.0, 0.18 * len(text)))
        if self.emotion is not None:
            try:
                self.emotion.set_emotion("happy")
                self.emotion.start_speak(duration)
            except Exception:
                pass
        if self.tts is not None:
            try:
                self.tts.speak_async(text)
            except Exception as e:
                self._log("warn", f"语音播放失败: {e}")
        return duration

    def stop_tts(self):
        """立即打断正在播放的 TTS —— 停积木程序时调用"""
        if self.tts is not None:
            try:
                self.tts.stop()
            except Exception as e:
                self._log("warn", f"打断语音失败: {e}")

    # ========================================================================
    # 拍照 / 识别
    # ========================================================================
    def photo(self) -> str | None:
        if self.camera is None:
            return None
        try:
            return self.camera.take_photo()
        except Exception as e:
            self._log("warn", f"拍照失败: {e}")
            return None

    def sees(self, target: str) -> bool:
        return self.perception.sees(target)

    def sees_color(self, key: str) -> bool:
        return self.perception.sees_color(key)

    def color_box(self, key: str) -> list | None:
        return self.perception.color_box(key)

    def perception_snapshot(self) -> dict:
        return self.perception.snapshot()

    def set_needed_colors(self, keys: list[str] | set[str] | None):
        """告诉感知线程当前程序用到哪些颜色"""
        self.perception.set_needed_colors(keys)

    # ========================================================================
    # 颜色追踪（P1）
    # ========================================================================
    def pid_tracker_running(self) -> bool:
        if self.pid_tracker is None:
            return False
        try:
            return bool(self.pid_tracker.running)
        except Exception:
            return False

    def stop_pid_tracker(self, arbitrate: bool = False):
        """停止 PID 追踪（仲裁用）"""
        if self.pid_tracker is None:
            return
        try:
            self.pid_tracker.stop()
        except Exception as e:
            self._log("warn", f"PID 追踪停止失败: {e}")

    def start_color_track(self, color_key: str) -> bool:
        """启动 PID 视觉伺服追踪指定颜色 —— 用面板持久化的 PID 参数"""
        if self.pid_tracker is None or self.camera is None or self.ptz is None:
            self._log("warn", "颜色追踪不可用（云台/摄像头未连接）")
            return False
        try:
            # 1) 先恢复面板持久化的 PID 参数 (双保险: 不假设面板之前一定 set 过)
            restored = self.pid_tracker.load_params()
            if restored:
                p = self.pid_tracker.params()
                self._log("info", "PID 参数已恢复 (kp={:.3f}, 增益={:.1f})".format(
                    p["kp"], p["kp"] * 25))
            # 2) 设置目标颜色 (不覆盖面板 kp/ki/kd)
            self.pid_tracker.set_target_color(color_key)
            self.pid_tracker.set_params(target="color", persist=False)
            # 3) 启动
            self.pid_tracker.start()
            return True
        except Exception as e:
            self._log("warn", f"启动颜色追踪失败: {e}")
            return False

    def stop_color_track(self):
        if self.pid_tracker is None:
            return
        try:
            self.pid_tracker.stop()
        except Exception as e:
            self._log("warn", f"停止颜色追踪失败: {e}")

    # ========================================================================
    # 生命周期
    # ========================================================================
    def start_perception(self):
        self.perception.start()

    def stop_perception(self):
        self.perception.stop()

    def release_all(self):
        self.stop_motion()
        self.stop_perception()
        self.stop_color_track()
        self.stop_tts()

    def emergency_stop(self):
        # 先停电机, 采样线程异步退出, 保证急停接口快速返回
        self.stop_motion()
        self.stop_color_track()
        self.stop_tts()
        self.perception.abort()

    def shutdown(self):
        self._watchdog_stop.set()
        self.release_all()

    # ========================================================================
    # 看门狗
    # ========================================================================
    def _watchdog_loop(self):
        while not self._watchdog_stop.wait(WATCHDOG_INTERVAL):
            expired = False
            with self._lock:
                if self._moving and time.monotonic() > self._lease_until:
                    self._stop_locked()
                    expired = True
            if expired:
                self._log("warn", "运动租约超时，已自动停车")
