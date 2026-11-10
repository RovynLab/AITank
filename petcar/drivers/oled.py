# -*- coding: utf-8 -*-
"""
drivers/oled.py — SSD1306 OLED 128×64 驱动
==========================================

用 luma.oled + PIL.ImageDraw 动态绘制表情元素。
如果 OLED 没连（开发机上），自动切换到 MockOLEDDriver，在终端打印预览。
"""

from __future__ import annotations

import sys
import os
import time
import threading
from typing import Optional

# 先加 AITank 根目录到 sys.path，方便相对 import
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar import config

# ============================================================================
# 真实驱动 (需要 luma.oled)
# ============================================================================

try:
    from luma.core.interface.serial import i2c
    from luma.oled.device import ssd1306
    from PIL import Image, ImageDraw, ImageFont
    _HAS_LUMA = True
except ImportError:
    _HAS_LUMA = False
    from PIL import Image, ImageDraw, ImageFont

# 一些常用常量
W, H = config.OLED_WIDTH, config.OLED_HEIGHT  # 128, 64

# 眼睛中心坐标 (左眼 x=30, 右眼 x=80, y=28)
EYE_L_CX = 30
EYE_R_CX = 80
EYE_CY   = 28
EYE_RADIUS = 8

# 嘴巴区域
MOUTH_Y = 46

# 文字气泡区
TEXT_Y = 54


# ============================================================================
# 画眼睛的各种形状
# ============================================================================

def _draw_eye_circle(draw, cx, cy, r=EYE_RADIUS, outline=1, fill=0):
    """普通圆形眼睛"""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=outline, fill=fill)

def _draw_eye_small(draw, cx, cy):
    _draw_eye_circle(draw, cx, cy, r=5)

def _draw_eye_arc(draw, cx, cy, r=EYE_RADIUS):
    """弯月眼 (开心笑) — 用一段 200° 弧度"""
    draw.arc([cx - r, cy - r + 2, cx + r, cy + r + 2], start=200, end=340, fill=1)

def _draw_eye_big(draw, cx, cy, r=11):
    """大圆眼 (惊讶)"""
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=1)
    # 瞳孔
    draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=1)

def _draw_eye_heart(draw, cx, cy, size=7):
    """爱心眼 — 用两个小圆+三角近似"""
    s = size
    # 左上圆
    draw.ellipse([cx - s, cy - s, cx, cy], fill=1)
    # 右上圆
    draw.ellipse([cx, cy - s, cx + s, cy], fill=1)
    # 下面的尖
    draw.polygon([(cx - s, cy - 1), (cx, cy + s + 2), (cx + s, cy - 1)], fill=1)

def _draw_eye_line(draw, cx, cy, length=10):
    """眯缝眼 / 眨眼 — 一条水平线"""
    draw.line([cx - length // 2, cy, cx + length // 2, cy], fill=1)

def _draw_eye_question(draw, cx, cy):
    """问号眼 (困惑)"""
    draw.text((cx - 3, cy - 6), "?", fill=1)


# ============================================================================
# 画嘴巴
# ============================================================================

def _draw_mouth_line(draw, y=MOUTH_Y, width=30):
    cx = W // 2
    draw.line([cx - width // 2, y, cx + width // 2, y], fill=1)

def _draw_mouth_arc_top(draw, y=MOUTH_Y, width=30, h=6):
    """上弧 = 笑"""
    cx = W // 2
    draw.arc([cx - width // 2, y - h, cx + width // 2, y + h],
             start=10, end=170, fill=1)

def _draw_mouth_arc_bottom(draw, y=MOUTH_Y, width=30, h=5):
    """下弧 = 难过"""
    cx = W // 2
    draw.arc([cx - width // 2, y - h, cx + width // 2, y + h + 2],
             start=190, end=350, fill=1)

def _draw_mouth_open(draw, y=MOUTH_Y, w=10, h=8):
    """张嘴 O"""
    cx = W // 2
    draw.ellipse([cx - w, y - h // 2, cx + w, y + h // 2 + 2], fill=1)

def _draw_mouth_open_big(draw, y=MOUTH_Y, w=14, h=12):
    """大笑张嘴"""
    cx = W // 2
    draw.ellipse([cx - w, y - h // 2, cx + w, y + h // 2 + 2], fill=1)

def _draw_mouth_skew(draw, y=MOUTH_Y, width=25):
    """歪嘴 (思考)"""
    cx = W // 2
    draw.line([cx - width // 2, y + 2, cx - 3, y], fill=1)
    draw.line([cx + 3, y, cx + width // 2, y - 1], fill=1)

def _draw_mouth_ponder(draw, y=MOUTH_Y):
    # 短嘴偏向右侧，与困惑的宽波浪嘴区分。
    cx = W // 2 + 8
    draw.line([cx - 5, y + 1, cx + 5, y - 1], fill=1, width=2)

def _draw_mouth_wave(draw, y=MOUTH_Y):
    """波浪嘴 (困惑)"""
    cx = W // 2
    draw.line([(cx - 16, y), (cx - 8, y - 4), (cx, y + 4),
               (cx + 8, y - 4), (cx + 16, y)], fill=1, width=2)


# ============================================================================
# 画眉毛 + 装饰
# ============================================================================

def _draw_brows(draw, style):
    cx_l = EYE_L_CX
    cx_r = EYE_R_CX
    cy   = EYE_CY - 14
    if style == "angry":
        # 倒八字
        draw.line([cx_l - 8, cy - 2, cx_l + 6, cy + 4], fill=1)
        draw.line([cx_r + 8, cy - 2, cx_r - 6, cy + 4], fill=1)
    elif style == "surprised":
        # 高挑平眉
        draw.line([cx_l - 8, cy - 2, cx_l + 8, cy - 2], fill=1)
        draw.line([cx_r - 8, cy - 2, cx_r + 8, cy - 2], fill=1)
    elif style == "sad":
        # 八字眉
        draw.line([cx_l - 8, cy + 2, cx_l + 6, cy - 2], fill=1)
        draw.line([cx_r + 8, cy + 2, cx_r - 6, cy - 2], fill=1)
    elif style == "happy":
        # 弯眉
        draw.arc([cx_l - 10, cy - 4, cx_l + 10, cy + 6], start=200, end=340, fill=1)
        draw.arc([cx_r - 10, cy - 4, cx_r + 10, cy + 6], start=200, end=340, fill=1)
    elif style == "thinking":
        draw.line([cx_l - 8, cy - 1, cx_l + 8, cy - 5], fill=1, width=2)
        draw.line([cx_r - 6, cy + 3, cx_r + 6, cy + 3], fill=1, width=2)
    elif style == "confused":
        draw.line([cx_l - 8, cy - 6, cx_l + 7, cy - 2], fill=1, width=2)
        draw.line([cx_r - 7, cy + 3, cx_r + 8, cy - 1], fill=1, width=2)
    # flat 不画眉毛


def _draw_decor(draw, decors):
    """画装饰: tear_l / tear_r / zzz / sweat / question"""
    for d in (decors or []):
        if d == "tear_l":
            draw.polygon([(EYE_L_CX - 4, EYE_CY + 10), (EYE_L_CX - 1, EYE_CY + 16),
                          (EYE_L_CX + 2, EYE_CY + 10)], fill=1)
        elif d == "tear_r":
            draw.polygon([(EYE_R_CX - 4, EYE_CY + 10), (EYE_R_CX - 1, EYE_CY + 16),
                          (EYE_R_CX + 2, EYE_CY + 10)], fill=1)
        elif d == "zzz":
            draw.text((100, 6), "z", fill=1)
            draw.text((108, 2), "z", fill=1)
        elif d == "sweat":
            draw.ellipse([105, 20, 110, 27], fill=1)
        elif d == "ellipsis":
            for x in (99, 110, 121):
                draw.ellipse([x - 1, 7, x + 1, 9], fill=1)
        elif d == "question_right":
            # 像素图形问号，不依赖字体；与双眼保持距离。
            draw.arc([104, 2, 116, 12], start=180, end=450, fill=1, width=2)
            draw.line([(110, 12), (110, 15)], fill=1, width=2)
            draw.ellipse([110, 18, 112, 20], fill=1)
        elif d == "question":
            draw.text((W // 2 - 2, 12), "?", fill=1)


# ============================================================================
# 表情定义表
# ============================================================================

# 每种表情: {left_eye_shape, right_eye_shape, mouth_func_name, brow_style, decor_list}
EXPRESSIONS = {
    "neutral": {
        "left_eye": "circle",  "right_eye": "circle",
        "mouth": "line",       "brows": "flat",    "decor": [],
    },
    "happy": {
        "left_eye": "arc",     "right_eye": "arc",
        "mouth": "arc_top",    "brows": "happy",   "decor": [],
    },
    "sad": {
        "left_eye": "circle",  "right_eye": "circle",
        "mouth": "arc_bottom", "brows": "sad",     "decor": ["tear_l", "tear_r"],
    },
    "angry": {
        "left_eye": "circle",  "right_eye": "circle",
        "mouth": "line",       "brows": "angry",   "decor": [],
    },
    "surprised": {
        "left_eye": "big",     "right_eye": "big",
        "mouth": "open",       "brows": "surprised","decor": [],
    },
    "sleepy": {
        "left_eye": "line_h",  "right_eye": "line_h",
        "mouth": "line",       "brows": "flat",    "decor": ["zzz"],
    },
    "love": {
        "left_eye": "heart",   "right_eye": "heart",
        "mouth": "arc_top",    "brows": "happy",   "decor": [],
    },
    "thinking": {
        "left_eye": "circle",  "right_eye": "small",
        "mouth": "ponder",     "brows": "thinking", "decor": ["ellipsis"],
    },
    "wink": {
        "left_eye": "arc",     "right_eye": "line_h",
        "mouth": "arc_top",    "brows": "happy",   "decor": [],
    },
    "laugh": {
        "left_eye": "arc",     "right_eye": "arc",
        "mouth": "open_big",   "brows": "happy",   "decor": [],
    },
    "scared": {
        "left_eye": "big",     "right_eye": "big",
        "mouth": "open",       "brows": "surprised","decor": ["sweat"],
    },
    "confused": {
        "left_eye": "circle",  "right_eye": "circle",
        "mouth": "wave",       "brows": "confused", "decor": ["question_right"],
    },
}

ALL_EMOTIONS = list(EXPRESSIONS.keys())


# 绘图函数路由
_EYE_FUNCS = {
    "circle":    _draw_eye_circle,
    "small":     _draw_eye_small,
    "arc":       _draw_eye_arc,
    "big":       _draw_eye_big,
    "heart":     _draw_eye_heart,
    "line_h":    _draw_eye_line,
    "question":  _draw_eye_question,
}

_MOUTH_FUNCS = {
    "line":        _draw_mouth_line,
    "arc_top":     _draw_mouth_arc_top,
    "arc_bottom":  _draw_mouth_arc_bottom,
    "open":        _draw_mouth_open,
    "open_big":    _draw_mouth_open_big,
    "skew":        _draw_mouth_skew,
    "ponder":      _draw_mouth_ponder,
    "wave":        _draw_mouth_wave,
}


def _draw_face(draw, face_dict: dict, offset_y: int = 0):
    """根据 face_dict 在 ImageDraw 上绘制完整一张脸"""
    le = face_dict.get("left_eye", "circle")
    re_ = face_dict.get("right_eye", "circle")
    mt = face_dict.get("mouth", "line")
    br = face_dict.get("brows", "flat")
    dc = face_dict.get("decor", [])

    # 如果有 y 偏移 (比如动画跳动), 保存原坐标, 临时调整
    if offset_y:
        # 简单方案: 整张脸画在一个临时 Image 上, 然后 paste 到主画布偏移位置
        tmp = Image.new('1', (W, H), 0)
        tmp_draw = ImageDraw.Draw(tmp)
        _draw_face_on(tmp_draw, le, re_, mt, br, dc)
        draw.bitmap((0, offset_y), tmp)
    else:
        _draw_face_on(draw, le, re_, mt, br, dc)


def _draw_face_on(draw, left_eye, right_eye, mouth, brows, decor):
    # 眼睛
    _EYE_FUNCS.get(left_eye, _draw_eye_circle)(draw, EYE_L_CX, EYE_CY)
    _EYE_FUNCS.get(right_eye, _draw_eye_circle)(draw, EYE_R_CX, EYE_CY)
    # 嘴巴
    _MOUTH_FUNCS.get(mouth, _draw_mouth_line)(draw)
    # 眉毛
    _draw_brows(draw, brows)
    # 装饰
    _draw_decor(draw, decor)


# ============================================================================
# OLEDDriver (真实 / Mock)
# ============================================================================

class OLEDDriver:
    """真实 SSD1306 OLED 驱动"""

    def __init__(self, address: int = config.OLED_ADDR):
        if not _HAS_LUMA:
            raise RuntimeError("luma.oled 未安装，请 pip install luma.oled Pillow")
        serial = i2c(port=1, address=address)
        self.device = ssd1306(serial)
        self.width = W
        self.height = H
        self._image = Image.new('1', (W, H), 0)
        self._draw = ImageDraw.Draw(self._image)
        try:
            self._font = ImageFont.load_default()
        except Exception:
            self._font = None
        self._lock = threading.Lock()

    def clear(self):
        self._draw.rectangle([0, 0, W, H], fill=0)

    def present(self):
        self.device.display(self._image)

    def show_expression(self, emotion_name: str):
        face = EXPRESSIONS.get(emotion_name, EXPRESSIONS["neutral"])
        with self._lock:
            self.clear()
            _draw_face(self._draw, face)
            self.present()

    def show_custom_face(self, face_dict: dict, offset_y: int = 0):
        with self._lock:
            self.clear()
            _draw_face(self._draw, face_dict, offset_y=offset_y)
            self.present()

    def show_text(self, text: str, y: int = TEXT_Y):
        """在屏幕底部画文字 (覆盖原表情, 但 EmotionEngine 会处理叠加)"""
        with self._lock:
            self._draw.text((0, y), text[:21], fill=1, font=self._font)
            self.present()

    def set_pixel(self, x, y, on=1):
        with self._lock:
            self._draw.point((x, y), fill=on)
            self.present()

    def save_screenshot(self, path: str):
        self._image.save(path)


class MockOLEDDriver:
    """开发机上用的 Mock —— 把表情用 ASCII 打印到终端"""

    def __init__(self):
        self.width = W
        self.height = H
        self._current = "neutral"
        self._lock = threading.Lock()
        print("[OLED Mock] 已初始化 (终端预览模式)")

    def clear(self):
        pass

    def present(self):
        pass

    def show_expression(self, emotion_name: str):
        self._current = emotion_name
        # 简单的 ASCII 预览
        icons = {
            "neutral":   "  ●      ●   ",
            "happy":     "  ⌒      ⌒  ",
            "sad":       "  ●      ●   ",
            "angry":     "  ●      ●   ",
            "surprised": "  ◉      ◉   ",
            "sleepy":    "  ─      ─   ",
            "love":      "  ♥      ♥   ",
            "thinking":  "  O      o   ...",
            "wink":      "  ⌒      ─   ",
            "laugh":     "  ⌒      ⌒  (◡)",
            "scared":    "  ◉      ◉  ○",
            "confused":  "  ●      ●   ∿ ?",
        }
        print(f"[OLED Mock] expression={emotion_name} | {icons.get(emotion_name, '?')}")

    def show_custom_face(self, face_dict: dict, offset_y: int = 0):
        print(f"[OLED Mock] custom_face={face_dict}, offset_y={offset_y}")

    def show_text(self, text: str, y: int = TEXT_Y):
        print(f"[OLED Mock] text @{y}: {text}")

    def save_screenshot(self, path: str):
        print(f"[OLED Mock] save screenshot -> {path}")


# ============================================================================
# 工厂函数
# ============================================================================

def create_oled_driver() -> OLEDDriver | MockOLEDDriver:
    """自动检测硬件是否可用，返回对应驱动"""
    if _HAS_LUMA:
        try:
            drv = OLEDDriver()
            # 快速自检
            drv.show_expression("neutral")
            time.sleep(0.05)
            return drv
        except Exception as e:
            print(f"[OLED] 硬件不可用 ({e}), 切换 Mock")
            return MockOLEDDriver()
    else:
        print("[OLED] luma.oled 未安装, 使用 Mock")
        return MockOLEDDriver()
