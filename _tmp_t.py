import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
i,o,e = c.exec_command("grep -F '[ASR]' /home/pi/AITank/petcar/logs/petcar.log | tail -6; free -m | head -2", timeout=60)
print(o.read().decode(errors="replace"))
c.close()
