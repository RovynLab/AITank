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
LLM_BACKEND = os.environ.get("PETCAR_LLM_BACKEND", "mock")
# 选项: "ollama" | "doubao" | "tongyi" | "mock"

OLLAMA_HOST = os.environ.get("PETCAR_OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("PETCAR_OLLAMA_MODEL", "qwen2.5:1.5b")

DOUBAO_API_KEY = os.environ.get("PETCAR_DOUBAO_KEY", "")
DOUBAO_MODEL   = os.environ.get("PETCAR_DOUBAO_MODEL", "doubao-pro-32k")

# ============================================================================
# ASR 配置
# ============================================================================
ASR_MODE = os.environ.get("PETCAR_ASR_MODE", "whisper")
# 选项: "whisper" | "porcupine" | "mock"

WHISPER_MODEL = os.environ.get("PETCAR_WHISPER_MODEL", "small")
WHISPER_LANG  = "zh"

WAKE_WORD = os.environ.get("PETCAR_WAKE_WORD", "你好小宝")

# ============================================================================
# TTS 配置
# ============================================================================
TTS_MODE = os.environ.get("PETCAR_TTS_MODE", "espeak")
# 选项: "espeak" | "pyttsx3" | "mock" | "doubao"

# ============================================================================
# Pet 人格
# ============================================================================
PET_NAME = "小宝"
PET_PERSONALITY = "活泼友善的 AI 宠物，像好朋友一样跟你说话，回答要口语化、简短（30字以内），偶尔用叠词卖萌。"

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
