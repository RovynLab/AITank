"""彻底修复 pip 源 + 后台装 OpenCV 4.8 (不 hang)"""
import paramiko, time, select

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 0. 彻底去掉 piwheels 干扰 (删掉 /etc/pip.conf 和 ~/.pip/pip.conf 里的 extra-index-url)
print("=== 0. 彻底清理 pip 源 ===")
cmd = "sudo rm -f /etc/pip.conf; cat > ~/.pip/pip.conf << 'EOF'\n[global]\nindex-url = https://pypi.tuna.tsinghua.edu.cn/simple\ntrusted-host = pypi.tuna.tsinghua.edu.cn\ntimeout = 300\nEOF\necho '==='; cat ~/.pip/pip.conf; echo '==='; pip3 config list 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
stdin.write(PASS + "\n"); stdin.flush()
print(stdout.read().decode()[:600])

# 1. 先 kill 掉残留的 pip 进程
cmd = "pkill -9 -f pip3; sleep 1; echo killed"
stdin, stdout, stderr = c.exec_command(cmd)
print(stdout.read().decode().strip())

# 2. 卸当前 opencv
print("\n=== 1. 卸 opencv 5.0 ===")
cmd = f"echo '{PASS}' | sudo -S pip3 uninstall -y --break-system-packages opencv-python-headless opencv-contrib-python 2>&1 | tail -5"
stdin, stdout, stderr = c.exec_command(cmd, timeout=30)
stdin.write(PASS + "\n"); stdin.flush()
print(stdout.read().decode()[:400])

# 3. nohup 后台装 OpenCV 4.8 (清华源 + 大 timeout)
print("\n=== 2. 后台装 opencv-contrib-python==4.8.0.76 ===")
# 注意: --index-url 强制只用清华, --extra-index-url 不加 piwheels
cmd = f"""nohup bash -c 'echo "{PASS}" | sudo -S pip3 install --break-system-packages --no-cache-dir \
  --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
  --timeout 300 \
  "opencv-contrib-python==4.8.0.76" > /tmp/pip_opencv.log 2>&1' &"""
stdin, stdout, stderr = c.exec_command(cmd)
pid = stdout.read().decode().strip()
print(f"后台 PID: {pid}")

# 4. 轮询进度 240 秒
for i in range(24):
    time.sleep(10)
    cmd = "tail -2 /tmp/pip_opencv.log 2>/dev/null; echo '===PS==='; pgrep -af pip3 || echo 'no pip'"
    stdin, stdout, stderr = c.exec_command(cmd)
    out = stdout.read().decode().strip()
    parts = out.split("===PS===")
    tail = parts[0].strip()
    ps = parts[1].strip() if len(parts) > 1 else ""
    print(f"  [{(i+1)*10}s] {tail[:100]}")
    if tail and ("Successfully installed" in tail or "ERROR" in tail) and i > 3:
        break

# 5. 最终结果
print("\n=== 3. pip 完整日志 ===")
cmd = "cat /tmp/pip_opencv.log | tail -15"
stdin, stdout, stderr = c.exec_command(cmd)
print(stdout.read().decode()[:600])

# 6. 测试
print("\n=== 4. cv2 测试 ===")
cmd = "python3 -c 'import cv2; print(\"cv2:\", cv2.__version__); print(\"HandDetector:\", hasattr(cv2, \"HandDetector\"))' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:400])
err = stderr.read().decode()
if err: print("STDERR:", err[:200])

c.close()
