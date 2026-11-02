"""先查网络/DNS/pip 源问题, 再解决 mediapipe"""
import paramiko

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 1. DNS 测试
print("=== DNS 测试 ===")
cmd = "nslookup pypi.org 2>&1; echo '---'; ping -c 1 pypi.org 2>&1 | head -3"
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
print(stdout.read().decode()[:500])

# 2. pip config 查当前源
print("\n=== pip config ===")
cmd = "pip3 config list 2>&1; echo '---'; cat ~/.pip/pip.conf 2>/dev/null || echo 'no ~/.pip/pip.conf'; cat /etc/pip.conf 2>/dev/null || echo 'no /etc/pip.conf'"
stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:400])

# 3. 查 mediapipe 在 PyPI 上的 wheel 平台支持 (用 requests 或 curl)
print("\n=== 查询 PyPI mediapipe wheel (用 curl) ===")
cmd = r"""curl -s https://pypi.org/pypi/mediapipe/1.2.0/json 2>&1 | python3 -c "
import sys, json
data = json.load(sys.stdin)
files = data.get('urls', [])
print(f'Total files: {len(files)}')
for f in files:
    fn = f['filename']
    if 'linux' in fn.lower() or 'manylinux' in fn.lower():
        print(f'  {fn}')
" 2>&1"""
stdin, stdout, stderr = c.exec_command(cmd, timeout=30)
print(stdout.read().decode()[:800])
err = stderr.read().decode()
if err and "curl" not in err: print("STDERR:", err[:300])

# 4. 如果 PyPI 能 curl 但 pip 慢, 换清华源
print("\n=== 换清华镜像源装 mediapipe ===")
cmd = f"echo '{PASS}' | sudo -S pip3 install --break-system-packages --index-url https://pypi.tuna.tsinghua.edu.cn/simple mediapipe==1.2.0 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=180)
stdin.write(PASS + "\n"); stdin.flush()
out = stdout.read().decode(); err = stderr.read().decode()
print((out + err)[-800:])

# 5. 最终 import 测试
if "Successfully installed" in out + err:
    print("\n=== import mediapipe ===")
    cmd = "python3 -c 'import mediapipe as mp; print(\"✅ mediapipe\", mp.__version__); import mediapipe.solutions.hands as h; print(\"✅ hands\")' 2>&1"
    stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
    print(stdout.read().decode()[:500])
    err = stderr.read()
    if err: print("STDERR:", err.decode()[:300])

c.close()
