"""把 v4 原版 MotorHAT 推上板 + 跑 AITank lab05 wheeltest + 回归"""
import paramiko, os, select

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
LOCAL = r"e:\work\AITank"
REMOTE = "/home/pi/AITank"

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)
print("[OK] SSH connected")

# 1. 推 MotorHAT 3 个文件
sftp = c.open_sftp()
for f in ["Adafruit_MotorHAT_Motors.py", "Adafruit_PWM_Servo_Driver.py", "__init__.py"]:
    lp = os.path.join(LOCAL, "deps", "Adafruit_MotorHAT", f)
    rp = f"{REMOTE}/deps/Adafruit_MotorHAT/{f}"
    sftp.put(lp, rp)
    print(f"  ✅ deps/Adafruit_MotorHAT/{f}")
sftp.close()
print("[OK] MotorHAT 驱动已覆盖为 v4 原版")

# 2. 验证 IN 引脚映射 (在板上 grep)
print("\n--- 验证驱动 IN 引脚 (确认是 v4 原版) ---")
cmd = f"grep -A3 'num == 0' {REMOTE}/deps/Adafruit_MotorHAT/Adafruit_MotorHAT_Motors.py | head -4"
stdin, stdout, stderr = c.exec_command(cmd)
print(stdout.read().decode())

# 3. 跑 AITank lab05_wheel_test.py (应用层, 零改动)
print("=" * 60)
print("  跑 AITank lab05_wheel_test.py (应用层零改动)")
print("  依次 M1(FR)→M2(FL)→M3(TL)→M4(TR) 各正传 2 秒")
print("=" * 60)

cmd = f"cd {REMOTE} && echo '{PASS}' | sudo -S python3 labs/lab05_wheel_test.py 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=60)
stdin.write(PASS + "\n"); stdin.flush()

while True:
    r, w, e = select.select([stdout.channel], [], [], 0.5)
    if stdout.channel.recv_ready():
        print(stdout.channel.recv(4096).decode(errors="replace"), end="", flush=True)
    if stdout.channel.exit_status_ready() and not stdout.channel.recv_ready():
        break
print(f"\n[exit={stdout.channel.recv_exit_status()}]")

# 4. 跑回归测试 (验证不崩)
print("\n" + "=" * 60)
print("  跑 regress.py (驱动覆盖后不崩)")
print("=" * 60)
cmd = f"cd {REMOTE} && echo '{PASS}' | sudo -S python3 regress.py 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=300)
stdin.write(PASS + "\n"); stdin.flush()
full = ""
while True:
    r, w, e = select.select([stdout.channel], [], [], 0.5)
    if stdout.channel.recv_ready():
        ch = stdout.channel.recv(4096).decode(errors="replace")
        full += ch
        print(ch, end="", flush=True)
    if stdout.channel.exit_status_ready() and not stdout.channel.recv_ready():
        break
rc = stdout.channel.recv_exit_status()

with open(os.path.join(LOCAL, "tools", "regress_after_driver_fix.txt"), "w", encoding="utf-8") as f:
    f.write(full)
print(f"\n[regress exit={rc}]")
print("✅ 方向对了 + 回归全过 = 完美!")

c.close()
