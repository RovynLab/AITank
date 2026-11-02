import paramiko, time, select

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 后台降级 numpy
print("=== nohup pip install numpy==1.26.4 ===")
cmd = f"echo '{PASS}' | sudo -S nohup pip3 install --break-system-packages --ignore-installed --no-deps 'numpy==1.26.4' > /tmp/np.log 2>&1 &"
stdin, stdout, stderr = c.exec_command(cmd)
print("后台中...")

for i in range(12):
    time.sleep(10)
    cmd = "tail -2 /tmp/np.log; echo '===PS==='; pgrep pip3 || echo none"
    stdin, stdout, stderr = c.exec_command(cmd)
    out = stdout.read().decode().strip()
    parts = out.split("===PS===")
    tail = parts[0].strip()
    print(f"  [{(i+1)*10}s] {tail[:100]}")
    if ("Successfully" in tail or "ERROR" in tail) and i > 2:
        break

# 直接查结果
print("\n=== 最终状态 ===")
cmd = "python3 -W ignore -c 'import numpy; print(\"numpy:\", numpy.__version__); import cv2; print(\"cv2:\", cv2.__version__); print(\"HandDetector:\", hasattr(cv2, \"HandDetector\"))' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:400])
err = stderr.read().decode()
if err: print("STDERR:", err[:300])

c.close()
