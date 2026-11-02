import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

files = ["ball_track_simple.py", "face_recognition.py", "finger.py", "finger_v2.py"]

for f in files:
    print(f"\n{'='*60}")
    print(f"运行: ai/{f} (timeout 5s 自动 kill)")
    print("=" * 60)
    cmd = f"cd /home/pi/AITank && timeout 5 python3 ai/{f} 2>&1; echo EXIT=$?"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=20)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    combined = (out + err).strip()
    # 只取前 20 行关键错误
    lines = combined.split("\n")
    for line in lines[:20]:
        print(f"  {line}")

c.close()
