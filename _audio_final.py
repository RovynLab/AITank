# -*- coding: utf-8 -*-
"""
有 sudo 密码 raspberry 了! 一键装音频栈 + 验证
"""
import paramiko, time

HOST='192.168.0.100'; USER='pi'; PASS='raspberry'; SUDO='raspberry'

c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=15)

def run(cmd, timeout=60):
    print(f'\n$ {cmd[:90]}')
    _, so, se = c.exec_command(cmd, timeout=timeout)
    out = so.read().decode(errors='replace').strip()
    err = se.read().decode(errors='replace').strip()
    code = so.channel.recv_exit_status()
    if out:
        for line in out.split('\n')[-12:]:
            print(f'    {line}')
    if err and code != 0:
        for line in err.split('\n')[-6:]:
            print(f'    [err] {line[:200]}')
    return code, out, err

def sudocmd(cmd, timeout=120):
    """带密码的 sudo"""
    full = f'echo "{SUDO}" | sudo -S {cmd}'
    return run(full, timeout=timeout)

# ====== 1. sudo 验证 ======
print('=== 1. sudo 验证 ===')
run(f'echo "{SUDO}" | sudo -S id')

# ====== 2. apt 装系统库 ======
print('\n=== 2. apt install ===')
sudocmd('apt-get update -y', timeout=90)
sudocmd('apt-get install -y libportaudio2 portaudio19-dev espeak libsndfile1 libasound2-dev', timeout=180)

# ====== 3. espeak 验证 ======
print('\n=== 3. espeak 验证 ===')
run('which espeak && espeak --version')

# ====== 4. ALSA 默认设备 ======
print('\n=== 4. ALSA 配置 ~/.asoundrc ===')
# 重新写一个简洁版本
asound = r'''# 耳机输出 (card 2)
defaults.pcm.card 2
defaults.pcm.device 0
defaults.ctl.card 2

pcm.!default {
    type plug
    slave { pcm "hw:2,0" }
}
'''
sftp = c.open_sftp()
with sftp.file('/home/pi/.asoundrc', 'w') as f:
    f.write(asound)
sftp.close()
run('cat ~/.asoundrc')

# ====== 5. sounddevice ======
print('\n=== 5. sounddevice ===')
run('pip3 install --break-system-packages --force-reinstall sounddevice 2>&1 | tail -3', timeout=60)
run("""python3 -c "
import sounddevice as sd
print(f'sounddevice OK {sd.__version__}')
print('--- 设备列表 ---')
for i, d in enumerate(sd.query_devices()):
    print(f'  [{i}] {d[\"name\"]} (in={d[\"max_input_channels\"]}, out={d[\"max_output_channels\"]})')
print(f'默认 in: {sd.default.device[0]}')
print(f'默认 out: {sd.default.device[1]}')
" 2>&1""", timeout=15)

# ====== 6. 播放测试 (440Hz 正弦波) ======
print('\n=== 6. 播放测试 (440Hz 1秒, 耳机应该听到嘟) ===')
run("""python3 -c "
import numpy as np
import sounddevice as sd
fs = 44100
t = np.linspace(0, 1, fs)
wav = (0.4 * np.sin(2*np.pi*440*t)).astype(np.float32)
print('播放 440Hz 1秒... 看耳机响不响!')
sd.play(wav, fs)
sd.wait()
print('✅ 播放完成')
" 2>&1""", timeout=15)

# ====== 7. espeak 中文 TTS ======
print('\n=== 7. espeak 中文 TTS (耳机应该听到中文) ===')
run('espeak -v zh+f "你好,我是小宝,音频调试成功啦!" --stdout | aplay 2>&1 | tail -5', timeout=15)

# ====== 8. 录音测试 ======
print('\n=== 8. 录音 3秒 (USB 麦克风, 对着说话!) ===')
run("""python3 -c "
import numpy as np
import sounddevice as sd
fs = 16000
print('录音 3 秒... 请对着麦克风说话!')
rec = sd.rec(int(3*fs), samplerate=fs, channels=1, dtype='float32')
sd.wait()
vol = np.abs(rec).max()
print(f'peak volume = {vol:.3f}  (小于 0.05 = 麦克风没收到)')
print('播放回去...')
sd.play(rec, fs)
sd.wait()
print('✅ 完成')
" 2>&1""", timeout=15)

# ====== 9. arecord 5秒 wav ======
print('\n=== 9. arecord 5秒 wav (card 3 USB mic) ===')
run('rm -f /tmp/test_rec.wav')
run('arecord -D hw:3,0 -c1 -r48000 -f S16_LE -d 5 /tmp/test_rec.wav 2>&1', timeout=12)
run('ls -la /tmp/test_rec.wav && file /tmp/test_rec.wav')
run('aplay /tmp/test_rec.wav 2>&1 | tail -3', timeout=10)

print(f'''
🎉 音频调试完成!

sudo 密码: raspberry

如果都 OK, 现在就能:

  耳机出声 ✅: espeak / sounddevice / speaker-test
  麦克风录音 ✅: arecord -D hw:3,0 / sounddevice
  petcar 语音交互:
    ssh pi@192.168.0.100
    cd ~/AITank
    PETCAR_LLM_BACKEND=mock python3 -m petcar.main --voice
    (然后终端输文字回车, MockASR, 就能听到小宝说话!)

  真正语音交互 (ASR=sounddevice 录音):
    # config.py 里改 ASR_MODE = "sounddevice" 或改环境变量
    PETCAR_ASR_MODE=sounddevice PETCAR_TTS_MODE=espeak python3 -m petcar.main --voice

  或者 SSH 进去手动交互:
    python3
    >>> from petcar.student_api import EmojiRobot
    >>> r = EmojiRobot()
    >>> r.say("你好呀!")     # 耳机应该听到
    >>> r.happy()             # OLED 应该变
''')

c.close()
