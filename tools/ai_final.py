import paramiko, os, select

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
LOCAL = r"e:\work\AITank"
REMOTE = "/home/pi/AITank"

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 推修复的文件
sftp = c.open_sftp()
for f in ["ball_track_simple.py"]:
    lp = os.path.join(LOCAL, "ai", f)
    rp = f"{REMOTE}/ai/{f}"
    sftp.put(lp, rp)
    print(f"  ✅ ai/{f}")
sftp.close()

# 逐个 timeout 运行
files = ["ball_track_simple.py", "face_recognition.py", "finger.py", "finger_v2.py"]

for f in files:
    print(f"\n{'='*60}")
    print(f"timeout 10s: ai/{f}")
    print("=" * 60)
    cmd = f"cd {REMOTE} && timeout 10 python3 ai/{f} 2>&1; echo EXIT=$?"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=20)
    out = stdout.read().decode(errors="replace")
    exit_line = ""
    for line in out.split("\n"):
        if "EXIT=" in line:
            exit_line = line
        elif line.strip():
            print(f"  {line}")

# regress
print(f"\n{'='*60}")
print("regress.py (简)")
print("=" * 60)
cmd = f"cd {REMOTE} && echo '{PASS}' | sudo -S python3 regress.py 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=180)
stdin.write(PASS + "\n"); stdin.flush()
full = ""
while True:
    r, w, e = select.select([stdout.channel], [], [], 0.5)
    if stdout.channel.recv_ready():
        full += stdout.channel.recv(4096).decode(errors="replace")
    if stdout.channel.exit_status_ready() and not stdout.channel.recv_ready():
        break
for line in full.split("\n"):
    if any(k in line for k in ["PASS:", "FAIL:", "通过率", "全绿", "🎉"]):
        print(line)

c.close()
