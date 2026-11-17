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

    控制律: 绝对角度视觉伺服 (非增量式 PID)
      目标角 = 当前角 - 误差px / PX_PER_DEG * 增益
    每帧直接对准, 不累积增量, 无延迟超调振荡。
    面板 Kp 滑条即增益 (kp*25): 1.0=一步对准, <1 更阻尼, >1 会振荡。
    默认 kp=0.14 (增益 3.5)。Ki/Kd 不再参与。

    PID 参数持久化: ~/.aitank/pid_params.json
      面板调参数 → set_params() 自动保存
      板重启 → main.py 创建后 load_params() 自动恢复
      积木 start_color_track → 显式 load_params() 双保险"""

    DEADZONE = 12        # 像素死区, 小于此不动 (防抖)
    LOST_TIMEOUT = 3.0   # 丢目标超过此秒数则清平滑状态
    PX_PER_DEG = 10.0    # 640px / 水平FOV约64°
    CONTROL_INTERVAL = 0.12

    DEFAULT_PARAMS = {"kp": 0.14, "ki": 0.0, "kd": 0.0}

    def __init__(self, camera, ptz, get_color_cfg=None, log=None,
                 params_path: str | None = None):
        self.camera = camera
        self.ptz = ptz
        self.get_color_cfg = get_color_cfg
        self._log = log or (lambda msg: None)
        self.pid_x = PID(kp=0.14, ki=0.0, kd=0.0)
        self.pid_y = PID(kp=0.14, ki=0.0, kd=0.0)
        self.target = "face"
        self.color_key = "custom"
        self.running = False
        self._thread = None
        self._lock = threading.Lock()
        self._axis_x = _ServoAxis()
        self._axis_y = _ServoAxis()
        self._exs = 0.0
        self._eys = 0.0
        self.err_x = 0.0
        self.err_y = 0.0
        self.out_x = 0.0
        self.out_y = 0.0
        self.last_seen = 0.0
        self.last_box = None

        # 持久化路径
        self._params_path = params_path or self._default_params_path()

    @staticmethod
    def _default_params_path() -> str:
        import os
        base = os.path.join(os.path.expanduser("~"), ".aitank")
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, "pid_params.json")

    def set_params(self, kp=None, ki=None, kd=None, target=None,
                   persist: bool = True):
        """设置 PID 参数, 默认持久化到磁盘 (面板/积木都走这里)"""
        with self._lock:
            self.pid_x.set_params(kp, ki, kd)
            self.pid_y.set_params(kp, ki, kd)
            if target in ("face", "color", "tennis"):
                if target != self.target:
                    self._axis_x.reset()
                    self._axis_y.reset()
                self.target = target
        if persist:
            self.save_params()

    def save_params(self):
        """把当前 PID 参数写到磁盘"""
        import json, os, tempfile
        try:
            data = {
                "kp": self.pid_x.kp,
                "ki": self.pid_x.ki,
                "kd": self.pid_x.kd,
                "target": self.target,
                "color_key": self.color_key,
            }
            os.makedirs(os.path.dirname(self._params_path), exist_ok=True)
            # 原子写
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self._params_path),
                                       suffix=".pid")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self._params_path)
            except Exception:
                try: os.unlink(tmp)
                except Exception: pass
                raise
        except Exception as e:
            self._log(f"PID 参数保存失败: {e}")

    def load_params(self):
        """从磁盘加载 PID 参数; 文件不存在则用默认值。
        返回 True 表示从磁盘恢复了值, False 表示用默认。"""
        import json, os
        try:
            if not os.path.exists(self._params_path):
                return False
            with open(self._params_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.set_params(kp=data.get("kp"), ki=data.get("ki"),
                            kd=data.get("kd"), persist=False)
            t = data.get("target")
            if t in ("face", "color", "tennis"):
                self.target = t
            self.color_key = data.get("color_key") or "custom"
            self._log(f"PID 参数已恢复: kp={self.pid_x.kp:.3f}")
            return True
        except Exception as e:
            self._log(f"PID 参数加载失败 (用默认): {e}")
            return False

    def reset_params(self):
        """恢复硬编码默认值并持久化"""
        self.set_params(kp=self.DEFAULT_PARAMS["kp"],
                        ki=self.DEFAULT_PARAMS["ki"],
                        kd=self.DEFAULT_PARAMS["kd"], persist=True)

    def set_target_color(self, key: str):
        """设置追踪的具体颜色 key（color_cfg 里的键）"""
        with self._lock:
            self.color_key = key or "custom"

    def params(self):
        return {"kp": self.pid_x.kp, "ki": self.pid_x.ki,
                "kd": self.pid_x.kd, "target": self.target,
                "color_key": self.color_key}

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
            # 优先走唯一数据源 color_cfg；fallback 旧回调
            try:
                from ..core import color_cfg as cc
                cfg = cc.get_cfg(self.color_key)
            except Exception:
                cfg = self.get_color_cfg() or {"h_min": 25, "h_max": 45,
                                               "s_min": 90, "s_max": 255,
                                               "v_min": 90, "v_max": 255}
            blobs = detect_color(frame, cfg)
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
