import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
cmd = r'''pip3 install -q --break-system-packages --user py-spy -i https://pypi.tuna.tsinghua.edu.cn/simple 2>&1 | tail -2
P=$(pgrep -f "python3 -m petcar.main" | tail -1); echo PID=$P
echo raspberry | sudo -S ~/.local/bin/py-spy dump --pid $P --nonblocking 2>&1 | head -40'''
i,o,e = c.exec_command(cmd, timeout=300)
print(o.read().decode(errors="replace"))
print("ERR:", e.read().decode(errors="replace")[:300])
c.close()
