"""精确查 mediapipe 1.2.0 有没有 arm64 wheel + 安装"""
import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# Step 0: 查架构 + Python 版本
print("=== Step 0: 板上架构 ===")
cmd = "uname -m; python3 --version; cat /etc/os-release | head -3"
stdin, stdout, stderr = c.exec_command(cmd)
print(stdout.read().decode())

# Step 1: pip download 查 mediapipe 1.2.0 是否有 arm64 wheel (不下载, 只解析)
print("=== Step 1: pip 解析 mediapipe==1.2.0 ===")
cmd = "pip3 download --no-deps --no-binary :none: --only-binary :all: --dest /tmp/_mp mediapipe==1.2.0 2>&1; ls /tmp/_mp/ 2>/dev/null; rm -rf /tmp/_mp"
stdin, stdout, stderr = c.exec_command(cmd, timeout=60)
print(stdout.read().decode()[:600])
err = stderr.read().decode()
if err: print("STDERR:", err[:400])

# Step 2: 直接 pip install mediapipe 1.2.0 (后台跑, 不 hang)
print("\n=== Step 2: pip install mediapipe==1.2.0 (后台) ===")
cmd = f"nohup bash -c \"echo '{PASS}' | sudo -S pip3 install --break-system-packages 'mediapipe==1.2.0' > /tmp/pip_mp.log 2>&1\" &"
stdin, stdout, stderr = c.exec_command(cmd)
print("后台 PID:", stdout.read().decode().strip() or "unknown")

# 等 60 秒, 每 10 秒刷一次进度
import time
for i in range(6):
    time.sleep(10)
    cmd = f"tail -3 /tmp/pip_mp.log 2>/dev/null; echo '---'; ps aux | grep pip | grep -v grep | wc -l"
    stdin, stdout, stderr = c.exec_command(cmd)
    out = stdout.read().decode().strip()
    print(f"  [{(i+1)*10}s] pip 进度: {out[:150]}")

# 最终状态
print("\n=== 最终 pip 日志 ===")
cmd = "cat /tmp/pip_mp.log 2>/dev/null | tail -20"
stdin, stdout, stderr = c.exec_command(cmd)
print(stdout.read().decode()[-800:])

# 检查能否 import
print("\n=== import mediapipe 测试 ===")
cmd = "python3 -c 'import mediapipe as mp; print(\"✅ mediapipe\", mp.__version__); import mediapipe.solutions.hands as h; print(\"✅ hands OK\")' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
print(stdout.read().decode()[:400])
err = stderr.read().decode()
if err: print("STDERR:", err[-200:])

c.close()
