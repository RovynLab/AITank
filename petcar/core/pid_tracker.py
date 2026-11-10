"""petcar PID 追踪器

用 PID 闭环控制云台, 让目标 (人脸/颜色积木) 保持在画面中心。
- 目标检测: face 用 YuNet, color 用 HSV 颜色块 (取最大块)
- 误差: 目标中心与画面中心的像素差
- 输出: 云台转角增量 (度), 带死区/限幅/抗积分饱和
"""
import threading
import time


class PID:
    def __init__(self, kp=0.04, ki=0.0, kd=0.012, out_limit=6.0, i_limit=200.0):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.out_limit = out_limit
        self.i_limit = i_limit
        self.reset()

    def reset(self):
        self.integral = 0.0
        self.prev_err = 0.0
        self.prev_t = None

    def set_params(self, kp=None, ki=None, kd=None):
        if kp is not None:
            self.kp = float(kp)
        if ki is not None:
            self.ki = float(ki)
        if kd is not None:
            self.kd = float(kd)

    def update(self, err, now=None):
        now = now or time.time()
        dt = 0.05 if self.prev_t is None else max(1e-3, now - self.prev_t)
        self.prev_t = now
        self.integral += err * dt
        self.integral = max(-self.i_limit, min(self.i_limit, self.integral))
        deriv = (err - self.prev_err) / dt
        self.prev_err = err
        out = self.kp * err + self.ki * self.integral + self.kd * deriv
        return max(-self.out_limit, min(self.out_limit, out))


class _ServoAxis:
    """Hysteresis and bounded corrections in reference-image pixels."""

    def reset(self):
        self.filtered = None
        self.active = False
        self.confirmed = 0
        self.direction = 0

    def __init__(self):
        self.reset()

    def update(self, error, gain):
        if abs(error) <= 12 or gain <= 0:
            self.reset()
            return 0.0
        direction = 1 if error > 0 else -1
        if direction != self.direction:
            self.reset()
            self.direction = direction
        self.filtered = (error if self.filtered is None else
                         0.55 * error + 0.45 * self.filtered)
        if not self.active:
            if abs(error) < 24:
                self.confirmed = 0
                return 0.0
            self.confirmed += 1
            if self.confirmed < 2:
                return 0.0
            self.active = True
        # Subtract the stop region instead of applying full error at its edge.
        correction = max(0.0, abs(self.filtered) - 12) / 10.0 * gain
        # Move faster far from center, retaining gentle corrections nearby.
        step_limit = min(4.0, 1.2 + abs(self.filtered) / 60.0)
        correction = min(step_limit, correction)
        return direction * correction if correction >= 0.3 else 0.0


class PIDTracker:
    """后台线程: 检测目标 → 视觉伺服 → 驱动云台。target: face | color | tennis

    控制律: 带滞回、平滑和步长限制的增量视觉伺服。
    偏差连续两帧超过 24px 才启动，回到 12px 内停止。
    Kp 映射为 kp*4，上限 0.8；默认增益 0.56。Ki/Kd 不参与。
    以 0.12 秒为目标控制周期，检测耗时计入周期。
    单步随偏差增大，上限 4°；接近中心时自动减速。"""

    DEADZONE = 12        # 像素死区, 小于此不动 (防抖)
    LOST_TIMEOUT = 3.0   # 丢目标超过此秒数则清平滑状态
    PX_PER_DEG = 10.0    # 640px / 水平FOV约64°
    CONTROL_INTERVAL = 0.12

    def __init__(self, camera, ptz, get_color_cfg, log=None):
        self.camera = camera
        self.ptz = ptz
        self.get_color_cfg = get_color_cfg
        self._log = log or (lambda msg: None)
        self.pid_x = PID(kp=0.14, ki=0.0, kd=0.0)   # kp 作为伺服增益
        self.pid_y = PID(kp=0.14, ki=0.0, kd=0.0)
        self.target = "face"
        self.running = False
        self._thread = None
        self._lock = threading.Lock()
        self._axis_x = _ServoAxis()
        self._axis_y = _ServoAxis()
        # 状态 (供面板实时显示)
        self.err_x = 0.0
        self.err_y = 0.0
        self.out_x = 0.0
        self.out_y = 0.0
        self.last_seen = 0.0
        self.last_box = None   # 当前锁定的目标框 (x, y, w, h), 视频流画框用

    def set_params(self, kp=None, ki=None, kd=None, target=None):
        with self._lock:
            self.pid_x.set_params(kp, ki, kd)
            self.pid_y.set_params(kp, ki, kd)
            if target in ("face", "color", "tennis"):
                if target != self.target:
                    self._axis_x.reset()
                    self._axis_y.reset()
                self.target = target

    def params(self):
        return {"kp": self.pid_x.kp, "ki": self.pid_x.ki,
                "kd": self.pid_x.kd, "target": self.target}

    def start(self):
        if self.running:
            return
        self.running = True
        self.pid_x.reset()
        self.pid_y.reset()
        self._axis_x.reset()
        self._axis_y.reset()
        self.last_seen = 0.0
        self.last_box = None
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._log(f"PID 追踪启动 (目标: {self.target})")

    def stop(self):
        self.running = False
        self.last_box = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        self.out_x = self.out_y = 0.0
        self._log("PID 追踪停止")

    def status(self):
        return {
            "running": self.running,
            "target": self.target,
            "err_x": round(self.err_x, 1),
            "err_y": round(self.err_y, 1),
            "out_x": round(self.out_x, 2),
            "out_y": round(self.out_y, 2),
            "seen": (time.time() - self.last_seen) < 0.5,
            **self.params(),
        }

    # ---------- 内部 ----------

    def _find_target(self, frame):
        """返回 ((cx, cy), (x, y, w, h)) 或 None"""
        if self.target == "face":
            faces = self.camera.detect_faces(frame)
            if not faces:
                return None
            # 取最大人脸
            f = max(faces, key=lambda f: f[2] * f[3])
            cx, cy, w, h = float(f[0]), float(f[1]), int(f[2]), int(f[3])
            return (cx, cy), (int(cx - w / 2), int(cy - h / 2), w, h)
        elif self.target == "tennis":
            from ..drivers.detectors import detect_tennis_ball
            balls = detect_tennis_ball(frame)
            if not balls:
                return None
            # detect_tennis_ball 已按面积降序, 取最大球
            x, y, w, h = balls[0][:4]
            return (x + w / 2.0, y + h / 2.0), (x, y, w, h)
        else:
            from ..drivers.detectors import detect_color
            blobs = detect_color(frame, self.get_color_cfg())
            if not blobs:
                return None
            x, y, w, h = blobs[0][:4]
            return (x + w / 2.0, y + h / 2.0), (x, y, w, h)

    def _loop(self):
        while self.running:
            cycle_started = time.monotonic()
            try:
                if not getattr(self.camera, "is_open", True):
                    time.sleep(0.3)
                    continue
                frame = self.camera.latest_frame()
                if frame is None:
                    time.sleep(0.1)
                    continue
                h, w = frame.shape[:2]
                pos = self._find_target(frame)
                if pos is None:
                    lost = time.time() - self.last_seen
                    # Never reuse filtered errors after losing the target.
                    with self._lock:
                        self._axis_x.reset()
                        self._axis_y.reset()
                    if lost > 0.5:
                        self.last_box = None   # 红框不残留, 避免误导
                    self.err_x = self.err_y = 0.0
                    self.out_x = self.out_y = 0.0
                    time.sleep(self.CONTROL_INTERVAL)
                    continue
                self.last_seen = time.time()
                (cx, cy), box = pos
                self.last_box = box
                err_x = cx - w / 2.0
                err_y = cy - h / 2.0
                self.err_x, self.err_y = err_x, err_y
                # Normalize to 640x480 so camera resolution cannot change gain.
                with self._lock:
                    gain = max(0.0, min(0.8, self.pid_x.kp * 4.0))
                    out_x = self._axis_x.update(err_x * 640.0 / w, gain)
                    out_y = self._axis_y.update(err_y * 480.0 / h, gain)
                if out_x and self.running:
                    # 目标在右 (err_x>0) → 水平角减小 (look_right 同向)
                    self.ptz.h_rotate(self.ptz.h_cur - out_x)
                if out_y and self.running:
                    # 目标在下 (err_y>0) → 垂直角减小 (向下)
                    self.ptz.v_rotate(self.ptz.v_cur - out_y)
                self.out_x, self.out_y = out_x, out_y
                time.sleep(max(0.0, self.CONTROL_INTERVAL -
                               (time.monotonic() - cycle_started)))
            except Exception as e:
                self._log(f"PID 追踪异常: {e}")
                time.sleep(0.3)
