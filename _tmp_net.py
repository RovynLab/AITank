import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
i,o,e = c.exec_command("ip route | head -3; curl -s -o /dev/null -m 6 -w 'internet:%{http_code}\\n' https://www.baidu.com", timeout=40)
print(o.read().decode(errors="replace"))
c.close()
