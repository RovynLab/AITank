import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.0.100", username="pi", password="raspberrypi", timeout=15)
cmd = r'''cd /home/pi && python3 -c "
import wave
w=wave.open('asr_test.wav'); sr=w.getframerate(); n=w.getnframes()
w.setpos(int(8.5*sr)); d=w.readframes(int(14.5*sr))
o=wave.open('clip.wav','wb'); o.setnchannels(1); o.setsampwidth(2); o.setframerate(sr); o.writeframes(d); o.close()
print('clip saved', len(d)/2/sr, 's')
"
aplay -q -D plughw:CARD=UACDemoV10,DEV=0 /home/pi/clip.wav && echo PLAY_DONE
cd /home/pi && timeout 200 python3 -u -c "
from faster_whisper import WhisperModel
m=WhisperModel('tiny', device='cpu', compute_type='int8')
segs,info=m.transcribe('/home/pi/clip.wav', language='zh', beam_size=1, vad_filter=False)
segs=list(segs); print('segs', len(segs))
for s in segs: print(round(s.avg_logprob,2), s.text)
" 2>&1 | tail -8'''
i,o,e = c.exec_command(cmd, timeout=300)
print(o.read().decode(errors="replace"))
c.close()
