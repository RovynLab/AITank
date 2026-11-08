import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
cmd = "top -b -n1 | head -14; echo ---; ps aux | grep -E 'petcar|ollama|piper' | grep -v grep | awk '{print $2, $3, $11, $12, $13}'"
i,o,e = c.exec_command(cmd, timeout=60)
print(o.read().decode(errors="replace"))
c.close()
