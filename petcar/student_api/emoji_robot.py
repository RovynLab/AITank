# -*- coding: utf-8 -*-
"""
student_api/emoji_robot.py — 学生友好的 EmojiRobot 极简接口
==============================================================

# 学生写的代码:
from petcar.student_api import EmojiRobot, Face, EyeStyle, MouthStyle
import time

robot = EmojiRobot()

# 12 种表情快捷方法
robot.happy()
robot.sad()
robot.angry()
robot.surprised()
robot.sleepy()
robot.love()
robot.neutral()
robot.wink()
robot.laugh()
robot.thinking()
robot.scared()
robot.confused()

# 动作
robot.forward()
robot.spin()
time.sleep(2)
robot.stop()

# 宠物动作 (云台 + 底盘组合)
robot.nod()
robot.wag_tail()
robot.twist()
robot.spin_joy()

# 云台
robot.look_up()
robot.look_left(20)

# 说话 (带表情)
robot.say("你好呀！")

# 自定义脸
face = Face(left_eye=EyeStyle.HEART, right_eye=EyeStyle.HEART, mouth=MouthStyle.SMILE)
robot.show_face(face, duration=3)

# 摄像头
p = robot.capture_photo()
faces = robot.detect_faces()

# 大模型对话
reply = robot.chat("你好")
"""

from __future__ import annotations

import sys
import os
import time
import threading
from typing import List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar import config
from petcar.student_api.face import Face, EyeStyle, MouthStyle, BrowStyle


class EmojiRobot:
    """极简学生编程接口: 表情 + 动作 + 云台 + 语音 + LLM"""

    _instance = None
    _instance_lock = threading.Lock()

    def __init__(self, auto_connect: bool = True, mock: bool = False):
        """
        auto_connect=True 时自动连接所有硬件驱动。
        mock=True 时不碰硬件 (开发机上跑)。
        """
        self.mock = mock

        # 延迟导入 — 避免循环 import + 启动慢
        self.oled = None
        self.emotion = None
        self.mood = None
        self.mecanum = None
        self.ptz = None
        self.action_player = None
        self.camera = None
        self.tts = None
        self.chat = None
        self.voice = None

        if auto_connect:
            self._connect_all()

    def _connect_all(self):
        """连接所有硬件和核心模块"""
        print("[EmojiRobot] 连接硬件和核心模块...")
        from petcar.drivers.oled import create_oled_driver
        from petcar.drivers.mecanum import MecanumDriver
        from petcar.drivers.ptz import PTZDriver
        from petcar.drivers.camera import CameraDriver
        from petcar.drivers.tts import TTSDriver
        from petcar.core.emotion_engine import EmotionEngine
        from petcar.core.mood_engine import MoodEngine
        from petcar.core.chat_agent import ChatAgent
        from petcar.core.skill_manager import SkillManager
        from petcar.skills.move import MoveSkill
        from petcar.skills.ptz import PTZSkill
        from petcar.skills.photo import PhotoSkill
        from petcar.skills.face_detect import FaceDetectSkill
        from petcar.skills.face_track import FaceTrackSkill
        from petcar.skills.weather import WeatherSkill
        from petcar.skills.alarm import AlarmSkill
        from petcar.skills.emote import EmoteSkill
        from petcar.skills.express import ExpressSkill, ExpressionPlayer

        # 驱动层
        self.oled = create_oled_driver()
        self.mecanum = MecanumDriver()
        self.ptz = PTZDriver()
        self.camera = CameraDriver()
        self.tts = TTSDriver()
        self.action_player = ExpressionPlayer(self.mecanum, self.ptz)

        # 核心引擎
        self.emotion = EmotionEngine(self.oled)
        self.emotion.start()

        self.mood = MoodEngine(self.emotion)
        self.mood.start()

        # Skills
        self._skill_mgr = SkillManager()
        self._skill_mgr.register(MoveSkill(self.mecanum))
        self._skill_mgr.register(PTZSkill(self.ptz))
        self._skill_mgr.register(PhotoSkill(self.camera))
        self._skill_mgr.register(FaceDetectSkill(self.camera))
        self._skill_mgr.register(FaceTrackSkill(self.camera, self.ptz))
        self._skill_mgr.register(WeatherSkill())
        self._skill_mgr.register(AlarmSkill())
        self._skill_mgr.register(EmoteSkill(self.emotion))
        self._skill_mgr.register(ExpressSkill(self.action_player))

        # LLM
        self.chat = ChatAgent(mood_engine=self.mood, skill_manager=self._skill_mgr)

        # 云台初始化
        self.ptz.init()

        print("[EmojiRobot] 全部就绪 ✅")

    def close(self):
        """释放资源"""
        try:
            if self.action_player: self.action_player.stop()
            if self.emotion: self.emotion.stop()
            if self.mood: self.mood.stop()
            if self.mecanum: self.mecanum.shutdown()
            if self.camera: self.camera.close()
        except Exception:
            pass
        print("[EmojiRobot] 已关闭")

    # ========================================================================
    # 表情 (12 种快捷方法)
    # ========================================================================
    def _set_emotion(self, name: str, duration: float = 0):
        if self.emotion:
            self.emotion.set_emotion(name, duration=duration)
        else:
            print(f"[EmojiRobot] emotion={name} (未连接硬件)")

    def happy(self, duration=0):      self._set_emotion("happy", duration)
    def sad(self, duration=0):        self._set_emotion("sad", duration)
    def angry(self, duration=0):       self._set_emotion("angry", duration)
    def surprised(self, duration=0):   self._set_emotion("surprised", duration)
    def sleepy(self, duration=0):      self._set_emotion("sleepy", duration)
    def love(self, duration=0):        self._set_emotion("love", duration)
    def neutral(self, duration=0):     self._set_emotion("neutral", duration)
    def wink(self, duration=0):        self._set_emotion("wink", duration)
    def laugh(self, duration=0):       self._set_emotion("laugh", duration)
    def thinking(self, duration=0):    self._set_emotion("thinking", duration)
    def scared(self, duration=0):      self._set_emotion("scared", duration)
    def confused(self, duration=0):   self._set_emotion("confused", duration)

    def blink(self):
        if self.emotion:
            self.emotion.blink_now()

    # ========================================================================
    # 动作
    # ========================================================================
    def forward(self):         self.mecanum and self.mecanum.forward()
    def backward(self):        self.mecanum and self.mecanum.backward()
    def leftSlide(self):       self.mecanum and self.mecanum.leftSlide()
    def rightSlide(self):      self.mecanum and self.mecanum.rightSlide()
    def turnLeft(self):        self.mecanum and self.mecanum.turnLeft()
    def turnRight(self):       self.mecanum and self.mecanum.turnRight()
    def spin(self):            self.mecanum and self.mecanum.spin()
    def stop(self):            self.mecanum and self.mecanum.stop()

    # ========================================================================
    # 宠物动作 (云台 + 底盘组合，后台播放)
    # ========================================================================
    def do_action(self, name: str) -> bool:
        if self.action_player is None:
            print(f"[EmojiRobot] action={name} (未连接硬件)")
            return False
        return self.action_player.play(name)

    def stop_action(self):
        self.action_player and self.action_player.stop()

    def nod(self):          return self.do_action("nod")
    def shake_head(self):   return self.do_action("shake")
    def tilt_head(self):    return self.do_action("tilt")
    def wag_tail(self):     return self.do_action("wag")
    def twist(self):        return self.do_action("twist")
    def spin_joy(self):     return self.do_action("spin")
    def nuzzle(self):       return self.do_action("nuzzle")
    def hop(self):          return self.do_action("hop")
    def droop(self):        return self.do_action("droop")
    def lean_in(self):      return self.do_action("lean_in")
    def look_around(self):  return self.do_action("look_around")
    def stretch(self):      return self.do_action("stretch")

    # ========================================================================
    # 云台
    # ========================================================================
    def look_up(self, delta=10):
        self.ptz and self.ptz.look_up(delta)
    def look_down(self, delta=10):
        self.ptz and self.ptz.look_down(delta)
    def look_left(self, delta=10):
        self.ptz and self.ptz.look_left(delta)
    def look_right(self, delta=10):
        self.ptz and self.ptz.look_right(delta)
    def look_center(self):
        self.ptz and self.ptz.look_center()

    # ========================================================================
    # 说话 + 语音
    # ========================================================================
    def say(self, text: str, emotion: str = "happy"):
        """说话 + 同步设置表情 + 嘴巴动画"""
        self._set_emotion(emotion)
        if self.emotion:
            self.emotion.start_speak(duration=max(2, len(text) * 0.15))
        if self.tts:
            self.tts.speak_async(text, emotion)
        print(f"[say {emotion}] {text}")

    # ========================================================================
    # 自定义 Face
    # ========================================================================
    def show_face(self, face: Face, duration: float = 2):
        if self.emotion:
            self.emotion.oled.show_custom_face(face.to_dict())
            # duration 秒后回到 neutral
            if duration > 0:
                threading.Timer(duration, self._set_emotion, args=("neutral", 0)).start()
        else:
            print(f"[EmojiRobot] show_face={face} (未连接)")

    def print_text(self, text: str):
        if self.oled:
            self.oled.show_text(text)

    # ========================================================================
    # 摄像头
    # ========================================================================
    def capture_photo(self) -> Optional[str]:
        if not self.camera:
            print("[EmojiRobot] camera 未连接")
            return None
        return self.camera.take_photo()

    def detect_faces(self) -> List[tuple]:
        if not self.camera:
            return []
        faces = self.camera.detect_faces()
        # 返回 [(cx, cy), ...] 简化版
        return [(f[0], f[1]) for f in faces]

    def start_face_tracking(self):
        if self.camera and self.ptz:
            self.camera.start_face_tracking(self.ptz)

    def stop_face_tracking(self):
        if self.camera:
            self.camera.stop_face_tracking()

    # ========================================================================
    # LLM 对话
    # ========================================================================
    def chat(self, text: str) -> str:
        if not self.chat:
            return "(ChatAgent 未配置) " + text
        resp = self.chat.chat(text)
        return resp.reply

    def chat_full(self, text: str):
        """返回完整 ChatResponse"""
        if not self.chat:
            return None
        return self.chat.chat(text)
