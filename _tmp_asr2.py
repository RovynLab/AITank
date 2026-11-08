import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
script = r"""
import wave, numpy as np, time
from faster_whisper import WhisperModel
w = wave.open("/home/pi/asr_test.wav"); sr = w.getframerate()
a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)/32768.0
seg = a[int(8.5*sr):int(23*sr)]
t0 = time.time()
m = WhisperModel("base", device="cpu", compute_type="int8")
print("load", round(time.time()-t0,1), flush=True)
t0 = time.time()
segs, info = m.transcribe(seg, language="zh", beam_size=1, vad_filter=True)
segs = list(segs)
print("cost", round(time.time()-t0,1), flush=True)
for s in segs: print(round(s.avg_logprob,2), s.text, flush=True)
"""
s = c.open_sftp()
with s.open("/home/pi/_t_asr.py", "w") as f: f.write(script)
s.close()
i,o,e = c.exec_command("cd /home/pi && HF_ENDPOINT=https://hf-mirror.com timeout 300 python3 -u _t_asr.py 2>&1 | tail -15", timeout=330)
print(o.read().decode(errors="replace"))
c.close()
