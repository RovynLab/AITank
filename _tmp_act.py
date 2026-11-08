import paramiko, time
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
def sh(cmd, t=90):
    i,o,e = c.exec_command(cmd, timeout=t)
    return o.read().decode(errors="replace")
print(sh("curl -s -G --data-urlencode 'text=请你摇摇头' --data-urlencode 'speak=0' http://127.0.0.1:5000/api/chat"))
time.sleep(3)
print(sh("curl -s http://127.0.0.1:5000/api/status | head -c 900"))
print(sh("grep -E 'ChatAgent|PTZ|ptz|云台' /home/pi/AITank/petcar/logs/petcar.log | tail -8"))
c.close()
