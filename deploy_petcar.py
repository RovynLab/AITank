# -*- coding: utf-8 -*-
"""
deploy_petcar.py — 一键部署 AI-PetCar 到树莓派
=============================================
步骤:
  1. 推 petcar/ 目录
  2. pip 装依赖 (用户级, 不需要 sudo)
  3. 装 ollama 到 ~/bin (不需要 sudo)
  4. 拉 qwen2.5:1.5b 模型
  5. 冒烟测试

python deploy_petcar.py all
python deploy_petcar.py push       # 只推代码
python deploy_petcar.py deps       # 只装 pip 依赖
python deploy_petcar.py ollama     # 只装 ollama + 模型
python deploy_petcar.py test       # 冒烟测试
"""
import sys, os, time, json
from pathlib import Path
import paramiko
from scp import SCPClient

# ---------- 连接 ----------
HOST = "10.1.1.112"
USER = "pi"
PASS = "raspberrypi"          # 如果 sudo 密码不同也没关系, pip 和 ollama 都不需要 sudo
LOCAL_ROOT = r"e:\work\AITank"
REMOTE_ROOT = f"/home/{USER}/AITank"

# ---------- 工具 ----------
def ssh_connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASS, timeout=15)
    print(f"[OK] SSH → {USER}@{HOST}")
    return c

def run(c, cmd, timeout=60):
    print(f"\n  $ {cmd[:90]}")
    _, so, se = c.exec_command(cmd, timeout=timeout)
    out = so.read().decode(errors="replace").strip()
    err = se.read().decode(errors="replace").strip()
    code = so.channel.recv_exit_status()
    if out:
        for line in out.split('\n')[-8:]:   # 只显示末尾几行
            print(f"    {line}")
    if err and code != 0:
        print(f"    [err] {err[:200]}")
    if code != 0:
        print(f"    [WARN] exit={code}")
    return code, out, err

def scp_dir(c, local_dir, remote_parent):
    """推整个目录"""
    scp = SCPClient(c.get_transport(), socket_timeout=60)
    try:
        name = os.path.basename(local_dir)
        # 远端先清掉旧的
        run(c, f"rm -rf {remote_parent}/{name}", timeout=10)
        scp.put(local_dir, remote_parent, recursive=True)
        print(f"  [OK] 目录推送 {name}")
    finally:
        scp.close()

# ---------- 1. 推代码 ----------
def step_push(c):
    print("\n" + "="*60)
    print("[1/5] 推 petcar 代码")
    print("="*60)
    local = os.path.join(LOCAL_ROOT, "petcar")
    run(c, f"mkdir -p {REMOTE_ROOT}", timeout=10)
    scp_dir(c, local, REMOTE_ROOT)
    # scp 不保留可执行位，这里补上 start.sh 等脚本的 +x
    run(c, f"chmod +x {REMOTE_ROOT}/petcar/*.sh 2>/dev/null || true", timeout=10)
    run(c, f"ls -la {REMOTE_ROOT}/petcar/", timeout=10)

# ---------- 2. pip 依赖 ----------
def step_deps(c):
    print("\n" + "="*60)
    print("[2/5] pip 装 petcar 依赖 (用户级, 无需 sudo)")
    print("="*60)
    cmds = [
        "pip3 install --break-system-packages --upgrade pip",
        "pip3 install --break-system-packages Pillow luma.oled schedule pyttsx3 requests",
        # sounddevice 需要 libportaudio2 (系统库) — 用户级 pip 装了也跑不起来
        # 但 sounddevice 纯 Python 层可装, 运行时会 fallback
        "pip3 install --break-system-packages sounddevice pyaudio 2>&1 | tail -3",
        # faster-whisper 需要 libsndfile1 (系统库), 但可以先 pip 装 wheel
        # 树莓派 4B 上 small 太慢, 先装 tiny
        "pip3 install --break-system-packages faster-whisper 2>&1 | tail -3",
    ]
    for cmd in cmds:
        run(c, cmd, timeout=180)
    # 验证
    print("\n  --- 验证 ---")
    run(c, 'python3 -c "import luma; print(\'  luma.oled OK\')"')
    run(c, 'python3 -c "import PIL; print(\'  Pillow OK\')"')
    run(c, 'python3 -c "import flask; print(\'  Flask OK\')"')
    run(c, 'python3 -c "import sounddevice; print(\'  sounddevice OK\')"')
    run(c, 'python3 -c "import pyttsx3; print(\'  pyttsx3 OK\')"')
    # petcar 自身 import
    run(c, f'cd {REMOTE_ROOT} && python3 -c "import sys; sys.path.insert(0, \'.\'); from petcar import config; from petcar.core.chat_agent import ChatAgent; print(\'  petcar import OK\')"')

# ---------- 3. Ollama ----------
def step_ollama(c):
    print("\n" + "="*60)
    print("[3/5] 装 Ollama (用户级, 无需 sudo)")
    print("="*60)

    # 先看 ollama 架构
    run(c, "uname -m")  # aarch64 → arm64

    # 创建 ~/bin
    run(c, "mkdir -p ~/bin")

    # 下载 ollama (ollama-linux-arm64)
    # 直接下官方 release 的二进制
    run(c, "curl -L https://ollama.com/download/ollama-linux-arm64 -o ~/bin/ollama", timeout=180)
    run(c, "chmod +x ~/bin/ollama")

    # 加到 PATH
    run(c, 'echo \'export PATH="$HOME/bin:$PATH"\' >> ~/.bashrc')

    # 验证
    _, out, _ = run(c, "~/bin/ollama --version")

    # 启动 ollama server (后台)
    print("\n  启动 Ollama server...")
    run(c, "pkill -f ollama 2>/dev/null; sleep 1; nohup ~/bin/ollama serve > ~/ollama.log 2>&1 &", timeout=10)
    time.sleep(3)
    run(c, "curl -s http://localhost:11434/api/tags || echo SERVER_DOWN")

    # 拉模型
    print("\n  拉 qwen2.5:1.5b (1.5GB, 约5分钟)...")
    run(c, "~/bin/ollama pull qwen2.5:1.5b", timeout=600)
    run(c, "~/bin/ollama list")

# ---------- 4. 冒烟测试 ----------
def step_test(c):
    print("\n" + "="*60)
    print("[4/5] 冒烟测试")
    print("="*60)

    # Test A: Ollama 快速对话
    print("\n  --- Test A: Ollama 直接对话 ---")
    _, out, _ = run(c, """curl -s http://localhost:11434/api/chat -d '{
  "model": "qwen2.5:1.5b",
  "stream": false,
  "messages": [{"role": "user", "content": "你好，说两个字就好"}]
}'""", timeout=60)
    try:
        data = json.loads(out)
        reply = data.get("message", {}).get("content", "")[:50]
        print(f"  ✅ Ollama 回复: {reply}")
    except Exception:
        print(f"  ❌ Ollama 解析失败: {out[:200]}")

    # Test B: petcar ChatAgent + Ollama
    print("\n  --- Test B: petcar ChatAgent + Ollama ---")
    run(c, f"""cd {REMOTE_ROOT} && PETCAR_LLM_BACKEND=ollama python3 -c "
import sys; sys.path.insert(0, '.')
from petcar.core.chat_agent import ChatAgent
from petcar.core.llm_backends import create_llm_backend
from petcar.core.skill_manager import SkillManager
from petcar.skills.emote import EmoteSkill
from petcar.skills.weather import WeatherSkill
from petcar.skills.move import MoveSkill
sm = SkillManager()
sm.register(EmoteSkill(None))
sm.register(WeatherSkill())
sm.register(MoveSkill(None))
llm = create_llm_backend()
chat = ChatAgent(backend=llm, skill_manager=sm)
r = chat.chat('你好，说句话介绍一下自己')
print(f'  emotion: {{r.emotion}}')
print(f'  reply: {{r.reply}}')
print(f'  tools: {{r.tools_called}}')
" """, timeout=90)

    # Test C: OLED 硬件检测
    print("\n  --- Test C: OLED I2C 扫描 ---")
    run(c, "i2cdetect -y 1 2>/dev/null || echo NO_I2C_DETECT")
    run(c, f"""cd {REMOTE_ROOT} && timeout 5 python3 -c "
import sys; sys.path.insert(0, '.')
from petcar.drivers.oled import OLEDDriver
try:
    drv = OLEDDriver(address=0x3C)
    drv.show_expression('happy')
    print('  ✅ OLED 硬件点亮成功!')
except Exception as e:
    print(f'  ⚠️  OLED 不可用: {{e}}')
" 2>&1 || true""", timeout=15)

# ---------- main ----------
STEPS = {
    "push":   step_push,
    "deps":   step_deps,
    "ollama": step_ollama,
    "test":   step_test,
}

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    c = ssh_connect()
    try:
        if mode == "all":
            for s in ["push", "deps", "ollama", "test"]:
                STEPS[s](c)
        elif mode in STEPS:
            STEPS[mode](c)
        else:
            print(f"未知 mode: {mode}")
            print(f"可选: all / {list(STEPS.keys())}")
    finally:
        c.close()
        print("\n[SSH] 已断开")

if __name__ == "__main__":
    main()
