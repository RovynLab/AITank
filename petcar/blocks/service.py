# -*- coding: utf-8 -*-
"""petcar/blocks/service.py — 积木运行服务
==========================================
负责编译、单实例运行、日志、状态查询。解释器跑在后台线程。
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque

from .compiler import CompileError, compile_program

MAX_RUNTIME_S = 600


class BusyError(Exception):
    """已有程序在运行"""


class _Cancelled(Exception):
    pass


class _Timeout(Exception):
    pass


class BlockService:
    def __init__(self, runtime, max_runtime: float = MAX_RUNTIME_S):
        self.runtime = runtime
        self.max_runtime = float(max_runtime)

        self._lock = threading.Lock()
        self._state = "idle"
        self._run_id = 0
        self._started_at = 0.0
        self._current_block = None
        self._last_error = None
        self._done_reason = None

        self._logs = deque(maxlen=300)
        self._seq = 0
        self._last_block_log = {}
        self._runner = None

    # ========================================================================
    # 对外接口
    # ========================================================================
    def run(self, workspace: dict) -> dict:
        with self._lock:
            if self._state == "running":
                raise BusyError()

        ir = compile_program(workspace)   # 失败直接抛 CompileError

        with self._lock:
            if self._state == "running":
                raise BusyError()
            self._state = "running"
            self._run_id += 1
            self._started_at = time.time()
            self._current_block = None
            self._last_error = None
            self._done_reason = None
            self._logs.clear()
            self._seq = 0
            self._last_block_log.clear()
            runner = ProgramRunner(ir, self.runtime, self, self.max_runtime)
            self._runner = runner

        self.runtime.start_perception()
        self.log("info", f"开始运行，共 {ir.get('block_count', 0)} 块积木")
        runner.start()
        return {
            "run_id": self._run_id,
            "blocks": ir.get("block_count", 0),
        }

    def stop(self, estop: bool = False):
        with self._lock:
            runner = self._runner
        if runner is not None:
            runner.cancel_event.set()

        if estop:
            self.runtime.emergency_stop()
            self.log("warn", "急停！程序已停止")
        else:
            self.log("info", "停止程序")

        with self._lock:
            if runner is None:
                self._state = "idle"

    def is_running(self) -> bool:
        with self._lock:
            return self._state == "running"

    def status(self, since: int = 0) -> dict:
        with self._lock:
            logs = [x for x in self._logs if x["id"] > since]
            state = self._state
            started = self._started_at
            elapsed = (time.time() - started) if state == "running" else 0.0
            out = {
                "state": state,
                "run_id": self._run_id,
                "current_block": self._current_block,
                "elapsed": round(elapsed, 2),
                "logs": logs,
                "last_error": self._last_error,
                "done_reason": self._done_reason,
            }
        out["motion"] = self.runtime.motion_state()
        out["sees"] = self.runtime.perception_snapshot()
        return out

    def shutdown(self):
        self.stop()
        self.runtime.shutdown()

    # ========================================================================
    # 内部：日志与状态
    # ========================================================================
    def log(self, level: str, text: str):
        with self._lock:
            self._seq += 1
            self._logs.append({
                "id": self._seq,
                "ts": time.strftime("%H:%M:%S"),
                "level": level,
                "text": str(text)[:300],
            })

    def log_block(self, block_id: str | None, text: str):
        """同一积木 0.8 秒内只记一次，避免循环刷屏"""
        if not block_id:
            return
        now = time.time()
        with self._lock:
            last = self._last_block_log.get(block_id, 0)
            if now - last < 0.8:
                return
            self._last_block_log[block_id] = now
        self.log("info", text)

    def set_current(self, block_id: str | None):
        with self._lock:
            self._current_block = block_id

    def set_error(self, text: str):
        with self._lock:
            self._last_error = text

    def finish(self, reason: str):
        with self._lock:
            self._state = "idle"
            self._current_block = None
            self._done_reason = reason

        msg = {
            "completed": "程序结束",
            "stopped": "程序已停止",
            "timeout": "程序运行超时，已停止",
            "error": "程序因错误停止",
        }.get(reason, f"程序结束: {reason}")
        level = "error" if reason in ("timeout", "error") else "info"
        self.log(level, msg)


class ProgramRunner(threading.Thread):
    """单栈顺序解释器"""

    DIR_CN = {
        "forward": "前进", "backward": "后退",
        "leftSlide": "左移", "rightSlide": "右移",
        "turnLeft": "左转", "turnRight": "右转", "spin": "原地旋转",
    }
    PTZ_CN = {
        "up": "向上", "down": "向下", "left": "向左",
        "right": "向右", "center": "回正",
    }
    EMOTION_CN = {
        "neutral": "中性", "happy": "开心", "sad": "难过",
        "angry": "生气", "surprised": "惊讶", "sleepy": "困倦",
        "love": "爱心", "wink": "眨眼", "laugh": "大笑",
        "thinking": "思考", "scared": "害怕", "confused": "困惑",
    }
    TARGET_CN = {"face": "人脸", "tennis": "网球", "color": "颜色"}

    def __init__(self, ir: dict, runtime, service: BlockService,
                 max_runtime: float):
        super().__init__(daemon=True)
        self.ir = ir
        self.runtime = runtime
        self.service = service
        self.max_runtime = max_runtime
        self.cancel_event = threading.Event()
        self._t0 = time.monotonic()

    # ---------- 主流程 ----------
    def run(self):
        reason = "completed"
        try:
            hats = self.ir.get("hats") or []
            body = hats[0].get("body", []) if hats else []
            self._exec_list(body)
        except _Cancelled:
            reason = "stopped"
        except _Timeout:
            reason = "timeout"
        except Exception as e:
            reason = "error"
            self.service.set_error(str(e))
            self.service.log("error", f"运行出错: {e}")
        finally:
            self.runtime.release_all()
            self.service.finish(reason)

    def _check(self, owner=None):
        if self.cancel_event.is_set():
            raise _Cancelled()
        if time.monotonic() - self._t0 > self.max_runtime:
            raise _Timeout()
        if owner is not None:
            self.runtime.renew_motion_lease(owner)

    def _sleep(self, seconds: float, owner=None):
        end = time.monotonic() + max(0.0, float(seconds))
        while True:
            self._check(owner)
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.02, remaining))

    def _exec_list(self, body):
        for node in body:
            self._check()
            self._exec(node)

    # ---------- 单个积木 ----------
    def _exec(self, node: dict):
        op = node.get("op")
        bid = node.get("id")
        self.service.set_current(bid)

        if op == "move_for":
            direction = node["dir"]
            seconds = float(node["seconds"])
            self.service.log_block(
                bid, f"{self.DIR_CN.get(direction, direction)}"
                     f" {seconds:g} 秒")
            owner = object()
            self.runtime.move_start(direction, int(node.get("speed", 150)), owner)
            try:
                self._sleep(seconds, owner=owner)
            finally:
                self.runtime.stop_if_owner(owner)
            return

        if op == "move_stop":
            self.service.log_block(bid, "停止运动")
            self.runtime.stop_motion()
            return

        if op == "wait":
            seconds = float(node["seconds"])
            self.service.log_block(bid, f"等待 {seconds:g} 秒")
            self._sleep(seconds)
            return

        if op == "look":
            direction = node["dir"]
            degrees = float(node["degrees"])
            if direction == "center":
                text = "云台回正"
            else:
                text = (f"云台{self.PTZ_CN.get(direction, direction)}"
                        f"转 {degrees:g} 度")
            self.service.log_block(bid, text)
            self.runtime.look(direction, degrees)
            self._sleep(0.15)
            return

        if op == "emotion":
            name = node["name"]
            self.service.log_block(
                bid, f"表情: {self.EMOTION_CN.get(name, name)}")
            self.runtime.set_emotion(name)
            return

        if op == "say":
            text = node["text"]
            self.service.log_block(bid, f'说: "{text}"')
            duration = self.runtime.say(text)
            self._sleep(duration)
            return

        if op == "photo":
            self.service.log_block(bid, "拍照")
            path = self.runtime.photo()
            if path:
                self.service.log("info", f"照片已保存: {os.path.basename(path)}")
            else:
                self.service.log("warn", "拍照失败或摄像头未连接")
            return

        if op == "if_sees":
            target = node["target"]
            self.service.log_block(
                bid, f"检查是否看到{self.TARGET_CN.get(target, target)}")
            if self.runtime.sees(target):
                self.service.log(
                    "info", f"看到了{self.TARGET_CN.get(target, target)}")
                self._exec_list(node.get("body") or [])
            else:
                self.service.log(
                    "info", f"没有看到{self.TARGET_CN.get(target, target)}")
            return

        if op == "repeat":
            times = int(node.get("times", 1))
            self.service.log_block(bid, f"重复 {times} 次")
            for _ in range(times):
                self._check()
                self._exec_list(node.get("body") or [])
                time.sleep(0.005)
            return

        if op == "forever":
            self.service.log_block(bid, "一直重复")
            while True:
                self._check()
                self._exec_list(node.get("body") or [])
                time.sleep(0.01)

        raise RuntimeError(f"不支持的积木: {op}")
