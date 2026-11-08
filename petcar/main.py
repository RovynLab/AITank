# -*- coding: utf-8 -*-
"""
petcar/main.py — AI-PetCar 主程序入口
======================================

用法:
    python -m petcar.main                  # 启动 Web API + 语音交互
    python -m petcar.main --flask          # 只启动 Web API
    python -m petcar.main --voice          # 只启动语音交互
    python -m petcar.main --mock           # Mock 模式 (开发机上测试表情)
    python -m petcar.main --test-emotion   # 跑一遍 12 种表情
    python -m petcar.main --llm ollama     # 强制用 Ollama
    python -m petcar.main --llm mock       # 强制用 MockBackend
"""

from __future__ import annotations

import sys
import os
import argparse
import time
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar import config


def _parse_args():
    parser = argparse.ArgumentParser(description="AI-PetCar 主程序")
    parser.add_argument("--flask", action="store_true", help="只启动 Web API")
    parser.add_argument("--voice", action="store_true", help="只启动语音交互")
    parser.add_argument("--mock", action="store_true", help="Mock 模式 (开发机)")
    parser.add_argument("--test-emotion", action="store_true", help="跑一遍 12 种表情然后退出")
    parser.add_argument("--llm", default=None, help="强制 LLM backend: ollama | doubao | mock")
    parser.add_argument("--port", type=int, default=config.FLASK_PORT, help="Flask 端口")
    parser.add_argument("--no-camera", action="store_true", help="不打开摄像头")
    return parser.parse_args()


def _connect_all():
    """初始化所有模块"""
    print("\n" + "=" * 60)
    print("  AI-PetCar 初始化中...")
    print("=" * 60)

    # 驱动层
    from petcar.drivers.oled import create_oled_driver
    from petcar.drivers.mecanum import MecanumDriver
    from petcar.drivers.ptz import PTZDriver
    from petcar.drivers.camera import CameraDriver
    from petcar.drivers.tts import TTSDriver
    from petcar.drivers.asr import ASRDriver

    oled = create_oled_driver()
    mecanum = MecanumDriver()
    ptz = PTZDriver()
    ptz.init()
    camera = CameraDriver()
    tts = TTSDriver()
    asr = ASRDriver()

    # 核心层
    from petcar.core.emotion_engine import EmotionEngine
    from petcar.core.mood_engine import MoodEngine
    from petcar.core.chat_agent import ChatAgent
    from petcar.core.llm_backends import create_llm_backend
    from petcar.core.skill_manager import SkillManager
    from petcar.core.voice_io import VoiceIO

    emotion = EmotionEngine(oled)
    emotion.start()

    mood = MoodEngine(emotion)
    mood.start()

    # Skills
    from petcar.skills.move import MoveSkill
    from petcar.skills.ptz import PTZSkill
    from petcar.skills.photo import PhotoSkill
    from petcar.skills.face_detect import FaceDetectSkill
    from petcar.skills.face_track import FaceTrackSkill
    from petcar.skills.weather import WeatherSkill
    from petcar.skills.alarm import AlarmSkill
    from petcar.skills.emote import EmoteSkill
    from petcar.skills.express import ExpressSkill, ExpressionPlayer

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

    # LLM
    llm = create_llm_backend()
    chat = ChatAgent(backend=llm, mood_engine=mood, skill_manager=sm)

    # VoiceIO
    voice = VoiceIO(asr=asr, tts=tts, chat=chat, emotion=emotion)

    # 积木编程运行时
    from petcar.blocks.runtime import BlockRuntime
    from petcar.blocks.service import BlockService
    block_service = BlockService(BlockRuntime(
        mecanum=mecanum,
        ptz=ptz,
        camera=camera,
        emotion=emotion,
        tts=tts,
    ))

    return {
        "oled": oled,
        "mecanum": mecanum,
        "ptz": ptz,
        "camera": camera,
        "tts": tts,
        "asr": asr,
        "emotion": emotion,
        "mood": mood,
        "chat": chat,
        "voice": voice,
        "skill_manager": sm,
        "block_service": block_service,
        "action_player": action_player,
    }


def _test_all_emotions(modules):
    """在 OLED 上遍历所有表情"""
    from petcar.drivers.oled import ALL_EMOTIONS
    emotion = modules["emotion"]
    print("\n=== 12 种表情预览 ===")
    for name in ALL_EMOTIONS:
        print(f"  → {name}")
        emotion.set_emotion(name, duration=0)
        time.sleep(1.2)
    emotion.set_emotion("happy")
    print("=== 完成 ===\n")


def main():
    args = _parse_args()

    # 面板保存的运行时配置 (优先于 config.py / 环境变量默认值)
    from petcar.core.runtime_config import load as load_runtime_config
    load_runtime_config()

    # Mock 模式: 强制不连硬件
    if args.mock:
        os.environ.setdefault("PETCAR_LLM_BACKEND", "mock")

    # 强制 LLM
    if args.llm:
        config.LLM_BACKEND = args.llm

    # 初始化
    m = _connect_all()

    # 欢迎表情
    m["emotion"].set_emotion("happy")
    m["emotion"].text_bubble(f"我是{config.PET_NAME}~", duration=3)
    # 启动自我介绍（异步播报，不阻塞启动）
    m["tts"].speak_async(config.STARTUP_GREETING)
    time.sleep(1)

    # 测试模式
    if args.test_emotion:
        _test_all_emotions(m)
        # 测试完继续运行

    # 全部都没开 → 两个都开
    run_flask = True
    run_voice = True
    if args.flask and not args.voice:
        run_flask, run_voice = True, False
    elif args.voice and not args.flask:
        run_flask, run_voice = False, True
    elif args.flask and args.voice:
        run_flask, run_voice = True, True
    # else: 默认两个都开

    # ASR=mock 且后台运行 (stdin 是 /dev/null) 时没有输入源, 语音循环只会空转
    if run_voice and m["asr"].mode == "mock" and not sys.stdin.isatty():
        print("[VoiceIO] ASR=mock 且无终端输入, 跳过语音循环 "
              "(在面板把 ASR 模式设为 whisper 后重启即可)")
        run_voice = False

    try:
        if run_flask:
            from petcar.api.flask_app import create_app
            app = create_app(
                chat=m["chat"],
                emotion=m["emotion"],
                mecanum=m["mecanum"],
                ptz=m["ptz"],
                camera=m["camera"],
                mood_engine=m["mood"],
                tts=m["tts"],
                asr=m["asr"],
                skill_manager=m["skill_manager"],
                block_service=m["block_service"],
                action_player=m["action_player"],
            )
            if app:
                # 后台线程启动 Flask
                def _run_flask():
                    app.run(host=config.FLASK_HOST, port=args.port,
                            debug=False, use_reloader=False)
                threading.Thread(target=_run_flask, daemon=True).start()
                print(f"[Flask] 已启动 http://localhost:{args.port}")

        if run_voice:
            print("\n按 Enter 开始语音交互, 'quit' 退出\n")
            m["voice"].start()
            # voice.start() 已经启动后台线程, 这里阻塞等 Ctrl+C
            try:
                while m["voice"]._running:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass
        elif run_flask:
            # 只跑 Flask: 阻塞主线程, 否则进程会立刻退出
            print("\n仅 Flask 模式, Ctrl+C 退出\n")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

    except KeyboardInterrupt:
        print("\nCtrl+C, 退出...")
    finally:
        # 清理
        m["block_service"].shutdown()
        m["action_player"].stop()
        m["mecanum"].stop()
        m["emotion"].stop()
        m["mood"].stop()
        m["camera"].close()
        print("✅ 再见啦~")


if __name__ == "__main__":
    main()
