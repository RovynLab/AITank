"""最后一战: 跳过 numpy 卸载重装 opencv 4.8"""
import paramiko, time

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

print("=== pip install opencv-contrib-python==4.8.0.76 --ignore-installed --no-deps ===")
cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages --no-cache-dir --ignore-installed --no-deps 'opencv-contrib-python==4.8.0.76' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=120)
stdin.write(PASS + "\n"); stdin.flush()
out = stdout.read().decode()
full = out
while True:
    if stdout.channel.recv_ready():
        full += stdout.channel.recv(4096).decode()
    else:
        break
print(full[-600:])

# 验证
print("\n=== 最终 ===")
cmd = "python3 -c 'import cv2; print(\"cv2:\", cv2.__version__); print(\"file:\", cv2.__file__); print(\"HandDetector:\", hasattr(cv2, \"HandDetector\"))' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:400])
err = stderr.read().decode()
if err: print("STDERR:", err[:300])

c.close()
