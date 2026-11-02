"""精准修复: 卸 ~/.local 里的 cv2 5.0, 装 4.8"""
import paramiko, time

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 1. 卸所有 cv2 (不加 sudo, 卸 ~/.local 里的)
print("=== 1. 卸 cv2 ===")
cmd = "pip3 uninstall -y --break-system-packages opencv-contrib-python opencv-python-headless opencv-python 2>&1 | tail -5"
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
print(stdout.read().decode()[:400])

# 2. 确认干净了
print("\n=== 2. 确认 cv2 已卸 ===")
cmd = "python3 -c 'import cv2; print(cv2.__version__, cv2.__file__)' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd)
out = stdout.read().decode().strip()
print("cv2 状态:", out if out else "(empty)")

# 3. 装 4.8 (后台, 不加 sudo → 装到 ~/.local)
print("\n=== 3. 后台装 opencv-contrib-python==4.8.0.76 ===")
cmd = "nohup pip3 install --break-system-packages --no-cache-dir --user 'opencv-contrib-python==4.8.0.76' > /tmp/pip3.log 2>&1 &"
stdin, stdout, stderr = c.exec_command(cmd)
print("后台运行中...")

# 轮询 3 分钟
for i in range(18):
    time.sleep(10)
    cmd = "tail -2 /tmp/pip3.log; echo '===PS==='; pgrep pip3 || echo none"
    stdin, stdout, stderr = c.exec_command(cmd)
    out = stdout.read().decode().strip()
    parts = out.split("===PS===")
    tail = parts[0].strip()
    ps = parts[1].strip() if len(parts) > 1 else ""
    print(f"  [{(i+1)*10}s] {tail[:90]}")
    if ("Successfully installed" in tail or "ERROR" in tail) and i > 2:
        break

# 4. 最终验证
print("\n=== 4. 最终 pip 日志 ===")
cmd = "tail -10 /tmp/pip3.log"
stdin, stdout, stderr = c.exec_command(cmd)
print(stdout.read().decode()[:600])

print("\n=== 5. cv2 + HandDetector ===")
cmd = "python3 -c 'import cv2; print(\"cv2:\", cv2.__version__, cv2.__file__); print(\"HandDetector:\", hasattr(cv2, \"HandDetector\"))' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:500])
err = stderr.read().decode()
if err: print("STDERR:", err[:200])

# 6. 还不行就 finger.py 保底
cmd2 = stdout.read().decode()
if "HandDetector: False" in cmd2 or "ImportError" in cmd2:
    print("\n=== 保底 finger.py ===")
    cmd = "cd /home/pi/AITank && python3 -c \"import sys; sys.path.insert(0,'.'); exec(open('ai/finger.py').read().split('if __name__')[0]); print('finger.py import OK')\" 2>&1"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
    print(stdout.read().decode()[:400])

c.close()
