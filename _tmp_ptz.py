import paramiko, time
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
def sh(cmd, t=60):
    i,o,e = c.exec_command(cmd, timeout=t)
    return o.read().decode(errors="replace")
print(sh("curl -s 'http://127.0.0.1:5000/api/ptz?direction=left&delta=20'; echo; sleep 1; curl -s http://127.0.0.1:5000/api/status | python3 -c \"import sys,json;d=json.load(sys.stdin);print('ptz=',d['ptz'])\""))
print(sh("grep -iE 'ptz|servo|pca9685|舵机' /home/pi/AITank/petcar/logs/petcar.log | head -10"))
c.close()
