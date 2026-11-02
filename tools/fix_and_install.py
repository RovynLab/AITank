"""诊断 pip 源 + 修复 + 按优先级试装手势后端"""
import paramiko, time

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# ========== 1. 网络/DNS 诊断 ==========
print("=" * 60)
print("1. 网络 / DNS 诊断")
print("=" * 60)

tests = [
    ("DNS pypi.org", "nslookup pypi.org 2>&1 | head -3"),
    ("DNS 清华源", "nslookup pypi.tuna.tsinghua.edu.cn 2>&1 | head -3"),
    ("curl PyPI", "curl -sI https://pypi.org/simple/ 2>&1 | head -3"),
    ("curl 清华", "curl -sI https://pypi.tuna.tsinghua.edu.cn/simple/ 2>&1 | head -3"),
    ("pip config", "pip3 config list 2>&1"),
    ("pip list 超时测试", "timeout 10 pip3 install --dry-run numpy 2>&1 | tail -5"),
]
for name, cmd in tests:
    stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
    out = stdout.read().decode().strip()
    print(f"\n[{name}]")
    print(out[:300] or "(timeout/empty)")

# ========== 2. 配置清华 pip 源 ==========
print("\n" + "=" * 60)
print("2. 配置清华 pip 源")
print("=" * 60)

pip_conf = f"""[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
trusted-host = pypi.tuna.tsinghua.edu.cn
timeout = 120
"""
cmd = f"mkdir -p ~/.pip && cat > ~/.pip/pip.conf << 'PIPEOF'\n{pip_conf}PIPEOF\necho done"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
stdin.write(PASS + "\n"); stdin.flush()
print(stdout.read().decode())

# 验证 pip 源
cmd = "timeout 15 pip3 install --dry-run numpy 2>&1 | tail -5"
stdin, stdout, stderr = c.exec_command(cmd, timeout=20)
print("pip 源测试:", stdout.read().decode()[:300])

# ========== 3. 按优先级试装手势后端 ==========
print("\n" + "=" * 60)
print("3. 试装手势后端 (按优先级)")
print("=" * 60)

backends = [
    ("① mediapipe 稳定版 1.2.0", "mediapipe==1.2.0", "import mediapipe as mp; print('✅', mp.__version__); import mediapipe.solutions.hands as h; print('✅ hands OK')"),
    ("② ultralytics YOLOv8-hand", "ultralytics", "from ultralytics import YOLO; print('✅ ultralytics OK')"),
    ("③ OpenCV 降级 4.8 + HandDetector", "pip uninstall -y opencv-python-headless opencv-contrib-python && pip install 'opencv-contrib-python==4.8.1.78'", "import cv2; print('cv2:', cv2.__version__); print('HandDetector:', hasattr(cv2, 'HandDetector'))"),
]

for name, install_cmd, test_cmd in backends:
    print(f"\n--- 试装 {name} ---")
    cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages --timeout 120 {install_cmd} 2>&1"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=240)
    stdin.write(PASS + "\n"); stdin.flush()
    out = stdout.read().decode()
    err = stderr.read().decode()
    if "Successfully installed" in out + err:
        print(f"  ✅ 安装成功")
        # 验证
        cmd2 = f"python3 -c '{test_cmd}' 2>&1"
        stdin, stdout, stderr = c.exec_command(cmd2, timeout=15)
        result = stdout.read().decode().strip()
        if "✅" in result or "cv2:" in result:
            print(f"  🎉 导入成功: {result[:200]}")
            break  # 装成一个就停
        else:
            print(f"  ⚠️ 导入失败: {result[:200]}")
    else:
        print(f"  ❌ 安装失败: {(out + err)[-300:]}")

# ========== 4. 最终 finger_v2.py 验证 ==========
print("\n" + "=" * 60)
print("4. finger_v2.py 最终验证")
print("=" * 60)
cmd = f"cd /home/pi/AITank && python3 -c \"import sys; sys.path.insert(0,'.'); exec(open('ai/finger_v2.py').read().split('if __name__')[0])\" 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
print(stdout.read().decode()[:500])
err = stderr.read().decode()
if err.strip(): print("STDERR:", err[-300:])

c.close()
