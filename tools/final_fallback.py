import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 1. CPU 特性
print("=== CPU 特性 ===")
cmd = "cat /proc/cpuinfo | head -30; echo '---'; lscpu 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:600])

# 2. 试更老的 mediapipe 版本 (不带 AES 编译)
print("\n=== 试 mediapipe 0.10.9 (最后稳定版) ===")
cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages --timeout 60 'mediapipe==0.10.9' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=120)
stdin.write(PASS + "\n"); stdin.flush()
out = stdout.read().decode(); err = stderr.read().decode()
print((out + err)[-500:])

# 3. 不行就试 ultralytics (YOLOv8-hand)
if ("Successfully installed" not in out + err) or "Illegal" in err:
    print("\n=== 试 ultralytics YOLOv8-hand ===")
    cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages --timeout 120 ultralytics 2>&1"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=180)
    stdin.write(PASS + "\n"); stdin.flush()
    print(stdout.read().decode()[-300:])
    err = stderr.read().decode()
    if err: print("STDERR:", err[-300:])

# 4. 再不行就降 OpenCV 4.8
cmd_out = out + err
if "Successfully installed" not in cmd_out and "ultralytics" not in cmd_out:
    print("\n=== 降 OpenCV 4.8 恢复 HandDetector ===")
    cmd = f"echo '{PASS}' | sudo -S pip3 uninstall -y opencv-python-headless opencv-contrib-python 2>&1 | tail -3"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=30)
    stdin.write(PASS + "\n"); stdin.flush()
    print(stdout.read().decode()[-200:])
    cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages --timeout 120 'opencv-contrib-python==4.8.1.78' 2>&1"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=180)
    stdin.write(PASS + "\n"); stdin.flush()
    print(stdout.read().decode()[-300:])
    err = stderr.read().decode()
    if err: print("STDERR:", err[-300:])

# 5. 最终检查
print("\n=== 最终环境 ===")
cmd = "python3 -c 'import cv2; print(\"cv2:\", cv2.__version__, \"HandDetector:\", hasattr(cv2, \"HandDetector\"))' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd)
print(stdout.read().decode()[:400])
err = stderr.read().decode()
if err: print("STDERR:", err[:300])

c.close()
