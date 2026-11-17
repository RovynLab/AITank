"""
key_probe.py — 在板子上跑这个，按键盘上的每个键，看 evdev 报什么
用法: python3 key_probe.py
然后按 ↑ ↓ ← → OK ESC Backspace 数字键等
"""
import sys
sys.path.insert(0, '.')
from evdev import InputDevice, categorize, ecodes, list_devices

# 找键盘
kbd = None
for path in list_devices():
    dev = InputDevice(path)
    if "keyboard" in dev.name.lower() or "kbd" in dev.name.lower():
        kbd = dev
        break
if not kbd:
    for path in list_devices():
        dev = InputDevice(path)
        caps = dev.capabilities()
        ev_keys = caps.get(ecodes.EV_KEY, [])
        if ecodes.KEY_A in ev_keys:
            kbd = dev
            break

if not kbd:
    print("没找到键盘")
    sys.exit(1)

print(f"键盘: {kbd.name} ({kbd.path})")
print("按键探测中... 按 Ctrl+C 退出")
print("=" * 50)

for raw in kbd.read_loop():
    if raw.type != ecodes.EV_KEY or raw.value != 1:
        continue
    key_name = ecodes.keys.get(raw.code, f"KEY_{raw.code}")
    char_map = {
        "KEY_ENTER": "ENTER", "KEY_ESC": "ESC", "KEY_BACKSPACE": "BACKSPACE",
        "KEY_UP": "UP", "KEY_DOWN": "DOWN", "KEY_LEFT": "LEFT", "KEY_RIGHT": "RIGHT",
        "KEY_SPACE": " ", "KEY_TAB": "TAB",
    }
    nice = char_map.get(key_name, key_name)
    print(f"  按了: code={raw.code:3d}  name={key_name:20s}  →  {nice}")
