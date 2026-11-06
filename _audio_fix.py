# -*- coding: utf-8 -*-
"""
一键修复音频栈:
1. apt install libportaudio2 espeak libsndfile1 (sudo 免密)
2. pip install sounddevice pyaudio pyttsx3 faster-whisper --break-system-packages
3. 配 ~/.asoundrc 指定默认麦克风 (card 3) 和耳机 (card 2)
4. 验证录音/播放
"""
import paramiko, time, sys

HOST='192.168.0.100'; USER='pi'; PASS='raspberrypi'
c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=15)

def run(cmd, timeout=60):
    print(f'\n$ {cmd[:90]}')
    _, so, se = c.exec_command(cmd, timeout=timeout)
    out = so.read().decode(errors='replace').strip()
    err = se.read().decode(errors='replace').strip()
    code = so.channel.recv_exit_status()
    if out:
        for line in out.split('\n')[-15:]:
            print(f'    {line}')
    if err and code != 0:
        for line in err.split('\n')[-8:]:
            print(f'    [err] {line}')
    return code, out, err

# ====== 1. apt 装系统库 (sudo 免密) ======
print('='*55)
print('[1/5] apt install PortAudio + espeak + libsndfile')
print('='*55)
run('sudo apt-get update -y', timeout=60)
run('sudo apt-get install -y libportaudio2 portaudio19-dev espeak libsndfile1 libasound2-dev', timeout=120)

# ====== 2. pip 装 Python 音频包 ======
print('\n' + '='*55)
print('[2/5] pip install sounddevice pyaudio faster-whisper')
print('='*55)
run('pip3 install --break-system-packages sounddevice pyaudio 2>&1 | tail -5', timeout=60)
run('python3 -c "import sounddevice as sd; print(f\'sounddevice OK {sd.__version__}\'); print(\'devices:\', sd.query_devices())"', timeout=10)

# ====== 3. 配 ALSA 默认设备 ======
# 麦克风: card 3 (UACDemoV10), 耳机: card 2 (Headphones)
print('\n' + '='*55)
print('[3/5] 配 ~/.asoundrc 默认设备')
print('='*55)
asound = '''# 默认输入 = USB 麦克风 (card 3)
defaults.ctl.card 2
defaults.pcm.card 2
defaults.pcm.device 0
defaults.ctl.card 2

# 让 aplay/speaker-test 走耳机
pcm.!default {
    type plug
    slave {
        pcm "hw:2,0"
        rate 44100
    }
}
ctl.!default {
    type hw
    card 2
}
'''
sftp = c.open_sftp()
with sftp.file('/home/pi/.asoundrc', 'w') as f:
    f.write(asound)
sftp.close()
run('cat ~/.asoundrc')
run('speaker-test -c1 -t sine -l1 2>&1 | head -10', timeout=15)

# ====== 4. espeak 测试 ======
print('\n' + '='*55)
print('[4/5] espeak 中文 TTS 测试 (耳机出声!)')
print('='*55)
run('which espeak && espeak --version')
run('espeak -v zh+f "你好,我是小宝,现在开始说话啦!" --stdout | aplay 2>&1 | tail -3', timeout=10)

# ====== 5. 录音测试 ======
print('\n' + '='*55)
print('[5/5] 5秒录音测试 (USB 麦克风)')
print('='*55)
run('rm -f /tmp/test_rec.wav')
run('arecord -D hw:3,0 -c1 -r16000 -f S16_LE -d 5 /tmp/test_rec.wav 2>&1', timeout=10)
run('ls -la /tmp/test_rec.wav && file /tmp/test_rec.wav')
run('aplay -D hw:2,0 /tmp/test_rec.wav 2>&1 | tail -3', timeout=10)

# ====== 6. Python sounddevice 端到端 ======
print('\n' + '='*55)
print('[6/6] Python sounddevice 端到端 (录音3s → 立即播放)')
print('='*55)
run("""python3 -c "
import numpy as np
import sounddevice as sd
fs = 16000
print('设备:', sd.query_devices())
print(f'录音中 3 秒 (in={sd.default.device[0]}, out={sd.default.device[1]})...')
rec = sd.rec(int(3*fs), samplerate=fs, channels=1, dtype='float32')
sd.wait()
vol = np.abs(rec).max()
print(f'peak volume = {vol:.3f}  (小于 0.05 说明麦克风没收到)')
# 播放
print('播放回去...')
sd.play(rec, fs)
sd.wait()
print('✅ 完成')
" 2>&1""", timeout=20)

# ====== 7. petcar TTS/ASR 驱动验证 ======
print('\n' + '='*55)
print('[7/7] petcar TTS Driver 验证')
print('='*55)
run("""cd ~/AITank && python3 -c "
import sys; sys.path.insert(0, '.')
from petcar.drivers.tts import TTSDriver
tts = TTSDriver(mode='espeak')
print(f'TTS mode: {tts.mode}')
tts.speak('你好,我是小宝,语音调试成功啦!', emotion='happy')
print('✅ TTS 播放完成')
" 2>&1""", timeout=15)

print('''
🎉 音频调试完成!

如果都 OK, 现在就能:
  1. 耳机能听到声音 (espeak / sounddevice)
  2. 麦克风能录音 (arecord -D hw:3,0 / sounddevice)
  3. petcar 启动语音交互:
     ssh pi@192.168.0.100
     cd ~/AITank
     PETCAR_LLM_BACKEND=mock python3 -m petcar.main --voice
     
     然后在终端输文字回车 (MockASR), 就能听到小宝说话 + 看 OLED 表情变化!

  真语音交互 (需要 sudo 装 libportaudio2 已搞定):
     # main.py 里改 ASR_MODE=whisper 或 ASR_MODE=sounddevice
''')

c.close()
