"""
keyboard_listener.py — USB 键盘事件监听
=========================================

用 evdev 直接读 /dev/input/eventX，绕过 termios（systemd 服务 stdin 是 /dev/null）。

使用方式：
    listener = KeyboardListener()
    listener.start()
    # 在回调里接收 KeyEvent
    listener.on_key = lambda ev: print(ev)
    # 或轮询
    ev = listener.get_key()
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Optional, Callable

try:
    from evdev import InputDevice, categorize, ecodes, list_devices
    _HAS_EVDEV = True
except ImportError:
    _HAS_EVDEV = False
    InputDevice = None
    categorize = None
    ecodes = None
    list_devices = None


# 键码 → ASCII / 功能键
_KEYMAP = {
    # 数字行（第一行）
    "KEY_1": "1", "KEY_2": "2", "KEY_3": "3", "KEY_4": "4", "KEY_5": "5",
    "KEY_6": "6", "KEY_7": "7", "KEY_8": "8", "KEY_9": "9", "KEY_0": "0",
    # 字母行
    "KEY_A": "a", "KEY_B": "b", "KEY_C": "c", "KEY_D": "d", "KEY_E": "e",
    "KEY_F": "f", "KEY_G": "g", "KEY_H": "h", "KEY_I": "i", "KEY_J": "j",
    "KEY_K": "k", "KEY_L": "l", "KEY_M": "m", "KEY_N": "n", "KEY_O": "o",
    "KEY_P": "p", "KEY_Q": "q", "KEY_R": "r", "KEY_S": "s", "KEY_T": "t",
    "KEY_U": "u", "KEY_V": "v", "KEY_W": "w", "KEY_X": "x", "KEY_Y": "y",
    "KEY_Z": "z",
    # 符号
    "KEY_MINUS": "-", "KEY_EQUAL": "=",
    "KEY_LEFTBRACE": "[", "KEY_RIGHTBRACE": "]",
    "KEY_SEMICOLON": ";", "KEY_APOSTROPHE": "'",
    "KEY_GRAVE": "`", "KEY_BACKSLASH": "\\",
    "KEY_COMMA": ",", "KEY_DOT": ".", "KEY_SLASH": "/",
    "KEY_SPACE": " ",
    # 功能键
    "KEY_ENTER": "ENTER",
    "KEY_BACKSPACE": "BACKSPACE",
    "KEY_ESC": "ESC",
    "KEY_TAB": "TAB",
    "KEY_UP": "UP",
    "KEY_DOWN": "DOWN",
    "KEY_LEFT": "LEFT",
    "KEY_RIGHT": "RIGHT",
    "KEY_F1": "F1",
    "KEY_F2": "F2",
    "KEY_F3": "F3",
    "KEY_F4": "F4",
    "KEY_F5": "F5",
    "KEY_F6": "F6",
    "KEY_F7": "F7",
    "KEY_F8": "F8",
    "KEY_F9": "F9",
    "KEY_F10": "F10",
    "KEY_F11": "F11",
    "KEY_F12": "F12",
}

# Shift 映射（简化：只处理符号和大写字母）
_SHIFT_MAP = {
    "1": "!", "2": "@", "3": "#", "4": "$", "5": "%",
    "6": "^", "7": "&", "8": "*", "9": "(", "0": ")",
    "-": "_", "=": "+",
    "[": "{", "]": "}",
    ";": ":", "'": '"',
    "`": "~", "\\": "|",
    ",": "<", ".": ">", "/": "?",
}


@dataclass
class KeyEvent:
    """解析后的按键事件"""
    char: str          # ASCII 字符，或功能键名 (ENTER/ESC/UP...)
    is_functional: bool  # True = 功能键，False = 普通可打印字符
    shift: bool        # 是否同时按了 Shift
    ctrl: bool         # 是否同时按了 Ctrl


class KeyboardListener:
    """USB 键盘事件监听"""

    def __init__(self, grab: bool = False):
        """
        Args:
            grab: True=独占物理键盘（其他进程收不到按键，如 X11/VNC）
                  False=共享模式（按键同时给 Menu 和系统，推荐默认）
        """
        self._device: Optional[InputDevice] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._shift_pressed = False
        self._ctrl_pressed = False
        self._on_key: Optional[Callable[[KeyEvent], None]] = None
        self._queue = []          # 线程安全的简易队列
        self._lock = threading.Lock()
        self._grab = grab

    @property
    def on_key(self) -> Optional[Callable[[KeyEvent], None]]:
        return self._on_key

    @on_key.setter
    def on_key(self, cb: Callable[[KeyEvent], None]):
        self._on_key = cb

    def _find_keyboard(self) -> Optional[str]:
        """在 /dev/input/by-id 下找键盘设备"""
        if not _HAS_EVDEV:
            return None
        try:
            for path in list_devices():
                dev = InputDevice(path)
                name = dev.name.lower()
                if "keyboard" in name or "kbd" in name:
                    dev.close()
                    return path
            # 备用：扫所有 eventX，看 capabilities 里有没有 EV_KEY
            for path in list_devices():
                dev = InputDevice(path)
                caps = dev.capabilities()
                ev_keys = caps.get(ecodes.EV_KEY, [])
                # 有 KEY_A~KEY_Z 就基本是键盘
                if ecodes.KEY_A in ev_keys and ecodes.KEY_Z in ev_keys:
                    dev.close()
                    return path
                dev.close()
        except Exception as e:
            print(f"[Keyboard] 扫描设备失败: {e}")
        return None

    def start(self) -> bool:
        """启动监听线程，返回是否成功找到键盘"""
        if self._running:
            return True
        if not _HAS_EVDEV:
            print("[Keyboard] evdev 未安装，请 pip install evdev")
            return False

        path = self._find_keyboard()
        if not path:
            print("[Keyboard] 未检测到 USB 键盘")
            return False

        self._device = InputDevice(path)
        if self._grab:
            self._device.grab()
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="kbd")
        self._thread.start()
        print(f"[Keyboard] 已绑定: {path} ({self._device.name})")
        return True

    def stop(self):
        self._running = False
        if self._device:
            try:
                if self._grab:
                    self._device.ungrab()
                self._device.close()
            except Exception:
                pass
            self._device = None

    def get_key(self, timeout: float = 0.5) -> Optional[KeyEvent]:
        """阻塞取一个按键事件（简易队列）"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self._queue:
                    return self._queue.pop(0)
            time.sleep(0.01)
        return None

    def _emit(self, ev: KeyEvent):
        """投递事件到回调或队列"""
        if self._on_key:
            try:
                self._on_key(ev)
            except Exception as e:
                print(f"[Keyboard] 回调异常: {e}")
        else:
            with self._lock:
                self._queue.append(ev)

    def _run_loop(self):
        try:
            for raw in self._device.read_loop():
                if not self._running:
                    break
                if raw.type != ecodes.EV_KEY:
                    continue
                # 只处理 keydown（value=1），忽略 keyup 和 repeat
                if raw.value != 1:
                    # 但要捕获 Shift/Ctrl 的 keyup 状态
                    key_name = ecodes.keys.get(raw.code, "")
                    if raw.value == 0:  # keyup
                        if key_name in ("KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"):
                            self._shift_pressed = False
                        elif key_name in ("KEY_LEFTCTRL", "KEY_RIGHTCTRL"):
                            self._ctrl_pressed = False
                    continue

                key_name = ecodes.keys.get(raw.code, "")

                # 捕获修饰键状态
                if key_name in ("KEY_LEFTSHIFT", "KEY_RIGHTSHIFT"):
                    self._shift_pressed = True
                    continue
                if key_name in ("KEY_LEFTCTRL", "KEY_RIGHTCTRL"):
                    self._ctrl_pressed = True
                    continue

                char = _KEYMAP.get(key_name)
                if char is None:
                    continue

                is_func = char in ("ENTER", "BACKSPACE", "ESC", "TAB",
                                   "UP", "DOWN", "LEFT", "RIGHT",
                                   "F1","F2","F3","F4","F5","F6",
                                   "F7","F8","F9","F10","F11","F12")

                # 普通字符：Shift 处理
                if not is_func and self._shift_pressed:
                    if char in _SHIFT_MAP:
                        char = _SHIFT_MAP[char]
                    elif char.isalpha():
                        char = char.upper()

                ev = KeyEvent(char=char, is_functional=is_func,
                              shift=self._shift_pressed, ctrl=self._ctrl_pressed)
                self._emit(ev)

        except OSError:
            # 键盘被拔掉
            print("[Keyboard] 键盘设备断开，等待重插...")
            self._running = False
        except Exception as e:
            print(f"[Keyboard] 事件循环异常: {e}")
            self._running = False
