import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
script = r"""
import wave, numpy as np
w = wave.open("/home/pi/clip.wav"); sr = w.getframerate()
a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)/32768.0
# 取最响的 2 秒
win = sr
energies = [np.sqrt((a[i:i+win]**2).mean()) for i in range(0, len(a)-win, win)]
k = int(np.argmax(energies))
seg = a[k*win:(k+1)*win]
sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
freqs = np.fft.rfftfreq(len(seg), 1/sr)
def band(lo, hi):
    m = (freqs >= lo) & (freqs < hi)
    return float(sp[m].mean())
for lo, hi in [(0,100),(100,300),(300,1000),(1000,3000),(3000,8000),(8000,16000),(16000,24000)]:
    print("%5d-%5d Hz: %.4f" % (lo, hi, band(lo, hi)))
top = np.argsort(sp)[-6:][::-1]
print("最强频率:", [int(freqs[i]) for i in top])
print("clipped(>0.99) 比例: %.3f" % float((np.abs(seg) > 0.99).mean()))
"""
s = c.open_sftp()
with s.open("/home/pi/_t_spec.py", "w") as f: f.write(script)
s.close()
i,o,e = c.exec_command("python3 /home/pi/_t_spec.py 2>&1 | tail -15", timeout=90)
print(o.read().decode(errors="replace"))
c.close()
