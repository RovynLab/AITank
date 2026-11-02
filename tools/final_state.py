import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# cv2 状态
cmd = "python3 -c 'import cv2; print(\"cv2:\", cv2.__version__); print(\"HandDetector:\", hasattr(cv2, \"HandDetector\"))' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
out = stdout.read().decode(errors="replace")
print("cv2:", out.strip())
err = stderr.read().decode(errors="replace")
if err: print("STDERR:", err[:200])

# finger.py (纯 OpenCV) import 测试
print("\n=== finger.py import ===")
cmd = "cd /home/pi/AITank && python3 -c \"import sys; sys.path.insert(0,'.'); exec(open('ai/finger.py').read().split('if __name__')[0]); print('OK')\" 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode(errors="replace")[:300])

# regress
print("\n=== regress.py (简版) ===")
cmd = f"echo '{PASS}' | sudo -S python3 /home/pi/AITank/regress.py 2>&1 | tail -20"
stdin, stdout, stderr = c.exec_command(cmd, timeout=180)
stdin.write(PASS + "\n"); stdin.flush()
out = stdout.read().decode(errors="replace")
while True:
    if stdout.channel.recv_ready():
        out += stdout.channel.recv(4096).decode(errors="replace")
    else:
        break
# 汇总
for line in out.split("\n"):
    if any(k in line for k in ["PASS:", "FAIL:", "通过率", "全绿", "🎉"]):
        print(line)

c.close()
