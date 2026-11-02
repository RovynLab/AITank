import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 降级 numpy 到 1.26 (兼容 opencv 4.8)
print("=== 降级 numpy 到 1.26.4 ===")
cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages --ignore-installed 'numpy==1.26.4' 2>&1 | tail -5"
stdin, stdout, stderr = c.exec_command(cmd, timeout=60)
stdin.write(PASS + "\n"); stdin.flush()
print(stdout.read().decode()[:400])

# 验证
print("\n=== cv2 + HandDetector ===")
cmd = "python3 -c 'import numpy; print(\"numpy:\", numpy.__version__); import cv2; print(\"cv2:\", cv2.__version__); print(\"HandDetector:\", hasattr(cv2, \"HandDetector\"))' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:400])
err = stderr.read().decode()
if err: print("STDERR:", err[:300])

c.close()
