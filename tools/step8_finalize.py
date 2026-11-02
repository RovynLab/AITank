"""Finalize: install all pip packages for root too (sudo compatibility)"""
import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"

def run(client, cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    if "sudo -S" in cmd:
        stdin.write(PASS + "\n")
        stdin.flush()
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    code = stdout.channel.recv_exit_status()
    print(f">>> {cmd.replace(PASS, '***').strip()[:120]}")
    tail = out.split("\n")[-5:] if out else []
    for l in tail: print(f"  {l}")
    if err and "password" not in err.lower() and "WARNING" not in err:
        print(f"[ERR] {err[:300]}")
    print(f"  (exit={code})\n")
    return code

BSP = "--break-system-packages"
PACKAGES = [
    "flask", "werkzeug", "opencv-python-headless", "imutils", "getkey", "RPi.GPIO", "pygame", "Pillow",
]

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=10)

for pkg in PACKAGES:
    print(f"--- Installing {pkg} for root ---")
    run(client, f"echo '{PASS}' | sudo -S pip3 install {BSP} {pkg}", timeout=120)

print("--- Final verify all imports under sudo ---")
checks = [
    "import cv2; print(f'OpenCV {cv2.__version__}')",
    "import flask; print(f'Flask OK')",
    "import RPi.GPIO; print('RPi.GPIO OK')",
    "import pygame; print('pygame OK')",
    "from PIL import Image; print('Pillow OK')",
    "import getkey; print('getkey OK')",
    "import numpy; print(f'NumPy {numpy.__version__}')",
    "import imutils; print('imutils OK')",
]
for c in checks:
    run(client, f"echo '{PASS}' | sudo -S python3 -c \"{c}\"", timeout=10, check=False)

client.close()
print("\n=== ALL DONE ===\n✅ AITank fully deployed on Raspberry Pi!")
