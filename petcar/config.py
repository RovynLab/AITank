# -*- coding: utf-8 -*-
"""
petcar/config.py — PetCar 专属配置
=================================

继承 AITank 的硬件地址配置，新增 AI-PetCar 升级项。
换模型 / 换 API Key / 换人格 —— 都改这里。
"""

import os
import sys

# ============================================================================
# 硬件地址 (继承自 AITank config，保持一致)
# ============================================================================
PCA9685_ADDR    = 0x60
PWM_FREQ        = 50

# 电机通道
MOTOR_FL = 2
MOTOR_FR = 1
MOTOR_TL = 3
MOTOR_TR = 4

# 速度
MOTOR_NORMAL_SPEED = 150
MOTOR_MAX_SPEED    = 255

# 云台
SERVO_H = 0
SERVO_V = 1
SERVO_H_MIN  = 0
SERVO_H_MAX  = 180
SERVO_V_MIN  = 45
SERVO_V_MAX  = 135
SERVO_INIT_H = 90
SERVO_INIT_V = 90

# 摄像头
CAMERA_INDEX = 0
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480

# ============================================================================
# OLED (AI-PetCar 新增)
# ============================================================================
OLED_ADDR  = 0x3C
OLED_WIDTH = 128
OLED_HEIGHT = 64

# ============================================================================
# LLM 配置
# ============================================================================
LLM_BACKEND = os.environ.get("PETCAR_LLM_BACKEND", "ollama")
# 选项: "ollama" | "doubao" | "tongyi" | "mock"

OLLAMA_HOST = os.environ.get("PETCAR_OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("PETCAR_OLLAMA_MODEL", "qwen2.5:0.5b")

DOUBAO_API_KEY = os.environ.get("PETCAR_DOUBAO_KEY", "")
DOUBAO_MODEL   = os.environ.get("PETCAR_DOUBAO_MODEL", "doubao-pro-32k")

# 生成参数 (面板可调)
LLM_TEMPERATURE = float(os.environ.get("PETCAR_LLM_TEMPERATURE", "0.7"))
LLM_NUM_PREDICT = int(os.environ.get("PETCAR_LLM_NUM_PREDICT", "96"))
LLM_TIMEOUT     = float(os.environ.get("PETCAR_LLM_TIMEOUT", "180"))

# ============================================================================
# Pet 人格
# ============================================================================
PET_NAME = "小坦"
PET_PERSONALITY = "活泼友善的编程伙伴，像好朋友一样跟你说话，回答要口语化、简短（30字以内），偶尔用叠词卖萌。"

# 启动时的自我介绍（启动完成后自动播报）
STARTUP_GREETING = os.environ.get(
    "PETCAR_STARTUP_GREETING",
    f"你好，我是{PET_NAME}，是你的编程伙伴，很高兴见到你！",
)

# ============================================================================
# ASR 配置
# ============================================================================
ASR_MODE = os.environ.get("PETCAR_ASR_MODE", "whisper")
# 选项: "whisper" | "porcupine" | "mock"

WHISPER_MODEL = os.environ.get("PETCAR_WHISPER_MODEL", "base")
WHISPER_LANG  = "zh"

# 唤醒词默认带上宠物名字
WAKE_WORD = os.environ.get("PETCAR_WAKE_WORD", f"你好{PET_NAME}")

# 麦克风设备 (sounddevice 序号或名字片段)，留空自动探测 USB 麦克风
ASR_DEVICE = os.environ.get("PETCAR_ASR_DEVICE", "")

# VAD 灵敏度 (面板可调): 触发阈值上限 / 连续有声起录时长 / 静音结束时长
VAD_THRESHOLD_MAX = float(os.environ.get("PETCAR_VAD_THRESHOLD_MAX", "0.02"))
VAD_SPEECH_MS     = int(os.environ.get("PETCAR_VAD_SPEECH_MS", "100"))
VAD_SILENCE_MS    = int(os.environ.get("PETCAR_VAD_SILENCE_MS", "600"))

# ============================================================================
# TTS 配置
# ============================================================================
TTS_MODE = os.environ.get("PETCAR_TTS_MODE", "piper")
# 选项: "edge" (云端童声, 需联网, 失败自动降级 piper) | "piper" (本地离线童声)
#       | "espeak" | "pyttsx3" | "mock"

# ALSA 播放设备，如 plughw:CARD=UACDemoV10,DEV=0；留空则自动探测 USB 声卡
TTS_DEVICE = os.environ.get("PETCAR_TTS_DEVICE", "")

# edge-tts 童声 (需要联网):
#   zh-CN-XiaoyiNeural 女童声 / zh-CN-YunxiaNeural 男童声
TTS_VOICE = os.environ.get("PETCAR_TTS_VOICE", "zh-CN-XiaoyiNeural")
TTS_PITCH = os.environ.get("PETCAR_TTS_PITCH", "+15Hz")  # 音调调高更像小朋友

# 本地离线童声 (Piper): 见 docs/使用说明.md 里的安装步骤
PIPER_BIN   = os.environ.get("PETCAR_PIPER_BIN", "/home/pi/piper/piper/piper")
PIPER_MODEL = os.environ.get("PETCAR_PIPER_MODEL",
                             "/home/pi/piper/zh_CN-huayan-medium.onnx")
# 音调倍率: 1.0=原声(成年女声), 1.15≈童声; 越大越尖
PIPER_PITCH = float(os.environ.get("PETCAR_PIPER_PITCH", "1.15"))
# 云端合成超时(秒), 超时即降级本地 piper, 避免断网时说一句话等很久
EDGE_TIMEOUT = float(os.environ.get("PETCAR_EDGE_TIMEOUT", "10"))

# ============================================================================
# MoodEngine 参数
# ============================================================================
MOOD_DECAY_V     = 0.98   # valence 每秒衰减
MOOD_DECAY_A     = 0.97   # arousal 每秒衰减
MOOD_DECAY_I     = 0.95   # intensity 每秒衰减
IDLE_SLEEPY_SEC  = 60     # 空闲多久进入 sleepy
BLINK_INTERVAL   = (4, 8) # 眨眼间隔范围 (秒)

# ============================================================================
# Flask
# ============================================================================
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000

# ============================================================================
# 路径
# ============================================================================
BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHOTO_DIR = os.path.join(BASE_DIR, "petcar", "photos")
LOG_DIR   = os.path.join(BASE_DIR, "petcar", "logs")

os.makedirs(PHOTO_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
