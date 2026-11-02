"""快速推 BOM 修复 + 跑最终回归"""
import paramiko, os, select

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
LOCAL = r"e:\work\AITank"
REMOTE = "/home/pi/AITank"
BOM_FILES = [
    "demos/flask_web_control/MecanumChasis.py",
    "demos/flask_web_control/PTZControl.py",
    "demos/object_tracking/MecanumChasis.py",
    "demos/object_tracking/PTZControl.py",
    "demos/traffic_sign/MecanumChasis.py",
    "labs/lab05_wheel_test.py",
    "labs/lab06_mecanum_class.py",
    "labs/lab07_mecanum_global.py",
    "labs/lab09_joystick.py",
    "labs/lab10_ptz_control.py",
    "labs/lab11_servo_test.py",
    "regress.py",
]

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)
print("[OK] SSH connected")

sftp = c.open_sftp()
for rel in BOM_FILES:
    lp = os.path.join(LOCAL, rel)
    rp = f"{REMOTE}/{rel}"
    try:
        sftp.put(lp, rp)
        print(f"  ✅ {rel}")
    except Exception as e:
        print(f"  ❌ {rel}: {e}")
sftp.close()

print("\n=== Running FINAL regression ===")
cmd = f"cd {REMOTE} && echo '{PASS}' | sudo -S python3 regress.py 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=300)
stdin.write(PASS + "\n"); stdin.flush()

full = ""
while True:
    r, w, e = select.select([stdout.channel], [], [], 0.5)
    if stdout.channel.recv_ready():
        chunk = stdout.channel.recv(4096).decode(errors="replace")
        full += chunk
        print(chunk, end="", flush=True)
    if stdout.channel.exit_status_ready() and not stdout.channel.recv_ready():
        break
exit_code = stdout.channel.recv_exit_status()
print(f"\n[exit={exit_code}]")

with open(os.path.join(LOCAL, "tools", "regress_final.txt"), "w", encoding="utf-8") as f:
    f.write(full)

# 判定
if exit_code == 0:
    print("\n🎉🎉🎉 全绿! 所有 22 个项目 PASS!")
else:
    print(f"\n⚠️  还有 FAIL, 看 regress_final.txt")

c.close()
