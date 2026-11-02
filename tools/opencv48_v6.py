"""sudo 彻底清 cv2 5.0 + 让 4.8 生效"""
import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 1. 用 sudo 彻底删干净所有 cv2 (两边位置)
print("=== 1. sudo 彻底清理所有 cv2 ===")
cmd = f"""echo '{PASS}' | sudo -S bash -c '
  echo "=== ~/.local ===" && ls -la /home/pi/.local/lib/python3.13/site-packages/ | grep -i cv2
  echo "=== /usr/local ===" && ls -la /usr/local/lib/python3.13/dist-packages/ | grep -i cv2
  echo "=== rm ~/.local cv2 ===" && rm -rf /home/pi/.local/lib/python3.13/site-packages/cv2*
  echo "=== pip uninstall /usr/local ===" && pip3 uninstall -y --break-system-packages opencv-contrib-python opencv-python-headless 2>&1 | tail -3
  echo "=== 清理完验证 ===" && python3 -c "import cv2; print(cv2.__file__, cv2.__version__)" 2>&1
'"""
stdin, stdout, stderr = c.exec_command(cmd, timeout=30)
out = stdout.read().decode()
err = stderr.read().decode()
print(out[:800])
if err: print("STDERR:", err[:300])

# 2. 现在只有 apt 的 python3-opencv (如果有的话), 应该 import 报错
print("\n=== 2. pip list opencv ===")
cmd = "pip3 list 2>/dev/null | grep -i opencv; echo '---'; echo 'sudo:'; echo '${PASS}' | sudo -S pip3 list 2>/dev/null | grep -i opencv"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:400])

# 3. 干净装 4.8 (sudo, 装到 /usr/local)
print("\n=== 3. 干净装 opencv-contrib-python==4.8.0.76 (sudo) ===")
cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages --no-cache-dir 'opencv-contrib-python==4.8.0.76' 2>&1 | tail -15"
stdin, stdout, stderr = c.exec_command(cmd, timeout=180)
stdin.write(PASS + "\n"); stdin.flush()
print(stdout.read().decode()[:600])
err = stderr.read().decode()
if err: print("STDERR:", err[:300])

# 4. 最终 cv2 + HandDetector
print("\n=== 4. 最终 ===")
cmd = "python3 -c 'import cv2; print(\"cv2:\", cv2.__version__); print(\"file:\", cv2.__file__); print(\"HandDetector:\", hasattr(cv2, \"HandDetector\"))' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:400])

c.close()
