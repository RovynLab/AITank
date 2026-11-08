import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
i,o,e = c.exec_command("grep -E 'ASR|\\[你\\]|VoiceIO' /home/pi/AITank/petcar/logs/petcar.log | tail -14; echo ---; tail -n 4 /home/pi/AITank/petcar/logs/petcar.log", timeout=60)
print(o.read().decode(errors="replace"))
c.close()
