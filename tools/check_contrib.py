import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 查 pip 里 opencv 相关的
cmd = "pip3 list 2>/dev/null | grep -i opencv; echo '---'; python3 -c 'import cv2; print(cv2.__version__); print(\"HandDetector:\", hasattr(cv2, \"HandDetector\"))' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
print("pip list opencv:", stdout.read().decode()[:400])
print("stderr:", stderr.read().decode()[:200])

# 如果没有 contrib, 换 apt 装
cmd_out = stdout.read().decode()
if "HandDetector" not in cmd_out:
    print("\n=== apt install python3-opencv-contrib ===")
    cmd = f"echo '{PASS}' | sudo -S apt-cache search opencv 2>&1 | grep -i contrib"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
    print("apt search:", stdout.read().decode()[:400])
    
    # trixie 可能没 python3-opencv-contrib, 先试 apt install
    cmd = f"echo '{PASS}' | sudo -S apt-get install -y python3-opencv-contrib 2>&1 | tail -10"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=120)
    stdin.write(PASS + "\n"); stdin.flush()
    print(stdout.read().decode()[-600:])
    err = stderr.read().decode()[-200:]
    if "Unable to locate" in err:
        print("apt 也没 python3-opencv-contrib, 放弃 contrib")

# 最终检查
print("\n=== 最终 cv2 状态 ===")
cmd = "python3 -c 'import cv2; print(cv2.__version__); print(\"HandDetector:\", hasattr(cv2, \"HandDetector\"))' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd)
print(stdout.read().decode()[:400])

c.close()
