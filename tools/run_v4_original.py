"""把 v4 小车控制原封不动推到树莓派 /home/pi/v4_test/ 运行 exp3_0_1.py
   注意: 这是独立测试, 完全不动 AITank 仓库"""
import paramiko, os, tarfile, io, select

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
OLD_V4 = r"e:\work\ev3\trunk\doc\code\aiTank\2. 课程代码  v4\小车控制"
AITANK_DEPS = r"e:\work\AITank\deps"

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)
print("[OK] SSH connected")

# 1. 打 tar 包: v4 小车控制 + deps
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    # v4 小车控制完整目录
    tar.add(os.path.join(OLD_V4, "exp3_0_1.py"), arcname="v4_test/exp3_0_1.py")
    for f in os.listdir(os.path.join(OLD_V4, "Adafruit_MotorHAT")):
        if f.endswith(".py"):
            tar.add(os.path.join(OLD_V4, "Adafruit_MotorHAT", f),
                    arcname=f"v4_test/Adafruit_MotorHAT/{f}")
    # Adafruit_GPIO 依赖
    for item in os.listdir(AITANK_DEPS):
        lp = os.path.join(AITANK_DEPS, item)
        if os.path.isdir(lp) and "Adafruit" in item:
            tar.add(lp, arcname=f"v4_test/{item}", recursive=True)

print(f"[OK] tar 包 {buf.tell()/1024:.1f} KB built (v4 小车控制 + deps)")

# 2. 推到 /home/pi/v4_test.tar.gz + 解压
buf.seek(0)
sftp = c.open_sftp()
sftp.putfo(buf, "/tmp/v4_test.tar.gz")
sftp.close()

cmd = f"echo '{PASS}' | sudo -S rm -rf /home/pi/v4_test && mkdir -p /home/pi/v4_test && tar xzf /tmp/v4_test.tar.gz -C /home/pi && rm /tmp/v4_test.tar.gz && ls /home/pi/v4_test/ && echo OK"
stdin, stdout, stderr = c.exec_command(cmd, timeout=30)
stdin.write(PASS + "\n"); stdin.flush()
print(stdout.read().decode())

# 3. 跑 exp3_0_1.py - 这是 v4 你原来方向对的 wheeltest
print("=" * 60)
print("  运行 v4 课程代码 wheel test (原版本, 不碰 AITank)")
print("  exp3_0_1.py - 依次 M1→M2→M3→M4 各正传 2 秒")
print("=" * 60)

cmd = f"echo '{PASS}' | sudo -S python3 /home/pi/v4_test/exp3_0_1.py 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=60)
stdin.write(PASS + "\n"); stdin.flush()

while True:
    r, w, e = select.select([stdout.channel], [], [], 0.5)
    if stdout.channel.recv_ready():
        chunk = stdout.channel.recv(4096).decode(errors="replace")
        print(chunk, end="", flush=True)
    if stdout.channel.exit_status_ready() and not stdout.channel.recv_ready():
        break
print(f"\n[exit={stdout.channel.recv_exit_status()}]")

c.close()
print("\n请观察 4 个轮子的实际方向!")
print("如果 v4 原版本方向对 → 把 v4 驱动覆盖到 AITank deps/")
print("如果 v4 原版本方向也错 → 说明不是驱动版本问题, 是电机物理接线问题")
