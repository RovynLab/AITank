import paramiko, time, json
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
def sh(cmd, t=60):
    i,o,e = c.exec_command(cmd, timeout=t)
    return o.read().decode(errors="replace")
print(sh("curl -s -X POST http://127.0.0.1:5000/api/voice_test"))
for _ in range(18):
    time.sleep(3)
    d = json.loads(sh("curl -s http://127.0.0.1:5000/api/voice_test/result"))
    print(d.get("stage"), "| 峰值", d.get("peak"), "阈值", d.get("threshold"), "ms", d.get("ms"), "| 识别:", d.get("text"))
    if d.get("done"): break
print(sh("grep -F '[ASR]' /home/pi/AITank/petcar/logs/petcar.log | tail -3"))
c.close()
