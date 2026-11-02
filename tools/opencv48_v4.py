"""修复 pip --user (pi 用户也装一份) + 验证 HandDetector"""
import paramiko, time

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 0. 查 sys.path + 当前 cv2 来自哪里
print("=== 0. 查 cv2 来源 ===")
cmd = r"""python3 << 'EOF'
import sys
print("sys.path:")
for p in sys.path:
    print("  ", p)
try:
    import cv2
    print("\ncv2 file:", cv2.__file__)
    print("cv2 version:", cv2.__version__)
except ImportError as e:
    print("no cv2:", e)
EOF
"""
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:600])
err = stderr.read().decode()
if err: print("STDERR:", err[:300])

# 1. 查 site-packages 里的 opencv
print("\n=== 1. 查所有 opencv 位置 ===")
cmd = "find /usr /home/pi -name 'cv2' -type d 2>/dev/null | head -10; find /usr -name 'cv2*.dist-info' -type d 2>/dev/null | head -10; find /usr -name 'cv2*.egg-info' -type d 2>/dev/null | head -10"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:600])

# 2. 先卸 root 的 4.8
print("\n=== 2. 卸 root 的 opencv ===")
cmd = f"echo '{PASS}' | sudo -S pip3 uninstall -y --break-system-packages opencv-contrib-python 2>&1 | tail -3"
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
stdin.write(PASS + "\n"); stdin.flush()
print(stdout.read().decode()[:300])

# 3. pi 用户自己装 4.8 (pip3 不加 sudo!)
print("\n=== 3. pip3 install (pi 用户, 不加 sudo) ===")
cmd = "nohup pip3 install --break-system-packages --no-cache-dir --user 'opencv-contrib-python==4.8.0.76' > /tmp/pip2.log 2>&1 &"
stdin, stdout, stderr = c.exec_command(cmd)
print("后台中...")
time.sleep(30)

cmd = "cat /tmp/pip2.log"
stdin, stdout, stderr = c.exec_command(cmd)
print(stdout.read().decode()[:800])

# 4. 验证 cv2 来自 ~/.local
print("\n=== 4. 验证 cv2 来源 + HandDetector ===")
cmd = r"""python3 << 'EOF'
import sys
try:
    import cv2
    print("cv2 file:", cv2.__file__)
    print("cv2 version:", cv2.__version__)
    print("HandDetector:", hasattr(cv2, "HandDetector"))
except ImportError as e:
    print("no cv2:", e)
EOF
"""
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:500])
err = stderr.read().decode()
if err: print("STDERR:", err[:300])

# 5. 如果还是不显示 HandDetector, 试 apt 装 libopencv-contrib-dev (也许共享库没带 contrib)
cmd_out = stdout.read().decode()
if "HandDetector: False" in cmd_out:
    print("\n=== 5. 试 apt 装 libopencv-contrib-dev ===")
    cmd = f"echo '{PASS}' | sudo -S apt-get install -y libopencv-contrib-dev 2>&1 | tail -5"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=30)
    stdin.write(PASS + "\n"); stdin.flush()
    print(stdout.read().decode()[:400])

c.close()
