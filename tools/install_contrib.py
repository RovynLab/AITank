import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# pip install opencv-contrib-python
print("=== pip install opencv-contrib-python ===")
cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages opencv-contrib-python 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=180)
stdin.write(PASS + "\n"); stdin.flush()
# 等 pip 完成
out = stdout.read().decode()
err = stderr.read().decode()
print((out + err)[-600:])

# 检查 HandDetector
print("\n=== 检查 HandDetector ===")
cmd = "python3 -c \"import cv2; print('cv2:', cv2.__version__); print('HandDetector:', hasattr(cv2, 'HandDetector')); print('contrib:', 'cv2-contrib' in cv2.__file__ or 'cv2' in cv2.__file__)\" 2>&1"
stdin, stdout, stderr = c.exec_command(cmd)
print(stdout.read().decode()[:400], stderr.read().decode()[:200])

# 再查 hand 相关的
cmd = "python3 -c \"import cv2; funcs = [x for x in dir(cv2) if 'and' in x.lower() or 'gesture' in x.lower()]; print('hand/gesture funcs:', funcs[:20])\" 2>&1"
stdin, stdout, stderr = c.exec_command(cmd)
print(stdout.read().decode()[:400])

c.close()
