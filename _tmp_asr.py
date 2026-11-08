import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
cmd = r'''arecord -l
echo "=== card3 stream0"; cat /proc/asound/card3/stream0 2>/dev/null | head -30
echo "=== mixer"; amixer -c 3 contents 2>&1 | head -40
'''
i,o,e = c.exec_command(cmd, timeout=60)
print(o.read().decode(errors="replace"))
print("ERR:", e.read().decode(errors="replace")[:300])
c.close()
