"""绕开 piwheels 源干扰, 单独装 OpenCV 4.8 + ultralytics"""
import paramiko, time

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 0. 先检查 pip 源 + 修复
print("=== 0. pip 源 ===")
cmd = "pip3 config list 2>&1; cat ~/.pip/pip.conf 2>/dev/null; cat /etc/pip.conf 2>/dev/null"
stdin, stdout, stderr = c.exec_command(cmd)
print(stdout.read().decode()[:400])

# 写干净的 pip.conf (去掉 piwheels 干扰)
pip_conf = """[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
timeout = 120
extra-index-url = https://www.piwheels.org/simple
"""
cmd = f"cat > ~/.pip/pip.conf << 'EOF'\n{pip_conf}EOF\necho done && cat ~/.pip/pip.conf"
stdin, stdout, stderr = c.exec_command(cmd)
stdin.write(PASS + "\n"); stdin.flush()
print(stdout.read().decode()[:300])

# 1. 查 opencv-contrib-python==4.8.1.78 有没有 arm64 wheel
print("\n=== 1. 查 OpenCV 4.8 wheel ===")
cmd = "curl -s 'https://pypi.tuna.tsinghua.edu.cn/simple/opencv-contrib-python/' | grep -oE 'opencv_contrib_python-4\\.8[^\"<>]*aarch64[^\"<>]*\\.whl' | head -5"
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
print("清华源 arm64 wheels:", stdout.read().decode()[:300])

# 2. 卸当前 opencv 5.0
print("\n=== 2. 卸 OpenCV 5.0 ===")
cmd = f"echo '{PASS}' | sudo -S pip3 uninstall -y opencv-python-headless opencv-contrib-python 2>&1 | tail -3"
stdin, stdout, stderr = c.exec_command(cmd, timeout=30)
stdin.write(PASS + "\n"); stdin.flush()
print(stdout.read().decode()[:300])

# 3. 装 OpenCV 4.8
print("\n=== 3. 装 opencv-contrib-python==4.8.1.78 ===")
cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages --no-cache-dir 'opencv-contrib-python==4.8.1.78' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=240)
stdin.write(PASS + "\n"); stdin.flush()
out = stdout.read().decode(); err = stderr.read().decode()
print((out + err)[-800:])

# 4. 测试 HandDetector
print("\n=== 4. 测试 HandDetector ===")
cmd = "python3 -c 'import cv2; print(\"cv2:\", cv2.__version__); print(\"HandDetector:\", hasattr(cv2, \"HandDetector\"))' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:400])
err_final = stderr.read().decode()
if err_final: print("STDERR:", err_final[:300])

# 5. 恢复 mediapipe 5.0 (如果 4.8 也失败)
if "4.8" not in (out + err):
    print("\n=== 回装 opencv 5.0 ===")
    cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages opencv-python-headless 2>&1 | tail -5"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=60)
    stdin.write(PASS + "\n"); stdin.flush()
    print(stdout.read().decode()[:300])

c.close()
