import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
i,o,e = c.exec_command("curl -s http://127.0.0.1:5000/api/status | python3 -c \"import sys,json;d=json.load(sys.stdin);print(d['config'])\"", timeout=40)
print(o.read().decode(errors="replace"))
c.close()
