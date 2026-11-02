"""在树莓派上试装 mediapipe — 逐个方案排雷"""
import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 先看 apt 源里有没有 python3-mediapipe
print("=== Step 0: apt 搜 mediapipe ===")
cmd = f"echo '{PASS}' | sudo -S apt-cache search mediapipe 2>&1; echo '---'; echo '{PASS}' | sudo -S dpkg -l | grep -i mediapipe 2>&1; echo '---'; pip list 2>&1 | grep -i mediapipe"
stdin, stdout, stderr = c.exec_command(cmd, timeout=30)
stdin.write(PASS + "\n"); stdin.flush()
out = stdout.read().decode(); err = stderr.read().decode()
print(out[:500]); print(err[:300])

# Step 1: pip install mediapipe
print("\n=== Step 1: pip install mediapipe ===")
cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages mediapipe 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=120)
stdin.write(PASS + "\n"); stdin.flush()
out = stdout.read().decode(); err = stderr.read().decode()
print((out + err)[-800:])

# Step 2: 不行试 apt
if "Successfully installed" not in out + err:
    print("\n=== Step 2: apt install python3-mediapipe ===")
    cmd = f"echo '{PASS}' | sudo -S apt-get install -y python3-mediapipe 2>&1"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=120)
    stdin.write(PASS + "\n"); stdin.flush()
    out = stdout.read().decode(); err = stderr.read().decode()
    print((out + err)[-800:])

# Step 3: 还不行就放弃, 试 pip 装 mediapipe的替代 (opencv-contrib-python 里有 HandDetector)
if "Successfully installed" not in out + err and "E: Unable" not in out + err:
    pass  # 已经装成功了
else:
    # 再试一个 pip 包名
    print("\n=== Step 3: pip install mediapipe-silicon (不对arm, 试试generic) ===")
    # Debian 13 trixie + arm64, 可能的 wheel: mediapipe 没有 arm64 wheel
    # 降级方案: 装 opencv-contrib-python (已装), 用 cv2 HandDetector
    cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages opencv-contrib-python 2>&1 | tail -5"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=60)
    stdin.write(PASS + "\n"); stdin.flush()
    print(stdout.read().decode()[-500:])

# 最终验证
print("\n=== 验证 ===")
cmd = f"python3 -c 'import mediapipe; print(\"OK mediapipe\", mediapipe.__version__)' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd)
print(stdout.read().decode()[:300], stderr.read().decode()[:300])

c.close()
