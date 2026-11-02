"""Step 2b: pip install with --break-system-packages (PEP 668 bypass for trixie)"""
import paramiko

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
    tail = out.strip().split("\n")[-6:] if out.strip() else []
    for l in tail: print("  " + l)
    if err.strip() and "password" not in err.lower():
        elines = [l for l in err.strip().split("\n") if l.strip()][-3:]
        print(f"  [ERR] " + " | ".join(elines))
    if check and code != 0: print(f"  [WARN] exit={code}")
    else: print(f"  (exit={code})")
    return code, out, err

BSP = "--break-system-packages"
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=10)
print("=== CONNECTED ===\n")

packages = [
    ("upgrade pip", f"pip3 install {BSP} --upgrade pip setuptools wheel"),
    ("opencv + imutils", f"pip3 install {BSP} opencv-python-headless imutils"),
    ("Flask + Werkzeug", f"pip3 install {BSP} Flask Werkzeug"),
    ("getkey", f"pip3 install {BSP} getkey"),
]

for name, cmd in packages:
    print(f"\n--- {name} ---")
    run(client, cmd, timeout=300)

# 验证
print("\n\n=== FINAL VERIFICATION ===")
checks = [
    "import cv2; print(f'  OpenCV {cv2.__version__}')",
    "import numpy; print(f'  NumPy {numpy.__version__}')",
    "import imutils; print('  imutils OK')",
    "import flask; print(f'  Flask {flask.__version__}')",
    "import RPi.GPIO as GPIO; print('  RPi.GPIO OK')",
    "import pygame; print('  pygame OK')",
    "from PIL import Image; print('  Pillow OK')",
    "import smbus; print('  smbus OK')",
]
for c in checks:
    run(client, f"python3 -c \"{c}\"", timeout=15, check=False)

client.close()
print("\n=== DONE ===")
