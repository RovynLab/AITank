"""后台装 OpenCV 4.8 + 轮询进度"""
import paramiko, time, select

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 0. 先卸 opencv 5.0 (加 --break-system-packages!)
print("=== 0. 卸 OpenCV 5.0 ===")
cmd = f"echo '{PASS}' | sudo -S pip3 uninstall -y --break-system-packages opencv-python-headless opencv-contrib-python 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=60)
stdin.write(PASS + "\n"); stdin.flush()
out = stdout.read().decode()
# 等 pip 真跑完
full = ""
while True:
    r, w, e = select.select([stdout.channel], [], [], 0.5)
    if stdout.channel.recv_ready():
        ch = stdout.channel.recv(4096).decode(errors="replace")
        full += ch
    if stdout.channel.exit_status_ready() and not stdout.channel.recv_ready():
        break
print(full[-400:])

# 1. 后台装 OpenCV 4.8.0.76 (已知有 arm64 wheel)
print("\n=== 1. 后台装 opencv-contrib-python==4.8.0.76 ===")
cmd = f"nohup bash -c \"echo '{PASS}' | sudo -S pip3 install --break-system-packages --no-cache-dir 'opencv-contrib-python==4.8.0.76' > /tmp/pip_opencv.log 2>&1\" &"
stdin, stdout, stderr = c.exec_command(cmd)
print("后台运行中...")

# 2. 轮询进度
for i in range(15):
    time.sleep(10)
    cmd = "tail -3 /tmp/pip_opencv.log 2>/dev/null; echo '===PS==='; ps aux | grep pip | grep -v grep | wc -l"
    stdin, stdout, stderr = c.exec_command(cmd)
    out = stdout.read().decode().strip()
    tail = out.split("===PS===")[0].strip()
    ps_count = out.split("===PS===")[1].strip() if "===PS===" in out else ""
    print(f"  [{(i+1)*10}s] pip进程数: {ps_count} | {tail[:100]}")
    if "0" in ps_count and i > 2:  # pip 进程结束
        break

# 3. 看最终结果
print("\n=== 2. 最终 pip 日志 ===")
cmd = "tail -10 /tmp/pip_opencv.log"
stdin, stdout, stderr = c.exec_command(cmd)
print(stdout.read().decode()[:600])

# 4. 测试 HandDetector
print("\n=== 3. 测试 cv2.HandDetector ===")
cmd = "python3 -c 'import cv2; print(\"cv2:\", cv2.__version__); print(\"HandDetector:\", hasattr(cv2, \"HandDetector\"))' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:400])
err = stderr.read().decode()
if err: print("STDERR:", err[:300])

# 5. 如果 HandDetector 也不行, finger.py (纯 OpenCV 凸包法) 保底
if "HandDetector: False" in stdout.read().decode():
    print("\n=== 保底: 确认 finger.py (纯 OpenCV 凸包法) 能 import ===")
    cmd = f"cd /home/pi/AITank && python3 -c \"import sys; sys.path.insert(0,'.'); exec(open('ai/finger.py').read().split('if __name__')[0]); print('finger.py import OK')\" 2>&1"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
    print(stdout.read().decode()[:400])
    err2 = stderr.read().decode()
    if err2: print("STDERR:", err2[:300])

c.close()
print("\n完成!")
