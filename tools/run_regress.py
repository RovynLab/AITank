import paramiko, tarfile, os, io, sys, time

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
LOCAL = r"e:\work\AITank"
REMOTE = "/home/pi/AITank"

def run(c, cmd, timeout=30):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    if "sudo -S" in cmd: stdin.write(PASS + "\n"); stdin.flush()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    code = stdout.channel.recv_exit_status()
    return code, out, err

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)
print("[OK] SSH connected")

# 推送 regress.py
sftp = c.open_sftp()
sftp.put(os.path.join(LOCAL, "regress.py"), f"{REMOTE}/regress.py")
sftp.close()
print("[OK] regress.py pushed")

# 运行全量回归 (sudo 因为要访问 I2C)
print("\n" + "="*70)
print("  跑全量回归测试 (预计 2-3 分钟)")
print("="*70)

cmd = f"cd {REMOTE} && echo '{PASS}' | sudo -S python3 regress.py 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=300)
if "sudo -S" in cmd:
    stdin.write(PASS + "\n")
    stdin.flush()

# 流式输出
full_out = ""
full_err = ""
import select
while True:
    r, w, e = select.select([stdout.channel], [], [], 0.5)
    if stdout.channel.recv_ready():
        chunk = stdout.channel.recv(4096).decode(errors="replace")
        full_out += chunk
        print(chunk, end="", flush=True)
    if stdout.channel.recv_stderr_ready():
        chunk = stdout.channel.recv_stderr(4096).decode(errors="replace")
        full_err += chunk
    if stdout.channel.exit_status_ready() and not stdout.channel.recv_ready():
        break

print(f"\n\n[exit code: {stdout.channel.recv_exit_status()}]")

# 保存输出
with open(os.path.join(LOCAL, "tools", "regress_output.txt"), "w", encoding="utf-8") as f:
    f.write(full_out + "\n--- STDERR ---\n" + full_err)
print(f"\n[OK] 完整输出已保存到 tools/regress_output.txt")

c.close()
