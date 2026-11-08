import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
cmd = "grep -E 'ASR|\\[你\\]|VoiceIO|\\[.*\\] ' /home/pi/AITank/petcar/logs/petcar.log | tail -20; echo ---; tail -n 6 /home/pi/AITank/petcar/logs/petcar.log; echo ---; ps -o pcpu,time -p $(pgrep -f '^python3 -m petcar.main')"
i,o,e = c.exec_command(cmd, timeout=60)
print(o.read().decode(errors="replace"))
c.close()
