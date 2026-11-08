import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
cmd = r'''pgrep -af petcar.main; ls -l ~/.local/bin/py-spy 2>&1 | tail -1; P=$(ps -eo pid,args | grep "[m] petcar.main" | awk '{print $1}' | head -1); echo PID=$P; echo raspberry | sudo -S ~/.local/bin/py-spy dump --pid $P 2>&1 | head -45'''
i,o,e = c.exec_command(cmd, timeout=180)
print(o.read().decode(errors="replace"))
print("ERR:", e.read().decode(errors="replace")[:400])
c.close()
