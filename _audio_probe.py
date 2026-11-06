# -*- coding: utf-8 -*-
"""
语音调试: 板子音频栈全链路检测
============================
1. 音频硬件 (arecord/aplay)
2. 系统库 (espeak / portaudio)
3. Python 包 (sounddevice / pyaudio / pyttsx3)
4. 录音测试 (arecord 5秒)
5. 播放测试 (aplay / espeak)
6. Python 层测试
"""
import paramiko, time, sys

HOST='192.168.0.100'; USER='pi'; PASS='raspberrypi'
c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=15)

def run(cmd, timeout=30):
    print(f'\n$ {cmd[:90]}')
    _, so, se = c.exec_command(cmd, timeout=timeout)
    out = so.read().decode(errors='replace').strip()
    err = se.read().decode(errors='replace').strip()
    code = so.channel.recv_exit_status()
    if out:
        for line in out.split('\n')[-15:]:
            print(f'    {line}')
    if err:
        for line in err.split('\n')[-10:]:
            print(f'    [err] {line}')
    return code, out, err

print('='*55)
print('1. 音频硬件 (arecord -l / aplay -l)')
print('='*55)
run('arecord -l 2>&1 | head -20 || echo NO_ALSA_UTILS')
run('aplay -l 2>&1 | head -20 || echo NO_ALSA_UTILS')
run('cat /proc/asound/cards 2>/dev/null || echo NO_CARDS')

print('\n' + '='*55)
print('2. ALSA 默认配置')
print('='*55)
run('cat ~/.asoundrc 2>/dev/null || echo NO_LOCAL_ASOUND')
run('cat /etc/asound.conf 2>/dev/null | head -20 || echo NO_SYS_ASOUND')
run('speaker-test -c1 -t sine -l1 2>&1 | head -10 || echo NO_SPEAKER_TEST')

print('\n' + '='*55)
print('3. 系统工具 (espeak / ffmpeg / portaudio)')
print('='*55)
run('which espeak 2>/dev/null && espeak --version 2>&1 | head -2 || echo NO_ESPEAK')
run('arecord --version 2>&1 | head -1 || echo NO_ARECORD')
run('aplay --version 2>&1 | head -1 || echo NO_APLAY')
run('dpkg -l | grep -i portaudio 2>/dev/null || echo NO_PORTAUDIO_PKG')
run('dpkg -l | grep -i libportaudio 2>/dev/null || echo NO_LIBPORTAUDIO')
run('ldconfig -p | grep -i portaudio 2>/dev/null || echo NO_LIBPORTAUDIO_SO')

print('\n' + '='*55)
print('4. Python 包')
print('='*55)
run('python3 -c "import sounddevice; print(f\'sounddevice OK {sounddevice.__version__}\')" 2>/dev/null || echo NO_SOUNDDEVICE')
run('python3 -c "import pyaudio; print(f\'pyaudio OK {pyaudio.__version__}\')" 2>/dev/null || echo NO_PYAUDIO')
run('python3 -c "import pyttsx3; print(f\'pyttsx3 OK {pyttsx3.__version__}\')" 2>/dev/null || echo NO_PYTTSX3')

print('\n' + '='*55)
print('5. 列出 Python 看到的音频设备 (sounddevice)')
print('='*55)
run('python3 -c "import sounddevice as sd; print(sd.query_devices())" 2>&1 || echo FAIL')
run('python3 -c "import sounddevice as sd; print(\'default_in=\', sd.default.device[0]); print(\'default_out=\', sd.default.device[1])" 2>&1 || echo FAIL')

print('\n' + '='*55)
print('6. 5秒录音测试 (arecord, 需接USB mic)')
print('='*55)
run('rm -f /tmp/test_rec.wav')
run('timeout 6 arecord -D hw:0 -c1 -r16000 -f S16_LE -d 5 /tmp/test_rec.wav 2>&1 || echo NO_HW0')
run('ls -la /tmp/test_rec.wav 2>/dev/null && file /tmp/test_rec.wav || echo REC_FAIL')

print('\n' + '='*55)
print('7. espeak 测试语音播放')
print('='*55)
run('espeak -v zh+f "你好,我是小宝" --stdout | aplay 2>&1 | tail -5 || echo ESPEAK_FAIL')

print('\n' + '='*55)
print('8. sounddevice 播放测试 (纯正弦波 1s)')
print('='*55)
run("""python3 -c "
import numpy as np
try:
    import sounddevice as sd
    fs = 16000
    t = np.linspace(0, 1, fs)
    wav = 0.3 * np.sin(2*np.pi*440*t).astype(np.float32)
    sd.play(wav, fs)
    sd.wait()
    print('✅ sounddevice 播放 OK')
except Exception as e:
    print(f'❌ {e}')
" 2>&1""")

print('\n' + '='*55)
print('9. sounddevice 录音 3s 测试')
print('='*55)
run("""python3 -c "
try:
    import sounddevice as sd
    import numpy as np
    fs = 16000
    print('录音中 3 秒, 请对着麦克风说话...')
    rec = sd.rec(int(3*fs), samplerate=fs, channels=1, dtype='float32')
    sd.wait()
    vol = np.abs(rec).max()
    print(f'✅ 录音 OK, peak volume = {vol:.3f}')
    if vol < 0.01:
        print('  ⚠️ 音量很小, 检查麦克风连接')
except Exception as e:
    print(f'❌ {e}')
" 2>&1""")

print('\n' + '='*55)
print('10. 装系统库 (先探测 sudo)')
print('='*55)
run('sudo -n apt list --installed 2>/dev/null | head -1; echo exit=$?')

c.close()
