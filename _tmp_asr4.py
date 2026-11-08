import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
cmd = r'''cd /home/pi && timeout 200 python3 -u -c "
import time
from faster_whisper import WhisperModel
m=WhisperModel('base', device='cpu', compute_type='int8')
t0=time.time()
segs,info=m.transcribe('/home/pi/clip.wav', language='zh', beam_size=1, vad_filter=True)
segs=list(segs)
print('cost %.1fs segs=%d' % (time.time()-t0, len(segs)))
for s in segs: print(round(s.avg_logprob,2), s.text)
" 2>&1 | tail -8'''
i,o,e = c.exec_command(cmd, timeout=240)
print(o.read().decode(errors="replace"))
c.close()
