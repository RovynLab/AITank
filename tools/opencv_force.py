"""--force-reinstall + 验证"""
import paramiko, time

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 1. 先查 /usr/local 里到底有没 cv2
print("=== 1. 查 cv2 位置 ===")
cmd = "echo '{PASS}' | sudo -S bash -c 'ls -la /usr/local/lib/python3.13/dist-packages/ | grep -i cv2; ls -la /home/pi/.local/lib/python3.13/site-packages/ | grep -i cv2; python3 -c \"import cv2; print(cv2.__file__)\" 2>&1'"
cmd = f"echo '{PASS}' | sudo -S bash -c 'echo /usr/local:; ls -d /usr/local/lib/python3.13/dist-packages/cv2* 2>/dev/null; echo .local:; ls -d /home/pi/.local/lib/python3.13/site-packages/cv2* 2>/dev/null; echo py import:; python3 -c \"import cv2; print(cv2.__version__, cv2.__file__)\" 2>&1'"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:500])
err = stderr.read().decode()
if err: print("STDERR:", err[:300])

# 2. 强制重装
print("\n=== 2. --force-reinstall opencv-contrib-python==4.8.0.76 ===")
cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages --no-cache-dir --force-reinstall 'opencv-contrib-python==4.8.0.76' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=300)
stdin.write(PASS + "\n"); stdin.flush()
out = stdout.read().decode()
# 等 pip 结束
full = out
while True:
    if stdout.channel.recv_ready():
        full += stdout.channel.recv(4096).decode()
    else:
        break
print(full[-800:])
err2 = stderr.read().decode()
if err2: print("STDERR:", err2[-400:])

# 3. 验证
print("\n=== 3. 最终 cv2 ===")
cmd = "python3 -c 'import cv2; print(\"cv2:\", cv2.__version__); print(\"HandDetector:\", hasattr(cv2, \"HandDetector\"))' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:400])
err = stderr.read().decode()
if err: print("STDERR:", err[:200])

c.close()
