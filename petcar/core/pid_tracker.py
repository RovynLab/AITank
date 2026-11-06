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


class PIDTracker:
    """后台线程: 检测目标 → 视觉伺服 → 驱动云台。target: face | color | tennis

    控制律: 绝对角度视觉伺服 (非增量式 PID)
      目标角 = 当前角 - 误差px / PX_PER_DEG * 增益
    每帧直接对准, 不累积增量, 无延迟超调振荡。
    面板 Kp 滑条即增益 (kp*25): 1.0=一步对准, <1 更阻尼, >1 会振荡。
    Ki/Kd 不再参与。"""

    DEADZONE = 12        # 像素死区, 小于此不动 (防抖)
    LOST_TIMEOUT = 3.0   # 丢目标超过此秒数则清平滑状态
    PX_PER_DEG = 10.0    # 640px / 水平FOV约64°
    MAX_STEP = 10.0      # 单次最大修正角 (度), 防目标重现时猛甩

    def __init__(self, camera, ptz, get_color_cfg, log=None):
        self.camera = camera
        self.ptz = ptz
        self.get_color_cfg = get_color_cfg
        self._log = log or (lambda msg: None)
        self.pid_x = PID(kp=0.03, ki=0.0, kd=0.0)   # kp 作为伺服增益
        self.pid_y = PID(kp=0.03, ki=0.0, kd=0.0)
        self.target = "face"
        self.running = False
        self._thread = None
        self._lock = threading.Lock()
        self._exs = 0.0     # EMA 平滑后的误差
        self._eys = 0.0
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
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._log(f"PID 追踪启动 (目标: {self.target})")

    def stop(self):
        self.running = False
        self.last_box = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
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
                    if lost > self.LOST_TIMEOUT:
                        self._exs = self._eys = 0.0
                    if lost > 0.5:
                        self.last_box = None   # 红框不残留, 避免误导
                    self.err_x = self.err_y = 0.0
                    self.out_x = self.out_y = 0.0
                    time.sleep(0.06)
                    continue
                self.last_seen = time.time()
                (cx, cy), box = pos
                self.last_box = box
                err_x = cx - w / 2.0
                err_y = cy - h / 2.0
                self.err_x, self.err_y = err_x, err_y
                # EMA 平滑, 抗检测框抖动 (也平滑导数噪声)
                self._exs = 0.5 * err_x + 0.5 * self._exs
                self._eys = 0.5 * err_y + 0.5 * self._eys
                # 绝对角度视觉伺服: 每帧直接算出应对准的角度, 不累积增量
                # kp 滑条 0~0.08 → 增益 0~2, 1.0 = 一步对准
                gain = self.pid_x.kp * 25.0
                out_x = out_y = 0.0
                if abs(self._exs) >= self.DEADZONE:
                    out_x = max(-self.MAX_STEP, min(
                        self.MAX_STEP, self._exs / self.PX_PER_DEG * gain))
                    # 目标在右 (err_x>0) → 水平角减小 (look_right 同向)
                    self.ptz.h_rotate(self.ptz.h_cur - out_x)
                if abs(self._eys) >= self.DEADZONE:
                    out_y = max(-self.MAX_STEP, min(
                        self.MAX_STEP, self._eys / self.PX_PER_DEG * gain))
                    # 目标在下 (err_y>0) → 垂直角减小 (向下)
                    self.ptz.v_rotate(self.ptz.v_cur - out_y)
                self.out_x, self.out_y = out_x, out_y
                time.sleep(0.06)
            except Exception as e:
                self._log(f"PID 追踪异常: {e}")
                time.sleep(0.3)
