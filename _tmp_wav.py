import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
script = r"""
import wave, numpy as np
w = wave.open("/home/pi/asr_test.wav")
n = w.getnframes(); sr = w.getframerate()
a = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32)/32768.0
print("时长 %.1fs sr=%d 峰值=%.4f" % (n/sr, sr, float(np.abs(a).max())))
step = sr
for i in range(0, len(a), step):
    seg = a[i:i+step]
    if len(seg): print("  %2ds rms=%.4f" % (i//sr, float(np.sqrt((seg**2).mean()))))
"""
s = c.open_sftp()
with s.open("/home/pi/_t_wav.py", "w") as f: f.write(script)
s.close()
i,o,e = c.exec_command("python3 /home/pi/_t_wav.py 2>&1 | head -70", timeout=60)
print(o.read().decode(errors="replace"))
c.close()
