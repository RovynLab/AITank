import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
i,o,e = c.exec_command("echo raspberry | sudo -S amixer -c 3 cset name='Auto Gain Control' on 2>&1 | tail -3; echo raspberry | sudo -S amixer -c 3 cset name='Mic Capture Volume' 147 2>&1 | tail -2", timeout=60)
print(o.read().decode(errors="replace"))
c.close()
