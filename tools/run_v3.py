import paramiko, os

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
LOCAL = r"e:\work\AITank"
REMOTE = "/home/pi/AITank"

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)
print("[OK] SSH connected")

# 1. 只推改过的文件 (lab09 + regress.py)
sftp = c.open_sftp()
for f in ["labs/lab09_joystick.py", "regress.py", "deps/Adafruit_GPIO/Platform.py"]:
    lp = os.path.join(LOCAL, f)
    rp = f"{REMOTE}/{f}"
    sftp.put(lp, rp)
    print(f"[OK] uploaded {f}")
sftp.close()

# 2. 跑
print("\n=== Running v2 regression ===")
cmd = f"cd {REMOTE} && echo '{PASS}' | sudo -S python3 regress.py 2>&1"

import select
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
print(f"\n[exit={stdout.channel.recv_exit_status()}]")

with open(os.path.join(LOCAL, "tools", "regress_v2.txt"), "w", encoding="utf-8") as f:
    f.write(full)

c.close()
