import paramiko, time

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# kill 残留 pip
c.exec_command("pkill -9 -f pip3 2>/dev/null; echo ok")

print("=== --force-reinstall --no-deps opencv-python-headless ===")
cmd = f"echo '{PASS}' | sudo -S nohup pip3 install --break-system-packages --no-cache-dir --force-reinstall --no-deps opencv-python-headless > /tmp/pip_cv2.log 2>&1 &"
stdin, stdout, stderr = c.exec_command(cmd, timeout=5)
stdin.write(PASS + "\n"); stdin.flush()

for i in range(12):
    time.sleep(10)
    cmd = "tail -2 /tmp/pip_cv2.log; echo '===PS==='; pgrep pip3 || echo none"
    stdin, stdout, stderr = c.exec_command(cmd)
    out = stdout.read().decode().strip()
    parts = out.split("===PS===")
    tail = parts[0].strip()
    print(f"  [{(i+1)*10}s] {tail[:100]}")
    if ("Successfully installed" in tail or "ERROR" in tail) and i > 2:
        break

# 最终
print("\n=== 恢复验证 ===")
cmd = "python3 -c 'import cv2; print(\"cv2:\", cv2.__version__); print(\"HandDetector:\", hasattr(cv2, \"HandDetector\"))' 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:400])
err = stderr.read().decode()
if err: print("STDERR:", err[:200])

c.close()
