"""方案: pip install mediapipe-nightly (有 ARM64 wheel!) + 降 OpenCV 4.x (恢复 HandDetector 兜底)"""
import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 先查 nightly 的 arm64 wheel 信息
print("=== Step 0: pip index 查 mediapipe-nightly ===")
cmd = "pip3 index versions mediapipe-nightly 2>&1 | head -3; echo '---'; pip3 index versions mediapipe 2>&1 | head -3"
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
print(stdout.read().decode()[:500])

# Step 1: 试装 mediapipe-nightly
print("\n=== Step 1: pip install mediapipe-nightly ===")
cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages 'mediapipe-nightly' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=180)
stdin.write(PASS + "\n"); stdin.flush()
out = stdout.read().decode(); err = stderr.read().decode()
print((out + err)[-800:])

# Step 2: 如果 nightly 也不行, 试 MediaPipe Tasks (新版 API)
if "Successfully installed" not in out + err:
    print("\n=== Step 2: pip install mediapipe-tasks (新版 API) ===")
    cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages mediapipe-tasks 2>&1"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=120)
    stdin.write(PASS + "\n"); stdin.flush()
    out2 = stdout.read().decode(); err2 = stderr.read().decode()
    print((out2 + err2)[-600:])

# Step 3: 如果还是不行, 降 OpenCV 4.8 恢复 HandDetector
all_out = out + err + locals().get("out2", "") + locals().get("err2", "")
if "Successfully installed" not in all_out:
    print("\n=== Step 3: 降 OpenCV 到 4.8 (恢复 HandDetector) ===")
    # 先卸载 5.0
    cmd = f"echo '{PASS}' | sudo -S pip3 uninstall -y opencv-python-headless opencv-contrib-python 2>&1 | tail -5"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=30)
    stdin.write(PASS + "\n"); stdin.flush()
    print(stdout.read().decode()[-300:])
    
    # 装 4.8
    cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages 'opencv-contrib-python==4.8.1.78' 2>&1"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=180)
    stdin.write(PASS + "\n"); stdin.flush()
    print(stdout.read().decode()[-600:])
    err = stderr.read().decode()
    if err:
        print(err[-300:])

# 最终检查
print("\n" + "=" * 60)
print("=== 最终环境检查 ===")
cmd = r"""python3 -c "
import sys
print('Python:', sys.version)
try:
    import mediapipe as mp
    print('✅ mediapipe:', mp.__version__)
    import mediapipe.tasks as mt
    print('✅ mediapipe.tasks:', hasattr(mt, 'vision'))
except ImportError as e:
    print('❌ mediapipe:', e)
try:
    import cv2
    print('cv2:', cv2.__version__)
    print('HandDetector:', hasattr(cv2, 'HandDetector'))
except ImportError as e:
    print('❌ cv2:', e)
try:
    import numpy; print('numpy:', numpy.__version__)
except: pass
" 2>&1"""
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
print(stdout.read().decode())
err = stderr.read().decode()
if err: print("STDERR:", err[:300])

c.close()
