"""Step 3b: 清理旧目录 + tar 打包推送 + 解压 (彻底解决 Windows 路径分隔符问题)"""
import paramiko, tarfile, os, io

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
LOCAL = r"e:\work\AITank"
REMOTE = "/home/pi"

def run(client, cmd, timeout=120, check=True):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    if "sudo -S" in cmd:
        stdin.write(PASS + "\n")
        stdin.flush()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    code = stdout.channel.recv_exit_status()
    short = cmd.replace(PASS, "***").strip()[:100]
    print(f"\n>>> {short}")
    if out.strip():
        for l in out.strip().split("\n")[-8:]: print(f"  {l}")
    if err.strip() and "password" not in err.lower():
        elines = [l for l in err.strip().split("\n") if l.strip()][-3:]
        print(f"  [ERR] " + " | ".join(elines))
    if check and code != 0: print(f"  [WARN] exit={code}")
    else: print(f"  (exit={code})")
    return code, out, err

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=10)
print("=== CONNECTED ===\n")

# 1. 清理远端旧目录
print("--- Cleanup old remote dir ---")
run(client, f"rm -rf {REMOTE}/AITank", check=False)

# 2. 在内存里创建 tar 包 (排除隐藏目录和 tools)
print("\n--- Create tar archive in memory ---")
exclude = {".git", "__pycache__", ".venv", "tools", ".gitignore", "LICENSE", "README.md", "docs"}
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    for item in os.listdir(LOCAL):
        if item in exclude:
            continue
        local_path = os.path.join(LOCAL, item)
        arcname = f"AITank/{item}"
        print(f"  adding: {arcname}")
        tar.add(local_path, arcname=arcname)

buf.seek(0)
tar_size_mb = buf.tell() / (1024*1024)
print(f"\n  Archive size: {tar_size_mb:.1f} MB")

# 3. 用 sftp 推送 tar 包
print("\n--- Upload tar via SFTP ---")
sftp = client.open_sftp()
remote_tar = f"{REMOTE}/aitank.tar.gz"
sftp.putfo(buf, remote_tar)
sftp.close()
print("  ✅ Uploaded")

# 4. 解压
print("\n--- Extract on remote ---")
run(client, f"cd {REMOTE} && tar xzf aitank.tar.gz && rm aitank.tar.gz")

# 5. 验证
print("\n--- Verify ---")
run(client, f"ls -la {REMOTE}/AITank/")
run(client, f"find {REMOTE}/AITank -name '*.py' | wc -l", check=False)
run(client, f"find {REMOTE}/AITank -type d | sort", check=False)

client.close()
print("\n=== DONE ===")
