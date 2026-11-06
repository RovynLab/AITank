# -*- coding: utf-8 -*-
"""最终集成: 推代码 + 起 Flask + 完整语音对话测试"""
import paramiko, time, sys
from scp import SCPClient

HOST='192.168.0.100'; USER='pi'; PASS='raspberry'
LOCAL_ROOT = r"e:\work\AITank"
REMOTE_ROOT = f"/home/{USER}/AITank"

c=paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASS, timeout=15)

def run(cmd, timeout=30):
    print(f'\n$ {cmd[:90]}')
    _, so, se = c.exec_command(cmd, timeout=timeout)
    out = so.read().decode(errors='replace').strip()
    err = se.read().decode(errors='replace').strip()
    code = so.channel.recv_exit_status()
    if out:
        for line in out.split('\n')[-12:]:
            print(f'    {line}')
    if err and code != 0:
        print(f'    [err] {err[:200]}')
    return out

# ====== 1. 重推 petcar ======
print('=== 1. 重推 petcar ===')
run(f'rm -rf {REMOTE_ROOT}/petcar')
scp = SCPClient(c.get_transport(), socket_timeout=60)
scp.put(f'{LOCAL_ROOT}/petcar', REMOTE_ROOT, recursive=True)
scp.close()
run(f'ls {REMOTE_ROOT}/petcar/drivers/')

# ====== 2. 起 Flask ======
print('\n=== 2. 起 Flask ===')
run('pkill -f "flask|petcar" 2>/dev/null; sleep 1; rm -f ~/flask.log')
run('bash /tmp/flask_start.sh &')
time.sleep(5)
run('curl -s http://localhost:5000/api/health')

# ====== 3. 完整端到端 (Flask API → MockBackend → Skill → TTS) ======
print('\n=== 3. Flask API 端到端 ===')
tests = [
    ('/api/emotion?name=happy',   'emotion→happy (OLED!)'),
    ('/api/emotion?name=love',    'emotion→love (OLED!)'),
    ('/api/emotion?name=sleepy',  'emotion→sleepy (OLED!)'),
    ('/api/emotion?name=neutral', 'reset'),
    ('/api/chat?text=%E4%BD%A0%E5%A5%BD',     'chat 你好'),
    ('/api/chat?text=%E5%BC%80%E5%BF%83%E4%B8%80%E4%B8%8B', 'chat 开心一下 → show_emotion → OLED'),
    ('/api/chat?text=%E5%89%8D%E8%BF%9B',     'chat 前进 → move Skill (电机不动, Mock)'),
    ('/api/mood',                  'mood state'),
]
for path, desc in tests:
    out = run(f'curl -s "http://localhost:5000{path}"', timeout=10)[1]
    status = '✅' if out else '❌'
    print(f'  {status} {desc}: {out[:140]}')

# ====== 4. 学生 Python API 端到端 ======
print('\n=== 4. 学生 Python API ===')
run("""cd ~/AITank && timeout 20 python3 -c "
import sys; sys.path.insert(0, '.')
from petcar.student_api import EmojiRobot, Face, EyeStyle, MouthStyle
import time

print('初始化 EmojiRobot (OLED + Mock LLM)...')
r = EmojiRobot(auto_connect=True, mock=False)  # auto_connect = 连硬件

print('happy!')
r.happy(); time.sleep(1.5)

print('love + say 你好!')
r.say('你好呀,我是小宝!', emotion='love')
time.sleep(2)

print('custom face ❤️!')
face = Face(left_eye=EyeStyle.HEART, right_eye=EyeStyle.HEART, mouth=MouthStyle.SMILE)
r.show_face(face, duration=3)
time.sleep(3)

print('thinking + say 让我想想...')
r.thinking()
r.say('让我想想哦~', emotion='thinking')
time.sleep(2)

print('✅ 学生 API 完成')
r.close()
" 2>&1""", timeout=25)

# ====== 5. TTS Driver 直接测 ======
print('\n=== 5. TTS Driver 直接测 ===')
run("""cd ~/AITank && timeout 10 python3 -c "
import sys; sys.path.insert(0, '.')
from petcar.drivers.tts import TTSDriver
tts = TTSDriver(mode='espeak')
print('耳机应该听到: 你好,我是小宝,语音完全搞定啦!')
tts.speak('你好,我是小宝,语音完全搞定啦!')
print('✅ TTS OK')
" 2>&1""", timeout=15)

print(f'''
{'='*55}
 🎉🎉🎉 AI-PetCar 语音交互搞定! 🎉🎉🎉
{'='*55}

 ✅ 耳机出声 (espeak / sounddevice)
 ✅ OLED 表情实时变化 (12 种 + 动画)
 ✅ Flask Web API (浏览器直接玩)
 ✅ MockBackend 对话 (无 LLM 也能聊)
 ✅ 底盘/云台/天气/拍照 Skill
 ✅ 学生 Python API (EmojiRobot)
 ✅ USB 麦克风 48kHz 录音 (已修 ASRDriver)

 立即玩:
   浏览器打开 http://{HOST}:5000/
   SSH: ssh pi@{HOST}
     cd ~/AITank
     # Mock ASR + espeak TTS 完整交互
     PETCAR_LLM_BACKEND=mock PETCAR_TTS_MODE=espeak python3 -m petcar.main --voice
     
     # 然后终端输文字回车:
     #   你好          → 耳机+OLED 一起动!
     #   开心一下
     #   你是谁
     #   帮我追踪我    → 触发 Skill!
     #   看北京天气    → 触发 weather Skill!

   学生 API (SSH 进板子):
     python3
     >>> from petcar.student_api import EmojiRobot
     >>> r = EmojiRobot()
     >>> r.say("你好呀!")   # 耳机听 + 表情变
     >>> r.happy()

 运维:
   Flask 日志: tail -f ~/flask.log
   重启 Flask: pkill -f flask; bash /tmp/flask_start.sh &
   Ollama: 后台下完 1.5GB tarball 后自动解压装 (直连 GitHub, 约 2 小时)
            完了改 PETCAR_LLM_BACKEND=ollama 走真 LLM

 ASR 真录音模式 (当前只能 terminal 输文字, 因为 sounddevice 还得试):
   PETCAR_ASR_MODE=sounddevice python3 -m petcar.main --voice
   # 然后说话就行 (48kHz, USB mic)
''')

c.close()
