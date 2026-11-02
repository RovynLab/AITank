"""最终 cv2 清理 + 安装脚本"""
import paramiko, time, select

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 1. 卸所有 opencv (pi 用户)
print("=== 1. pip3 uninstall (pi 用户) ===")
cmd = "pip3 uninstall -y --break-system-packages opencv-python-headless opencv-contrib-python opencv-python 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
out = stdout.read().decode()
full = out
# 读完
while stdout.channel.recv_ready():
    full += stdout.channel.recv(4096).decode()
print(full[:400])

# 2. 手动删残留目录
print("\n=== 2. 手动删残留 ===")
cmd = "echo '{PASS}' | sudo -S rm -rf /home/pi/.local/lib/python3.13/site-packages/cv2* /usr/local/lib/python3.13/dist-packages/cv2*; python3 -c 'import cv2' 2>&1; echo exit=$?"
cmd = f"echo '{PASS}' | sudo -S rm -rf /home/pi/.local/lib/python3.13/site-packages/cv2* /usr/local/lib/python3.13/dist-packages/cv2*; python3 -c 'import cv2' 2>&1; echo exit=$?"
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
stdin.write(PASS + "\n"); stdin.flush()
print(stdout.read().decode()[:400])

# 3. 后台装 opencv-contrib-python 4.8
print("\n=== 3. nohup sudo pip install 4.8 ===")
cmd = f"echo '{PASS}' | sudo -S nohup pip3 install --break-system-packages --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple 'opencv-contrib-python==4.8.0.76' > /tmp/pip_final.log 2>&1 &"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
stdin.write(PASS + "\n"); stdin.flush()
print(stdout.read().decode().strip())

# 4. 轮询
for i in range(24):
    time.sleep(10)
    cmd = "tail -3 /tmp/pip_final.log; echo '===PS==='; pgrep -af pip3 || echo none"
    stdin, stdout, stderr = c.exec_command(cmd)
    out = stdout.read().decode().strip()
    parts = out.split("===PS===")
    tail = parts[0].strip()
    ps = parts[1].strip() if len(parts) > 1 else ""
    print(f"  [{(i+1)*10}s] {tail[:100]}")
    if ("Successfully installed" in tail or "ERROR" in tail) and i > 2:
        break

# 5. 最终
print("\n=== 4. 最终 pip 日志 ===")
cmd = "tail -8 /tmp/pip_final.log"
stdin, stdout, stderr = c.exec_command(cmd)
print(stdout.read().decode()[:500])

print("\n=== 5. cv2 + HandDetector ===")
cmd = "python3 -c 'import cv2; print(\"cv2:\", cv2.__version__); print(\"HandDetector:\", hasattr(cv2, \"HandDetector\"))' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:400])
err = stderr.read().decode()
if err: print("STDERR:", err[:200])

# 6. 如果 HandDetector 有了, finger_v2.py 就有第二个后端了
cmd2 = stdout.read().decode()
if "HandDetector: True" in cmd2:
    print("\n🎉 HandDetector 可用! finger_v2.py 现在有双后端 fallback")
elif "HandDetector: False" in cmd2:
    print("\n⚠️ HandDetector 不可用, 保底 finger.py (纯 OpenCV 凸包法)")
    cmd = "cd /home/pi/AITank && python3 -c \"import sys; sys.path.insert(0,'.'); exec(open('ai/finger.py').read().split('if __name__')[0]); print('finger.py import OK')\" 2>&1"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
    print(stdout.read().decode()[:300])

c.close()
