import paramiko, os

HOST, USER, PASS = "192.168.0.100", "pi", "raspberry"
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=10)

# 推测试脚本
sftp = c.open_sftp()
sftp.put(r"e:\work\AITank\tools\_mp_test.py", "/tmp/_mp_test.py")
sftp.close()

# 跑
cmd = "python3 /tmp/_mp_test.py 2>&1"
stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
print(stdout.read().decode()[:1500])
err = stderr.read().decode()
if err: print("STDERR:", err[-500:])
c.close()
