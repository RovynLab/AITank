import paramiko, time
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
def sh(cmd, t=60):
    i,o,e = c.exec_command(cmd, timeout=t)
    return o.read().decode(errors="replace")
for q in ["请你摇摇头", "你叫什么名字", "往前走"]:
    t0 = time.time()
    r = sh("curl -s -G --data-urlencode 'text=%s' --data-urlencode 'speak=0' http://127.0.0.1:5000/api/chat" % q)
    print("%.2fs" % (time.time()-t0), q, "→", r)
    time.sleep(2)
c.close()
