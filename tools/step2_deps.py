"""Step 2: 装剩余 apt 包 + pip install 所有 Python 依赖"""
import paramiko, sys, os, time

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"

def run(client, cmd, timeout=300, check=True):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    if "sudo -S" in cmd:
        stdin.write(PASS + "\n")
        stdin.flush()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    code = stdout.channel.recv_exit_status()
    short = cmd.replace(PASS, "***").strip()
    print(f"\n>>> {short[:120]}")
    if out.strip():
        lines = out.strip().split("\n")
        print("\n".join(lines[-8:]))  # 只打最后几行
    if err.strip() and "password" not in err.lower():
        elines = [l for l in err.strip().split("\n") if l.strip()][-5:]
        print(f"[ERR] " + "\n      ".join(elines))
    if check and code != 0: print(f"    [WARN] exit={code}")
    else: print(f"    (exit={code})")
    return code, out, err

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=10)
print("=== CONNECTED ===\n")

# 1. apt 装系统依赖 (trixie 跳过 libatlas-base-dev, 用 libopenblas-dev 替代)
print("--- Step 2.1: apt install (trixie-compatible) ---")
pkgs = "i2c-tools python3-smbus python3-pip python3-numpy python3-venv python3-dev build-essential python3-psutil libopenblas-dev libhdf5-dev libjpeg-dev libpng-dev"
run(client, f"echo '{PASS}' | sudo -S apt-get install -y --no-install-recommends {pkgs}", timeout=600)

# 2. 升级 pip
print("\n--- Step 2.2: upgrade pip ---")
run(client, f"pip3 install --upgrade pip setuptools wheel", timeout=120)

# 3. 树莓派 GPIO
print("\n--- Step 2.3: install RPi.GPIO ---")
run(client, f"pip3 install RPi.GPIO", timeout=60)

# 4. OpenCV headless (省空间, trixie python3.13 需要最新版本)
print("\n--- Step 2.4: install opencv-python-headless imutils ---")
run(client, f"pip3 install opencv-python-headless imutils", timeout=180)

# 5. Flask + Werkzeug
print("\n--- Step 2.5: install Flask Werkzeug ---")
run(client, f"pip3 install Flask Werkzeug", timeout=60)

# 6. pygame (无头模式)
print("\n--- Step 2.6: install pygame ---")
run(client, f"pip3 install pygame", timeout=60)

# 7. getkey + Pillow
print("\n--- Step 2.7: install getkey Pillow ---")
run(client, f"pip3 install getkey Pillow", timeout=60)

# 8. 验证关键包
print("\n--- Step 2.8: verify imports ---")
checks = [
    "import cv2; print(f'  OpenCV {cv2.__version__}')",
    "import numpy; print(f'  NumPy {numpy.__version__}')",
    "import smbus; print('  smbus OK')",
    "import RPi.GPIO as GPIO; print('  RPi.GPIO OK')",
    "import flask; print(f'  Flask {flask.__version__}')",
    "import pygame; print(f'  pygame {pygame.version.ver}')",
    "from PIL import Image; print('  Pillow OK')",
]
for c in checks:
    run(client, f"python3 -c \"{c}\"", timeout=15, check=False)

client.close()
print("\n=== DONE ===")
