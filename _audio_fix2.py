# -*- coding: utf-8 -*-
"""磁盘清理 + 装音频库 + 验证"""
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
        for line in out.split('\n')[-15:]:
            print(f'    {line}')
    if err:
        for line in err.split('\n')[-8:]:
            print(f'    [err] {line[:300]}')
    return code, out, err

def sudocmd(cmd, timeout=60):
    return run(f'echo "{SUDO}" | sudo -S {cmd}', timeout=timeout)

# ====== 1. 查磁盘 ======
print('='*55)
print('[1] 磁盘状态')
print('='*55)
run('df -h / && df -h /tmp && df -h /home/pi')
run('du -sh ~/AITank ~/ollama* ~/install* ~/ollama_dl.log /tmp/ollama* 2>/dev/null')
run('du -sh ~/.local ~/.cache 2>/dev/null')

# ====== 2. 清空间 ======
print('\n' + '='*55)
print('[2] 清空间')
print('='*55)

# 删 Ollama 下载的半成品 (121MB, 而且下载卡死了)
run('rm -f /tmp/ollama-linux-arm64.tar.zst /tmp/ollama 2>/dev/null')
run('rm -f ~/ollama_dl.log ~/ollama.log ~/install.log ~/install.out ~/ollama.pid 2>/dev/null')
run('rm -rf ~/.ollama 2>/dev/null')

# 清 pip cache
run('rm -rf ~/.cache/pip 2>/dev/null')

# 清 apt cache
sudocmd('apt-get clean', timeout=30)
sudocmd('rm -rf /var/lib/apt/lists/*', timeout=10)

# 清 journal
sudocmd('journalctl --vacuum-time=1d 2>&1 | tail -3', timeout=15)

run('df -h / && df -h /home/pi')

# ====== 3. apt update + install ======
print('\n' + '='*55)
print('[3] apt update + install PortAudio + espeak')
print('='*55)
sudocmd('apt-get update -y', timeout=120)
sudocmd('apt-get install -y libportaudio2 portaudio19-dev espeak libsndfile1 libasound2-dev', timeout=180)

# ====== 4. 验证 ======
print('\n' + '='*55)
print('[4] 验证系统库')
print('='*55)
run('which espeak && espeak --version')
run('dpkg -l | grep -E "libportaudio|espeak|libsndfile" 2>/dev/null | grep ^ii')
run('ldconfig -p | grep portaudio 2>/dev/null || echo "no ldconfig, try ldconfig via sudo"')
sudocmd('ldconfig && ldconfig -p | grep portaudio | head -3', timeout=10)

# ====== 5. Python 验证 ======
print('\n' + '='*55)
print('[5] Python sounddevice 验证')
print('='*55)
run("""python3 -c "
import sounddevice as sd
print(f'sounddevice OK {sd.__version__}')
print('--- 音频设备 ---')
for i, d in enumerate(sd.query_devices()):
    print(f'  [{i}] {d[\"name\"]}  in={d[\"max_input_channels\"]} out={d[\"max_output_channels\"]}')
print(f'默认 in: {sd.default.device[0]}')
print(f'默认 out: {sd.default.device[1]}')
" 2>&1""", timeout=15)

# ====== 6. 播放测试 ======
print('\n' + '='*55)
print('[6] 耳机播放 440Hz 1秒 (听嘟声!)')
print('='*55)
run("""python3 -c "
import numpy as np
import sounddevice as sd
fs = 44100
wav = 0.4 * np.sin(2*np.pi*440*np.linspace(0,1,fs)).astype(np.float32)
print('▶ 播放 440Hz 嘟 1秒... 看耳机响不响!')
sd.play(wav, fs)
sd.wait()
print('✅ 播放完')
" 2>&1""", timeout=15)

# ====== 7. espeak 中文 ======
print('\n' + '='*55)
print('[7] espeak 中文 TTS')
print('='*55)
run('espeak -v zh+f "你好,我是小宝,现在开始说话啦!" --stdout | aplay 2>&1 | tail -3', timeout=15)

# ====== 8. 录音 ======
print('\n' + '='*55)
print('[8] USB 麦克风录音 3秒 (请说话!)')
print('='*55)
run("""python3 -c "
import numpy as np
import sounddevice as sd
fs = 16000
print('🎙️ 录音 3 秒, 请对着 USB 麦克风说话!')
rec = sd.rec(int(3*fs), samplerate=fs, channels=1, dtype='float32')
sd.wait()
vol = np.abs(rec).max()
print(f'peak volume = {vol:.3f}  (>0.05 = 麦克风 OK)')
print('▶ 播放回去...')
sd.play(rec, fs)
sd.wait()
print('✅ 完成')
" 2>&1""", timeout=20)

# ====== 9. petcar TTS ======
print('\n' + '='*55)
print('[9] petcar TTS Driver')
print('='*55)
run("""cd ~/AITank && python3 -c "
import sys; sys.path.insert(0, '.')
from petcar.drivers.tts import TTSDriver
tts = TTSDriver(mode='espeak')
print(f'TTS mode: {tts.mode}')
tts.speak('你好,我是小宝,语音调试成功啦!', emotion='happy')
print('✅ TTS 播放')
" 2>&1""", timeout=15)

print(f'''
🎉 音频搞定!

立即可玩:
  ssh pi@192.168.0.100
  cd ~/AITank
  # MockASR + espeak TTS + Flask 已好的
  PETCAR_LLM_BACKEND=mock python3 -m petcar.main --voice
  # 或者只跑 Flask (已经在跑了): http://192.168.0.100:5000/
  # 学生 API:
  python3
  >>> from petcar.student_api import EmojiRobot
  >>> r = EmojiRobot()
  >>> r.say("你好呀!")   # 耳机听
  >>> r.happy()          # OLED 变

  真语音交互 (ASR=sounddevice 录音):
  PETCAR_ASR_MODE=sounddevice PETCAR_TTS_MODE=espeak python3 -m petcar.main --voice
''')

c.close()
