import paramiko, os, select

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
LOCAL = r"e:\work\AITank"
REMOTE = "/home/pi/AITank"

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)
print("[OK] SSH connected")

sftp = c.open_sftp()
sftp.put(os.path.join(LOCAL, "regress.py"), f"{REMOTE}/regress.py")
sftp.close()
print("[OK] regress.py uploaded")

print("\n=== Running v3 regression ===")
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
print(f"\n[exit={stdout.channel.recv_exit_status()}]")

with open(os.path.join(LOCAL, "tools", "regress_v3.txt"), "w", encoding="utf-8") as f:
    f.write(full)
c.close()
print("[OK] done")
