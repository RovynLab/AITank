# -*- coding: utf-8 -*-
"""
petcar/main.py — AI-PetCar 主程序入口
======================================

启动流程:
  1. OLED 显示 loading 旋转动画（立即替换 menu 残留画面）
  2. multiprocessing 起占位 HTTP server（fork context，不 spawn）
     - GET  / /dashboard  → loading HTML（spinner + 进度条 + 阶段文案）
     - GET  /api/init      → 从 Queue 拉状态返回（JSON）
  3. 主线程同步初始化所有模块（whisper base 约 2-3 分钟）
     → 期间浏览器访问看到 loading 页 + 进度条实时更新
  4. 初始化完 → 推 ready → terminate 占位子进程
  5. 起真 Flask（完整 modules），监听同一端口
     - /api/init 注册（读主进程 _INIT_STATUS dict，ready=True）
     - 首页 ready gate 通过
  6. 浏览器下一次 poll 拿到 ready=true → 自动跳 /dashboard
"""

from __future__ import annotations

import sys, os, time, argparse, threading, multiprocessing as mp
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar import config


# ============================================================================
# 全局 init 状态
# ============================================================================
_STAGE_PROGRESS = {
    "starting":        5,
    "connecting":     25,
    "waiting_whisper": 40,
    "loading_skills":  65,
    "loading_llm":     85,
    "ready":          100,
}

_INIT_STATUS: dict = {"ready": False, "stage": "starting", "progress": 5}
_INIT_FILE = "/tmp/petcar_init.json"   # fork 子进程从文件读状态，避免 mp.Queue 不可靠

def _set_stage(stage: str):
    _INIT_STATUS["stage"] = stage
    _INIT_STATUS["progress"] = _STAGE_PROGRESS.get(stage, 0)
    print(f"[Init] {stage} ({_INIT_STATUS['progress']}%)")
    try:
        import json as _j
        with open(_INIT_FILE, "w") as f:
            _j.dump(_INIT_STATUS, f)
    except Exception:
        pass


def _build_loading_html(pet_name: str) -> str:
    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{pet_name} Loading...</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{min-height:100vh;display:flex;align-items:center;justify-content:center;background:#0a0e17;color:#e0e8ff;font-family:-apple-system,Segoe UI,Roboto,sans-serif}}
.box{{text-align:center;padding:40px;min-width:320px}}
.spinner{{width:72px;height:72px;border-radius:50%;border:6px solid rgba(120,160,255,.15);border-top-color:#5a9dff;animation:spin 1s linear infinite;margin:0 auto 28px}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
h1{{font-size:22px;margin-bottom:6px;color:#fff}}
.sub{{font-size:13px;color:#7b8ba8;margin-bottom:28px}}
.bar-wrap{{width:100%;height:10px;background:rgba(120,160,255,.12);border-radius:6px;overflow:hidden;margin-bottom:14px}}
.bar{{height:100%;width:0%;background:linear-gradient(90deg,#5a9dff,#7fc0ff);border-radius:6px;transition:width .4s ease-out}}
.bar.done{{background:linear-gradient(90deg,#4ade80,#86efac)}}
.pct{{font-size:12px;color:#9ab;opacity:.85}}
#stage{{font-size:14px;color:#b9c7de;margin-top:18px;min-height:20px}}
.dot{{animation:dot 1.4s infinite both;display:inline-block}}
.dot:nth-child(2){{animation-delay:.2s}}.dot:nth-child(3){{animation-delay:.4s}}
@keyframes dot{{0%{{opacity:.2}}20%{{opacity:1}}100%{{opacity:.2}}}}
</style></head><body>
<div class="box">
  <div class="spinner" id="spinner"></div>
  <h1>{pet_name}<span class="dot">.</span><span class="dot">.</span><span class="dot">.</span></h1>
  <p class="sub">启动中，请稍候...</p>
  <div class="bar-wrap"><div class="bar" id="bar"></div></div>
  <div class="pct"><span id="pct">0</span>%</div>
  <div id="stage">启动中...</div>
</div>
<script>
async function poll(){{
  try{{
    const r = await fetch('/api/init',{{cache:'no-store'}});
    const j = await r.json();
    const pct = Math.max(0, Math.min(100, j.progress || 0));
    document.getElementById('pct').textContent = pct;
    document.getElementById('bar').style.width = pct + '%';
    const zh = {{
      starting:'启动中...',
      connecting:'加载基础模块...',
      waiting_whisper:'等待语音服务就绪...',
      loading_skills:'注册技能...',
      loading_llm:'连接 Ollama LLM...',
      ready:'就绪！'
    }};
    document.getElementById('stage').textContent = zh[j.stage] || j.stage || '';
    if(j.ready){{
      document.getElementById('spinner').style.borderTopColor = '#4ade80';
      document.getElementById('bar').classList.add('done');
      setTimeout(()=>location.href='/dashboard',800);
      return;
    }}
  }}catch(e){{}}
  setTimeout(poll, 1200);
}}
poll();
</script></body></html>"""


# ============================================================================
# 占位 HTTP server（子进程，fork context）
# ============================================================================
def _serve_loading(port: int, pet_name: str, init_file: str):
    """fork 出的子进程：极简 HTTP server，serve loading 页 + /api/init（从文件读状态）"""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json as _json

    HTML = _build_loading_html(pet_name)

    class _H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _resp(self, code, body, ct="text/html"):
            if isinstance(body, str): body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        def _get(self):
            try:
                with open(init_file) as f:
                    return _json.load(f)
            except Exception:
                return {"ready": False, "stage": "starting", "progress": 5}
        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/init":
                return self._resp(200, _json.dumps(self._get()), "application/json")
            if path in ("/", "/dashboard"):
                return self._resp(200, HTML, "text/html")
            return self._resp(503, b'{"error":"not ready"}', "application/json")

    try:
        HTTPServer(("0.0.0.0", port), _H).serve_forever()
    except Exception:
        pass


# ============================================================================
# 模块初始化
# ============================================================================
def _wait_whisper_service(timeout: float = 120.0) -> bool:
    """等 whisper_service 模型加载完。开机自启时 petcar 和 service 几乎同时拉起,
    service 加载模型要 60s 左右, 这里主动 poll 直到 ready 或超时。"""
    import requests
    url = config.WHISPER_SERVICE_URL.rstrip("/") + "/health"
    start = time.time()
    last_err = ""
    while time.time() - start < timeout:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200 and r.json().get("loaded"):
                elapsed = time.time() - start
                print(f"[Init] whisper_service ready ({elapsed:.1f}s)")
                return True
        except Exception as e:
            last_err = str(e)
        # 还没 ready 就等等, 每 2 秒 poll 一次
        time.sleep(2)
    print(f"[Init] ⚠️ whisper_service 超时 ({last_err}), ASR 可能不可用")
    return False


def _connect_all() -> dict:
    from petcar.drivers.oled import create_oled_driver
    from petcar.drivers.mecanum import MecanumDriver
    from petcar.drivers.ptz import PTZDriver
    from petcar.drivers.camera import CameraDriver
    from petcar.drivers.tts import TTSDriver
    from petcar.drivers.asr import ASRDriver

    _set_stage("connecting")
    oled = create_oled_driver()
    mecanum = MecanumDriver()
    ptz = PTZDriver(); ptz.init()
    camera = CameraDriver()
    tts = TTSDriver()

    _set_stage("waiting_whisper")
    _wait_whisper_service(timeout=120)
    asr = ASRDriver()

    from petcar.core.emotion_engine import EmotionEngine
    from petcar.core.mood_engine import MoodEngine
    from petcar.core.chat_agent import ChatAgent
    from petcar.core.llm_backends import create_llm_backend
    from petcar.core.skill_manager import SkillManager
    from petcar.core.voice_io import VoiceIO

    emotion = EmotionEngine(oled); emotion.start()
    mood = MoodEngine(emotion); mood.start()

    from petcar.skills.move import MoveSkill
    from petcar.skills.ptz import PTZSkill
    from petcar.skills.photo import PhotoSkill
    from petcar.skills.face_detect import FaceDetectSkill
    from petcar.skills.face_track import FaceTrackSkill
    from petcar.skills.weather import WeatherSkill
    from petcar.skills.alarm import AlarmSkill
    from petcar.skills.emote import EmoteSkill
    from petcar.skills.express import ExpressSkill, ExpressionPlayer

    _set_stage("loading_skills")
    action_player = ExpressionPlayer(mecanum, ptz)

    sm = SkillManager()
    sm.register(MoveSkill(mecanum))
    sm.register(PTZSkill(ptz))
    sm.register(PhotoSkill(camera))
    sm.register(FaceDetectSkill(camera))
    sm.register(FaceTrackSkill(camera, ptz))
    sm.register(WeatherSkill())
    sm.register(AlarmSkill())
    sm.register(EmoteSkill(emotion))
    sm.register(ExpressSkill(action_player))

    _set_stage("loading_llm")
    llm = create_llm_backend()
    chat = ChatAgent(backend=llm, mood_engine=mood, skill_manager=sm)

    voice = VoiceIO(asr=asr, tts=tts, chat=chat, emotion=emotion)

    # PIDTracker 只创建一次，同时注入 BlockRuntime 和 create_app
    pid_tracker = None
    if camera and ptz:
        try:
            from petcar.core.pid_tracker import PIDTracker
            pid_tracker = PIDTracker(camera, ptz)
            # 自动恢复面板持久化的 PID 参数 (重启不丢)
            restored = pid_tracker.load_params()
            p = pid_tracker.params()
            note = "已恢复持久化值" if restored else "使用硬编码默认"
            print(f"[Init] PIDTracker {note}: kp={p['kp']:.3f} 增益={p['kp']*25:.1f}")
        except Exception as e:
            print(f"[Init] PIDTracker 初始化失败: {e}")

    from petcar.blocks.runtime import BlockRuntime
    from petcar.blocks.service import BlockService
    block_service = BlockService(BlockRuntime(
        mecanum=mecanum, ptz=ptz, camera=camera, emotion=emotion, tts=tts,
        pid_tracker=pid_tracker,
    ))

    _set_stage("ready")
    return {
        "oled": oled, "mecanum": mecanum, "ptz": ptz,
        "camera": camera, "tts": tts, "asr": asr,
        "emotion": emotion, "mood": mood, "chat": chat,
        "voice": voice, "skill_manager": sm,
        "block_service": block_service, "action_player": action_player,
        "pid_tracker": pid_tracker,
    }


# ============================================================================
# main
# ============================================================================
def _stop_aitank_menu():
    """
    清理 aitank-menu，独占 OLED，三步走：
      1. SIGUSR1 → 优雅暂停 menu 的 OLED 渲染（若 menu 有 handler）
      2. SIGTERM/SIGKILL → 干掉所有 menu 进程（立即释放 I2C）
      3. sudo -S systemctl stop → 停掉 service 防止 systemd 自动重启

    sudo 密码从环境变量 SUDO_PASSWORD 读取，默认 "raspberry"（Raspberry Pi 默认）。
    """
    import signal as _sig
    import subprocess as _sp

    my_pid = os.getpid()
    sudo_pw = os.environ.get("SUDO_PASSWORD", "raspberry")

    def _find_menu_pids():
        """找真正的 menu python 进程，跳过自己和 bash wrapper"""
        try:
            out = _sp.run(
                ["pgrep", "-f", "aitank_menu.main"],
                capture_output=True, text=True, timeout=2,
            )
            # 再核对 /proc/*/cmdline 确认是 python3，不是 bash wrapper
            real_pids = []
            for pid in (out.stdout or "").split():
                pid = pid.strip()
                if not pid or int(pid) == my_pid:
                    continue
                try:
                    cmd = open(f"/proc/{pid}/cmdline").read().replace("\x00", " ")
                    if "aitank_menu.main" in cmd and "python" in cmd:
                        real_pids.append(int(pid))
                except Exception:
                    pass
            return real_pids
        except Exception:
            return []

    # ---- 步骤 1: SIGUSR1 优雅让路 ----
    for pid in _find_menu_pids():
        try:
            os.kill(pid, _sig.SIGUSR1)
            print(f"[Init] SIGUSR1 → menu({pid}) 暂停 OLED")
        except ProcessLookupError:
            pass

    # ---- 步骤 2: SIGTERM → SIGKILL 干掉 menu ----
    pids = _find_menu_pids()
    for pid in pids:
        try:
            os.kill(pid, _sig.SIGTERM)
        except ProcessLookupError:
            pass
    if pids:
        time.sleep(0.5)
        for pid in _find_menu_pids():  # 再查一次，防止新 menu 被 systemd 拉起来
            try:
                os.kill(pid, _sig.SIGKILL)
                print(f"[Init] SIGKILL → menu({pid})")
            except ProcessLookupError:
                pass

    # ---- 步骤 3: 停 systemd service 防重启 ----
    try:
        result = _sp.run(
            ["sudo", "-S", "systemctl", "stop", "aitank-menu.service"],
            input=(sudo_pw + "\n").encode(),
            capture_output=True, timeout=5,
        )
        if result.returncode == 0:
            print("[Init] systemctl stop aitank-menu.service ✓")
        else:
            # 密码错误或没有 sudo 权限 — 用 kill-loop 兜底
            print("[Init] systemctl stop 失败，启动 kill-loop 兜底...")
            def _kill_loop():
                import time as _t
                for _ in range(5):
                    for p in _find_menu_pids():
                        try: os.kill(p, _sig.SIGKILL)
                        except: pass
                    _t.sleep(0.5)
            threading.Thread(target=_kill_loop, daemon=True).start()
    except Exception as e:
        print(f"[Init] systemctl stop 异常: {e}")

    # 等 I2C 句柄释放
    time.sleep(0.4)


def main():
    args = _parse_args()

    from petcar.core.runtime_config import load as load_runtime_config
    load_runtime_config()
    if args.llm:
        config.LLM_BACKEND = args.llm

    port = args.port
    run_flask = not args.voice or args.flask
    run_voice = not args.flask or args.voice

    # 0. 先清掉 aitank-menu，独占 OLED（SIGUSR1 优雅让路 → service stop → kill 兜底）
    _stop_aitank_menu()
    time.sleep(0.3)  # 等 I2C 句柄释放

    # 1. OLED + loading 动画
    from petcar.drivers.oled import create_oled_driver
    oled = create_oled_driver()
    oled.start_loading("LOADING...")

    # 2. 起占位 HTTP 子进程（fork context，从文件读状态）
    loading_proc: Optional[mp.Process] = None

    if run_flask:
        # 先清空状态文件
        _set_stage("starting")
        loading_proc = mp.Process(   # 默认 context 是 fork（Linux）
            target=_serve_loading,
            args=(port, config.PET_NAME, _INIT_FILE),
            name="petcar-loading",
        )
        loading_proc.daemon = True
        loading_proc.start()
        print(f"[Loading] fork PID={loading_proc.pid} -> http://0.0.0.0:{port}/")
        time.sleep(0.3)

    # 3. 同步初始化（whisper 约 2-3 分钟）
    m = _connect_all()
    oled.stop_loading()

    # 推最终 ready 到文件
    _INIT_STATUS["ready"] = True
    _set_stage("ready")
    print("[Init] 全部就绪!")

    # 4. 停占位子进程
    if loading_proc is not None and loading_proc.is_alive():
        loading_proc.terminate()
        loading_proc.join(timeout=2)
        if loading_proc.is_alive(): loading_proc.kill()
        print("[Loading] 占位 server 已停止")

    # 5. 欢迎表情
    m["emotion"].set_emotion("happy")
    m["emotion"].text_bubble(f"我是{config.PET_NAME}~", duration=3)
    m["tts"].speak_async(config.STARTUP_GREETING)
    time.sleep(1)

    if args.test_emotion:
        _test_all_emotions(m)

    # 6. 真 Flask（完整 modules + init_status_ref + loading_html）
    loading_html = _build_loading_html(config.PET_NAME)
    try:
        if run_flask:
            from petcar.api.flask_app import create_app
            app = create_app(
                chat=m["chat"], emotion=m["emotion"],
                mecanum=m["mecanum"], ptz=m["ptz"],
                camera=m["camera"], mood_engine=m["mood"],
                tts=m["tts"], asr=m["asr"],
                skill_manager=m["skill_manager"],
                block_service=m["block_service"],
                action_player=m["action_player"],
                pid_tracker=m["pid_tracker"],
                init_status_ref=_INIT_STATUS,
                loading_html=loading_html,
            )
            if app:
                def _run_flask():
                    app.run(host=config.FLASK_HOST, port=port, debug=False,
                            use_reloader=False, threaded=True)
                threading.Thread(target=_run_flask, daemon=True).start()
                print(f"[Flask] 已启动 http://localhost:{port}")

        if run_voice:
            print("\n按 Enter 开始语音交互, 'quit' 退出\n")
            m["voice"].start()
            try:
                while m["voice"]._running: time.sleep(0.5)
            except KeyboardInterrupt: pass
        elif run_flask:
            print("\n仅 Flask 模式, Ctrl+C 退出\n")
            try:
                while True: time.sleep(1)
            except KeyboardInterrupt: pass

    except KeyboardInterrupt:
        print("\nCtrl+C, 退出...")
    finally:
        m["block_service"].shutdown()
        m["action_player"].stop()
        m["mecanum"].stop()
        m["emotion"].stop()
        m["mood"].stop()
        m["camera"].close()
        print("✅ 再见啦~")


# ============================================================================
# argparse
# ============================================================================
def _parse_args():
    p = argparse.ArgumentParser(description="AI-PetCar 主程序")
    p.add_argument("--flask", action="store_true", help="只启动 Web API")
    p.add_argument("--voice", action="store_true", help="只启动语音交互")
    p.add_argument("--test-emotion", action="store_true", help="跑一遍 12 种表情")
    p.add_argument("--llm", default=None, help="强制 LLM backend: ollama | doubao")
    p.add_argument("--port", type=int, default=config.FLASK_PORT, help="Flask 端口")
    p.add_argument("--no-camera", action="store_true", help="不打开摄像头")
    return p.parse_args()


def _test_all_emotions(modules):
    from petcar.drivers.oled import ALL_EMOTIONS
    emotion = modules["emotion"]
    print("\n=== 12 种表情预览 ===")
    for name in ALL_EMOTIONS:
        print(f"  → {name}")
        emotion.set_emotion(name, duration=0); time.sleep(1.2)
    emotion.set_emotion("happy")
    print("=== 完成 ===\n")


if __name__ == "__main__":
    main()
