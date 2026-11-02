"""重新打包纯 v4 原版 (修复覆盖 bug)
   关键: Adafruit_MotorHAT 只用 v4 原版的, 不要 AITank deps 的
"""
import paramiko, os, tarfile, io, select

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
OLD_V4 = r"e:\work\ev3\trunk\doc\code\aiTank\2. 课程代码  v4\小车控制"
AITANK_DEPS = r"e:\work\AITank\deps"

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    # ========== 1. v4 原版的 exp3_0_1.py ==========
    tar.add(os.path.join(OLD_V4, "exp3_0_1.py"), arcname="v4_test/exp3_0_1.py")

    # ========== 2. v4 原版的 Adafruit_MotorHAT (关键! 只用这个) ==========
    v4_mh_dir = os.path.join(OLD_V4, "Adafruit_MotorHAT")
    for f in os.listdir(v4_mh_dir):
        if f.endswith(".py"):
            full = os.path.join(v4_mh_dir, f)
            tar.add(full, arcname=f"v4_test/Adafruit_MotorHAT/{f}")
            # 打印 IN 引脚确认是 v4 原版
            with open(full, encoding="utf-8") as fh:
                for line in fh:
                    if "num == 0" in line:
                        nxt = next(fh).strip() + ", " + next(fh).strip()
                        print(f"  v4 MotorHAT_Motors.py num=0: {nxt}")
                        break

    # ========== 3. AITank deps 的 Adafruit_GPIO / Adafruit_PureIO (跳过 MotorHAT!) ==========
    for item in os.listdir(AITANK_DEPS):
        lp = os.path.join(AITANK_DEPS, item)
        if os.path.isdir(lp) and "Adafruit" in item and "MotorHAT" not in item:
            tar.add(lp, arcname=f"v4_test/{item}", recursive=True)

print(f"\n[OK] tar 包 {buf.tell()/1024:.1f} KB")

buf.seek(0)
sftp = c.open_sftp()
sftp.putfo(buf, "/tmp/v4_test.tar.gz")
sftp.close()

cmd = f"echo '{PASS}' | sudo -S rm -rf /home/pi/v4_test && tar xzf /tmp/v4_test.tar.gz -C /home/pi && rm /tmp/v4_test.tar.gz && ls /home/pi/v4_test/ && echo OK"
stdin, stdout, stderr = c.exec_command(cmd, timeout=30)
stdin.write(PASS + "\n"); stdin.flush()
print(stdout.read().decode())

# 运行
print("=" * 60)
print("  运行纯 v4 原版 exp3_0_1.py")
print("=" * 60)

cmd = f"echo '{PASS}' | sudo -S python3 /home/pi/v4_test/exp3_0_1.py 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=60)
stdin.write(PASS + "\n"); stdin.flush()

while True:
    r, w, e = select.select([stdout.channel], [], [], 0.5)
    if stdout.channel.recv_ready():
        print(stdout.channel.recv(4096).decode(errors="replace"), end="", flush=True)
    if stdout.channel.exit_status_ready() and not stdout.channel.recv_ready():
        break
print(f"\n[exit={stdout.channel.recv_exit_status()}]")

c.close()
print("\n请观察 4 个轮子方向!")
