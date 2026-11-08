import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
cmd = "grep -c 自动聆听中 /home/pi/AITank/petcar/logs/petcar.log; echo ---; tail -n 20 /home/pi/AITank/petcar/logs/petcar.log; echo ---; ps -o pid,pcpu,time,cmd -p 122897"
i,o,e = c.exec_command(cmd, timeout=60)
print(o.read().decode(errors="replace"))
c.close()
