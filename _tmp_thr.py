import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
cmd = r'''free -m | head -3; echo ---; uptime; echo ---; ps -L -p $(pgrep -f '[p]etcar.main') -o tid,pcpu,time,comm | sort -k2 -nr | head -6; echo ---; vmstat 1 2 | tail -2'''
i,o,e = c.exec_command(cmd, timeout=60)
print(o.read().decode(errors="replace"))
c.close()
