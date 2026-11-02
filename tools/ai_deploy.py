import paramiko, os

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
LOCAL = r"e:\work\AITank"
REMOTE = "/home/pi/AITank"

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 推 4 个文件
sftp = c.open_sftp()
for f in ["finger_v2.py", "ball_track_simple.py", "face_recognition.py", "finger.py"]:
    lp = os.path.join(LOCAL, "ai", f)
    rp = f"{REMOTE}/ai/{f}"
    sftp.put(lp, rp)
    print(f"  ✅ ai/{f}")
sftp.close()

# 逐个 timeout 运行
files = ["ball_track_simple.py", "face_recognition.py", "finger.py", "finger_v2.py"]

for f in files:
    print(f"\n{'='*60}")
    print(f"timeout 8s 运行: ai/{f}")
    print("=" * 60)
    cmd = f"cd {REMOTE} && timeout 8 python3 ai/{f} 2>&1 | head -25; echo EXIT=$?"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
    out = stdout.read().decode(errors="replace")
    for line in out.split("\n")[:25]:
        print(f"  {line}")

# regress
print(f"\n{'='*60}")
print("regress.py")
print("=" * 60)
cmd = f"cd {REMOTE} && echo '{PASS}' | sudo -S python3 regress.py 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=180)
stdin.write(PASS + "\n"); stdin.flush()
import select
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
print("\n全部完成!")
