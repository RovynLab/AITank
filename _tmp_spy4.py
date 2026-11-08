import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
cmd = r'''P=$(pgrep -f "^python3 -m petcar.main"); echo raspberry | sudo -S ~/.local/bin/py-spy dump --pid $P 2>/dev/null > /tmp/spy.txt; grep -n -A12 -E "whisper|asr|voice_io" /tmp/spy.txt | head -60; echo ===; grep -c Thread /tmp/spy.txt'''
i,o,e = c.exec_command(cmd, timeout=180)
print(o.read().decode(errors="replace"))
print("ERR:", e.read().decode(errors="replace")[:300])
c.close()
