"""
app_launcher.py — 应用子进程托管
==================================

职责：
- 从 data/menu_apps.json 读取应用注册表
- fork+exec 启动子进程（start_new_session=True → 独立会话组）
- 阻塞 wait() 等待退出，返回 exit_code
- 退出时 killpg 清残留（piper / ffmpeg 等子进程）
- 支持 Ctrl+Shift+X 强制 killpg

不负责 OLED fd 传递（那是方案 A，暂未实现）。
"""

from __future__ import annotations

import os
import sys
import json
import signal
import subprocess
import threading
import time
from typing import Optional, Callable


_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _apps_json_path() -> str:
    """应用注册表路径"""
    return os.path.join(_ROOT, "data", "menu_apps.json")


# ---------- 注册表 ----------

def load_apps() -> list[dict]:
    """读取应用注册表，返回 list[app_config]。文件不存在则返回默认"""
    path = _apps_json_path()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("apps", [])
        except Exception as e:
            print(f"[AppLauncher] 读取 {path} 失败: {e}")

    # 默认（开发机没 JSON 时也能跑）
    return [
        {
            "id": "petcar_flask",
            "name": "PetCar Web面板",
            "command": ["python3", "-m", "petcar.main", "--flask", "--port", "5000"],
            "cwd": os.path.join(_ROOT),
            "env": {},
        },
        {
            "id": "petcar_full",
            "name": "PetCar 语音+面板",
            "command": ["python3", "-m", "petcar.main"],
            "cwd": os.path.join(_ROOT),
            "env": {},
        },
    ]


# ---------- 启动器 ----------

class AppLauncher:
    """子进程托管"""

    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._current_app: Optional[dict] = None
        self._exited = threading.Event()  # 子进程退出信号

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    @property
    def current_app(self) -> Optional[dict]:
        return self._current_app

    def launch(self, app_config: dict) -> bool:
        """
        启动应用。返回是否成功创建子进程。
        调用方应该在 launch() 后调用 wait_for_exit()。
        """
        if self.is_running:
            print(f"[AppLauncher] 已有进程在跑 (pid={self._proc.pid})")
            return False

        cmd = app_config["command"]
        cwd = app_config.get("cwd") or _ROOT
        env = os.environ.copy()
        env.update(app_config.get("env", {}) or {})

        print(f"[AppLauncher] 启动: {' '.join(cmd)}")
        print(f"[AppLauncher]   cwd = {cwd}")

        try:
            self._proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                start_new_session=True,       # 关键：进新会话组 (SIDs)
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            self._current_app = app_config
            self._exited.clear()
            print(f"[AppLauncher] PID = {self._proc.pid}, SID 已创建")
            return True
        except FileNotFoundError as e:
            print(f"[AppLauncher] 可执行文件找不到: {e}")
            self._proc = None
            return False
        except Exception as e:
            print(f"[AppLauncher] 启动失败: {e}")
            self._proc = None
            return False

    def wait_for_exit(self) -> tuple[int, list[str]]:
        """
        阻塞等待子进程退出。
        返回 (exit_code, 最后 N 行 stdout)
        """
        if not self._proc:
            return -1, []

        # 先启动一个后台线程读 stdout（避免缓冲区满导致子进程卡死）
        tail_lines = []
        MAX_TAIL = 30

        def _reader():
            assert self._proc is not None
            assert self._proc.stdout is not None
            for line in self._proc.stdout:
                line = line.decode("utf-8", errors="replace").rstrip("\n")
                tail_lines.append(line)
                if len(tail_lines) > MAX_TAIL:
                    tail_lines.pop(0)

        reader_thread = threading.Thread(target=_reader, daemon=True)
        reader_thread.start()

        # 阻塞等待
        try:
            rc = self._proc.wait()
        except Exception as e:
            print(f"[AppLauncher] wait() 异常: {e}")
            rc = -1

        # 清理
        self._cleanup_children()
        self._current_app = None
        self._exited.set()

        print(f"[AppLauncher] 子进程退出 exit_code={rc}")
        return rc, tail_lines

    def kill_current(self, force: bool = False) -> bool:
        """
        杀当前运行的子进程。
        force=False: SIGTERM → 等 3 秒 → SIGKILL
        force=True:  直接 SIGKILL
        返回是否成功发出信号
        """
        if not self._proc or self._proc.poll() is not None:
            return False

        pid = self._proc.pid
        print(f"[AppLauncher] 请求 kill pid={pid} force={force}")

        # killpg 杀整个会话组（包括 petcar fork 的 piper、ffmpeg）
        try:
            if force:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            else:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                # 等 3 秒宽限期
                deadline = time.time() + 3.0
                while time.time() < deadline:
                    if self._proc.poll() is not None:
                        break
                    time.sleep(0.1)
                # 还没退？强杀
                if self._proc.poll() is None:
                    print(f"[AppLauncher] SIGTERM 超时，改用 SIGKILL")
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
        except ProcessLookupError:
            print(f"[AppLauncher] 进程 {pid} 已不存在")
        except Exception as e:
            print(f"[AppLauncher] killpg 失败: {e}")
            return False

        # 收尸
        try:
            self._proc.wait(timeout=2)
        except Exception:
            pass

        self._current_app = None
        self._exited.set()
        print(f"[AppLauncher] 已清理")
        return True

    def _cleanup_children(self):
        """子进程退出后，再次确保会话组里没残留"""
        if not self._proc:
            return
        # 等一小会儿让子进程都退
        time.sleep(0.5)
        try:
            pgid = os.getpgid(self._proc.pid)
            # SIGTERM 宽限 2 秒，再 SIGKILL
            os.killpg(pgid, signal.SIGTERM)
            time.sleep(2)
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        except (ProcessLookupError, PermissionError):
            pass
        except Exception as e:
            print(f"[AppLauncher] _cleanup_children: {e}")

    def start_exit_watcher(self, on_exit: Callable[[int, list[str]], None]):
        """
        非阻塞模式：启动一个后台线程 watch 子进程，退出时回调 on_exit(code, tail_lines)。
        比 wait_for_exit() 更适合事件循环架构（但会和 wait_for_exit 冲突，二选一）。
        """
        def _watch():
            rc, tail = self.wait_for_exit()
            try:
                on_exit(rc, tail)
            except Exception as e:
                print(f"[AppLauncher] on_exit 回调异常: {e}")

        t = threading.Thread(target=_watch, daemon=True, name="app-watch")
        t.start()
        return t
