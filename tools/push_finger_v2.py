"""推 finger_v2.py 上树莓派 + 验证不崩"""
import paramiko, os, select

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
LOCAL = r"e:\work\AITank"
REMOTE = "/home/pi/AITank"

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 推 finger_v2.py
sftp = c.open_sftp()
sftp.put(
    f"{LOCAL}/ai/finger_v2.py",
    f"{REMOTE}/ai/finger_v2.py",
)
sftp.close()
print("[OK] finger_v2.py pushed")

# Step 1: 语法验证 + import 测试 (不用摄像头)
print("\n=== Step 1: 语法 + import 测试 (无摄像头) ===")
cmd = f"cd {REMOTE} && python3 -c \"import sys; sys.path.insert(0,'.'); exec(open('ai/finger_v2.py').read().split('if __name__')[0]); print('import 链 OK')\" 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
out = stdout.read().decode(); err = stderr.read().decode()
print(out[:500])
if err.strip():
    print("STDERR:", err[-500:])

# Step 2: 检查 cv2.HandDetector 是否存在 (降级后端)
print("\n=== Step 2: 检查 OpenCV HandDetector ===")
cmd = "python3 -c \"import cv2; print('cv2 version:', cv2.__version__); print('HandDetector:', hasattr(cv2, 'HandDetector'))\" 2>&1"
stdin, stdout, stderr = c.exec_command(cmd)
print(stdout.read().decode()[:400], stderr.read().decode()[:200])

# Step 3: 如果没有 HandDetector, 装 opencv-contrib-python
cmd_out = out + err
if "HandDetector" not in cmd_out or "False" in cmd_out:
    print("\n=== Step 3: pip install opencv-contrib-python ===")
    cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages opencv-contrib-python=={''.join(str(cv2_version) for cv2_version in [cv2.__version__[:3]] if False).strip()} 2>&1 | tail -3"
    # 先查当前 opencv 版本
    cmd2 = "python3 -c 'import cv2; print(cv2.__version__)' 2>&1"
    stdin, stdout, stderr = c.exec_command(cmd2)
    cv2_ver = stdout.read().decode().strip()
    print(f"当前 cv2 版本: {cv2_ver}")

    cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages opencv-contrib-python 2>&1 | tail -10"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=120)
    stdin.write(PASS + "\n"); stdin.flush()
    print(stdout.read().decode()[-500:])

# Step 4: 最终 finger_v2.py 导入验证
print("\n=== Step 4: 最终 finger_v2.py 导入测试 ===")
cmd = f"cd {REMOTE} && python3 -c \"import sys; sys.path.insert(0,'.'); exec(open('ai/finger_v2.py').read().split('if __name__')[0])\" 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
print(stdout.read().decode()[:500], stderr.read().decode()[-300:])

c.close()
print("\n完成!")
