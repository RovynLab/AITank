import paramiko, tarfile, os, io, sys, time

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
LOCAL = r"e:\work\AITank"
REMOTE = "/home/pi/AITank"

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)
print("[OK] SSH connected")

# 1. 打 tar 包 (源码 + regress.py)
items_to_include = [
    "config.py", "requirements.txt", "regress.py",
    "deps", "labs", "demos", "ai", "core", "student_api",
]
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    for item in items_to_include:
        lp = os.path.join(LOCAL, item)
        if os.path.exists(lp):
            tar.add(lp, arcname=f"AITank/{item}", recursive=True)
print(f"Archive: {buf.tell()/(1024*1024):.1f} MB")

# 2. 推 + 解压 (tar 放 /tmp 避免被 rm -rf 删)
sftp = c.open_sftp()
buf.seek(0)
sftp.putfo(buf, "/tmp/aitank_update.tar.gz")
sftp.close()

stdin, stdout, stderr = c.exec_command(f"echo '{PASS}' | sudo -S rm -rf {REMOTE} && tar xzf /tmp/aitank_update.tar.gz -C /home/pi && rm /tmp/aitank_update.tar.gz && ls {REMOTE}/regress.py && echo OK")
stdin.write(PASS + "\n"); stdin.flush()
print(stdout.read().decode().strip())

# 3. 跑回归
print("\n" + "="*70)
print("  跑第二轮回归测试 (sudo python3 regress.py)")
print("="*70)

import select
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

# 保存
with open(os.path.join(LOCAL, "tools", "regress_v2.txt"), "w", encoding="utf-8") as f:
    f.write(full)

c.close()
print("\n[OK] done")
