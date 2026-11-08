import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
cmd = "grep -F '[ASR]' /home/pi/AITank/petcar/logs/petcar.log | tail -12; echo ===; grep -F '[你]' /home/pi/AITank/petcar/logs/petcar.log | tail -5; echo ===; grep -F '[VoiceIO]' /home/pi/AITank/petcar/logs/petcar.log | tail -5"
i,o,e = c.exec_command(cmd, timeout=60)
print(o.read().decode(errors="replace"))
c.close()
