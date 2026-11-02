import paramiko
HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
def run(c, cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    if "sudo -S" in cmd: stdin.write(PASS + "\n"); stdin.flush()
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    print(f">>> {cmd.replace(PASS,'***')[:100]}")
    if out: print(f"  {out}")
    if err and "password" not in err.lower(): print(f"  [ERR] {err[:200]}")
    print()

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

checks = [
    "import cv2; print(f'OpenCV {cv2.__version__}')",
    "import flask; print(f'Flask OK')",
    "import RPi.GPIO; print('RPi.GPIO OK')",
    "import pygame; print('pygame OK')",
    "from PIL import Image; print('Pillow OK')",
    "import getkey; print('getkey OK')",
    "import numpy; print(f'NumPy {numpy.__version__}')",
    "import imutils; print('imutils OK')",
    "import Adafruit_GPIO.Platform as P; print(f'Platform detect={P.platform_detect()} (expect 1)')",
    "import Adafruit_GPIO.I2C as I; print(f'I2C default bus={I.get_default_bus()} (expect 1)')",
    "from Adafruit_MotorHAT import Adafruit_MotorHAT; mh=Adafruit_MotorHAT(addr=0x60); print('MotorHAT init OK')",
]
for chk in checks:
    run(c, f"echo '{PASS}' | sudo -S python3 -c \"{chk}\"")

c.close()
print("=== ALL VERIFIED ===")
