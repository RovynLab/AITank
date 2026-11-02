import paramiko, os, select

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
LOCAL = r"e:\work\AITank"
REMOTE = "/home/pi/AITank"

c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 1. 跑 finger.py (纯 OpenCV, 不需要 HandDetector 或 MediaPipe)
print("=== finger.py (纯 OpenCV 凸包缺陷法) ===")
cmd = f"cd {REMOTE} && timeout 5 python3 ai/finger.py --help 2>&1 || python3 -c \"import sys; sys.path.insert(0,'.'); exec(open('ai/finger.py').read().split('if __name__')[0]); print('finger.py import OK')\" 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
print(stdout.read().decode()[:500])
err = stderr.read().decode()
if err.strip(): print("STDERR:", err[:300])

# 2. finger_v2.py (语法+导入链验证)
print("\n=== finger_v2.py 导入验证 ===")
cmd = f"cd {REMOTE} && python3 -c \"import sys; sys.path.insert(0,'.'); exec(open('ai/finger_v2.py').read().split('if __name__')[0])\" 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
print(stdout.read().decode()[:500])
err = stderr.read().decode()
if err.strip(): print("STDERR:", err[-300:])

# 3. 跑一次 regress.py 确认全绿
print("\n=== regress.py ===")
cmd = f"cd {REMOTE} && echo '{PASS}' | sudo -S python3 regress.py 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=300)
stdin.write(PASS + "\n"); stdin.flush()
full = ""
while True:
    r, w, e = select.select([stdout.channel], [], [], 0.5)
    if stdout.channel.recv_ready():
        ch = stdout.channel.recv(4096).decode(errors="replace")
        full += ch
    if stdout.channel.exit_status_ready():
        break
# 只打印汇总
lines = full.split("\n")
for line in lines:
    if any(k in line for k in ["PASS:", "FAIL:", "通过率", "全绿", "❌", "✅ 后端"]):
        print(line)

c.close()
