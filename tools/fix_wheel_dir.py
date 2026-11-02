import paramiko, os, select

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
LOCAL = r"e:\work\AITank"
REMOTE = "/home/pi/AITank"

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)
print("[OK] SSH connected")

# 1. 推驱动层文件
sftp = c.open_sftp()
fp = f"{LOCAL}/deps/Adafruit_MotorHAT/Adafruit_MotorHAT_Motors.py"
sftp.put(fp, f"{REMOTE}/deps/Adafruit_MotorHAT/Adafruit_MotorHAT_Motors.py")
print("[OK] Adafruit_MotorHAT_Motors.py pushed")
sftp.close()

# 2. 跑 lab05 轮测 (脚本会依次 M1→M2→M3→M4 正传/反转)
print("\n=== Running lab05_wheel_test.py ===")
cmd = f"cd {REMOTE} && echo '{PASS}' | sudo -S python3 labs/lab05_wheel_test.py 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=60)
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
print(f"\n[exit={stdout.channel.recv_exit_status()}]")

c.close()
print("\n[DONE]")
