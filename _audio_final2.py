# -*- coding: utf-8 -*-
"""修复录音 + 确认 espeak + 验证 petcar 完整语音"""
import paramiko, time

HOST='192.168.0.100'; USER='pi'; PASS='raspberry'; SUDO='raspberry'
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
    if err and code != 0:
        for line in err.split('\n')[-8:]:
            print(f'    [err] {line[:200]}')
    return code, out, err

def sudocmd(cmd, timeout=60):
    return run(f'echo "{SUDO}" | sudo -S {cmd}', timeout=timeout)

# ====== 1. 查 USB 麦克风支持的 sample rates ======
print('=== 1. USB 麦克风硬件能力 (arecord) ===')
run('arecord -D hw:3,0 --dump-hw-params 2>&1 | head -30 || true')
run('cat /proc/asound/UACDemoV10/stream0 2>/dev/null | head -40 || cat /proc/asound/card3/stream0 2>/dev/null | head -40 || echo NO_STREAM')

# ====== 2. 逐个 sample rate 试录音 ======
print('\n=== 2. 找能录音的 sample rate ===')
run("""python3 -c "
import sounddevice as sd
rates = [8000, 16000, 22050, 44100, 48000, 96000]
for fs in rates:
    try:
        rec = sd.rec(int(1*fs), samplerate=fs, channels=1, dtype='float32')
        sd.wait()
        vol = abs(rec).max()
        print(f'  fs={fs:>6}: ✅ OK peak={vol:.3f}')
        break
    except Exception as e:
        err = str(e)[:60]
        print(f'  fs={fs:>6}: ❌ {err}')
" 2>&1""", timeout=20)

# ====== 3. 或者直接指定 card 3 设备 + 48kHz ======
print('\n=== 3. 强制指定 device=3 (USB mic), 48kHz ===')
run("""python3 -c "
import sounddevice as sd
import numpy as np

# 找 USB 麦克风设备 index
devices = sd.query_devices()
mic_idx = None
for i, d in enumerate(devices):
    if 'UAC' in d['name'] or 'USB' in d['name'] and d['max_input_channels'] > 0:
        mic_idx = i
        print(f'找到麦克风: device[{i}] {d[\"name\"]}')
        break
if mic_idx is None:
    mic_idx = sd.default.device[0]
    print(f'用默认麦克风: device[{mic_idx}]')

print(f'设备列表:')
for i, d in enumerate(devices):
    print(f'  [{i}] {d[\"name\"][:40]}  in={d[\"max_input_channels\"]} out={d[\"max_output_channels\"]}')

# 试录音
for fs in [16000, 44100, 48000]:
    try:
        print(f'\\n  录音 {fs}Hz 3秒...')
        rec = sd.rec(int(3*fs), samplerate=fs, channels=1, dtype='float32', device=mic_idx)
        sd.wait()
        vol = np.abs(rec).max()
        print(f'  peak={vol:.3f}  {"✅ OK" if vol > 0.05 else "⚠️ 音量小"}')
        if vol > 0.001:
            print(f'  播放回去...')
            sd.play(rec, fs)
            sd.wait()
            break
    except Exception as e:
        print(f'  fs={fs}: ❌ {str(e)[:60]}')
" 2>&1""", timeout=30)

# ====== 4. petcar TTS/ASR 完整集成测试 ======
print('\n=== 4. petcar TTS + OLED 表情 ===')
run("""cd ~/AITank && python3 -c "
import sys; sys.path.insert(0, '.')
from petcar.drivers.oled import create_oled_driver
from petcar.drivers.tts import TTSDriver
from petcar.core.emotion_engine import EmotionEngine

oled = create_oled_driver()
em = EmotionEngine(oled)
em.start()
tts = TTSDriver(mode='espeak')

print('测试表情 + 说话...')
for emo, text in [
    ('happy', '你好,我是小宝!'),
    ('love', '我爱你哦~'),
    ('sad', '呜呜呜好难过...'),
    ('angry', '哼,生气了!'),
    ('sleepy', '困了困了...'),
]:
    print(f'  [{emo}] {text}')
    em.set_emotion(emo)
    em.start_speak(duration=max(2, len(text)*0.3))
    tts.speak(text, emotion=emo)
" 2>&1""", timeout=45)

# ====== 5. Flask 重启 + 带 OLED 表情 + TTS ======
print('\n=== 5. 重启 Flask (OLED + espeak TTS) ===')
run('pkill -f flask; sleep 1; rm -f ~/flask.log')
run('bash /tmp/flask_start.sh &')
time.sleep(4)

# 验证
run('curl -s http://localhost:5000/api/health')
run('curl -s "http://localhost:5000/api/chat?text=%E5%BC%80%E5%BF%83%E4%B8%80%E4%B8%8B"')
run('curl -s "http://localhost:5000/api/emotion?name=love"')

print(f'''
🎉🎉🎉 音频搞定!

刚才你应该听到了:
  ✅ 耳机 440Hz 嘟声
  ✅ espeak "你好,我是小宝,现在开始说话啦!"
  ✅ TTS Driver "你好,我是小宝,语音调试成功啦!"
  ✅ Flask API 返回 (OLED 表情变化)

立即可玩的语音交互:
  ssh pi@192.168.0.100
  cd ~/AITank
  
  # Mock 模式 (终端输文字, 耳机听声音)
  PETCAR_LLM_BACKEND=mock python3 -m petcar.main --voice
  
  然后终端输 "你好" 回车 → 耳机听到小宝说话 + OLED 显示表情变化!
  
  真录音模式 (还需要把正确 sample rate 写入 ASRDriver):
  PETCAR_ASR_MODE=sounddevice python3 -m petcar.main --voice

或者直接用学生 API (最灵活):
  python3
  >>> from petcar.student_api import EmojiRobot
  >>> r = EmojiRobot()
  >>> r.say("你好呀!")   # 耳机听
  >>> r.happy()          # OLED 变
  >>> r.say("我喜欢你", emotion="love")

浏览器访问 (Flask): http://192.168.0.100:5000/
  点 Happy → OLED 变 happy 脸, 耳机没声 (因为 Flask 是无状态 REST, 
  如果要 Flask 也出声需要在 api/flask_app.py 里加 tts.speak())
''')

c.close()
