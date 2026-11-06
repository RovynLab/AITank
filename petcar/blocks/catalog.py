# -*- coding: utf-8 -*-
"""petcar/blocks/catalog.py — 积木目录
=====================================
前端用它生成 Blockly 积木定义和工具箱，后端用它做白名单校验。
第一版只保留"简单运动 + 简单识别"。
"""

from __future__ import annotations

MOTIONS = [
    ("前进", "forward"),
    ("后退", "backward"),
    ("左移", "leftSlide"),
    ("右移", "rightSlide"),
    ("左转", "turnLeft"),
    ("右转", "turnRight"),
    ("原地旋转", "spin"),
]

PTZ_DIRS = [
    ("向上", "up"),
    ("向下", "down"),
    ("向左", "left"),
    ("向右", "right"),
    ("回正", "center"),
]

EMOTIONS = [
    ("中性", "neutral"),
    ("开心", "happy"),
    ("难过", "sad"),
    ("生气", "angry"),
    ("惊讶", "surprised"),
    ("困倦", "sleepy"),
    ("爱心", "love"),
    ("眨眼", "wink"),
    ("大笑", "laugh"),
    ("思考", "thinking"),
    ("害怕", "scared"),
    ("困惑", "confused"),
]

TARGETS = [
    ("人脸", "face"),
    ("网球", "tennis"),
    ("颜色", "color"),
]

CATEGORIES = [
    {"id": "event", "label": "事件", "colour": "#eab308"},
    {"id": "motion", "label": "运动", "colour": "#3b82f6"},
    {"id": "ptz", "label": "云台", "colour": "#06b6d4"},
    {"id": "face", "label": "表情", "colour": "#a855f7"},
    {"id": "speech", "label": "说话", "colour": "#ec4899"},
    {"id": "sense", "label": "识别", "colour": "#22c55e"},
    {"id": "control", "label": "控制", "colour": "#f97316"},
]


def _dd(name: str, options) -> dict:
    return {
        "type": "field_dropdown",
        "name": name,
        "options": [[label, value] for label, value in options],
    }


def _num(name: str, value: float, vmin: float, vmax: float,
         precision: float = 1) -> dict:
    return {
        "type": "field_number",
        "name": name,
        "value": value,
        "min": vmin,
        "max": vmax,
        "precision": precision,
    }


BLOCKS = [
    {
        "type": "event_start",
        "category": "event",
        "blockly": {
            "type": "event_start",
            "message0": "当程序开始",
            "nextStatement": None,
            "colour": "#eab308",
            "hat": "cap",
            "tooltip": "程序从这里开始运行",
        },
    },
    {
        "type": "move_for",
        "category": "motion",
        "blockly": {
            "type": "move_for",
            "message0": "向 %1 以速度 %2 移动 %3 秒",
            "args0": [
                _dd("DIR", MOTIONS),
                _num("SPEED", 150, 50, 255),
                _num("SECONDS", 1, 0.1, 30, 0.1),
            ],
            "previousStatement": None,
            "nextStatement": None,
            "inputsInline": True,
            "colour": "#3b82f6",
            "tooltip": "按方向移动一段时间后自动停止",
        },
    },
    {
        "type": "move_stop",
        "category": "motion",
        "blockly": {
            "type": "move_stop",
            "message0": "停止运动",
            "previousStatement": None,
            "nextStatement": None,
            "colour": "#3b82f6",
            "tooltip": "立即停止底盘",
        },
    },
    {
        "type": "look",
        "category": "ptz",
        "blockly": {
            "type": "look",
            "message0": "云台向 %1 转动 %2 度",
            "args0": [
                _dd("DIR", PTZ_DIRS),
                _num("DEGREES", 10, 1, 45),
            ],
            "previousStatement": None,
            "nextStatement": None,
            "inputsInline": True,
            "colour": "#06b6d4",
            "tooltip": "控制摄像头云台转动",
        },
    },
    {
        "type": "show_emotion",
        "category": "face",
        "blockly": {
            "type": "show_emotion",
            "message0": "显示表情 %1",
            "args0": [_dd("EMOTION", EMOTIONS)],
            "previousStatement": None,
            "nextStatement": None,
            "colour": "#a855f7",
            "tooltip": "在 OLED 屏幕上显示表情",
        },
    },
    {
        "type": "say",
        "category": "speech",
        "blockly": {
            "type": "say",
            "message0": "说 %1",
            "args0": [
                {
                    "type": "field_input",
                    "name": "TEXT",
                    "text": "你好呀",
                }
            ],
            "previousStatement": None,
            "nextStatement": None,
            "colour": "#ec4899",
            "tooltip": "让小车说话",
        },
    },
    {
        "type": "photo",
        "category": "sense",
        "blockly": {
            "type": "photo",
            "message0": "拍一张照片",
            "previousStatement": None,
            "nextStatement": None,
            "colour": "#22c55e",
            "tooltip": "拍照并保存到小车",
        },
    },
    {
        "type": "if_sees",
        "category": "sense",
        "blockly": {
            "type": "if_sees",
            "message0": "如果看到 %1 那么 %2",
            "args0": [
                _dd("TARGET", TARGETS),
                {"type": "input_statement", "name": "DO"},
            ],
            "previousStatement": None,
            "nextStatement": None,
            "colour": "#22c55e",
            "tooltip": "看到目标时执行里面的积木",
        },
    },
    {
        "type": "wait",
        "category": "control",
        "blockly": {
            "type": "wait",
            "message0": "等待 %1 秒",
            "args0": [_num("SECONDS", 1, 0, 600, 0.1)],
            "previousStatement": None,
            "nextStatement": None,
            "colour": "#f97316",
            "tooltip": "等待一段时间",
        },
    },
    {
        "type": "repeat",
        "category": "control",
        "blockly": {
            "type": "repeat",
            "message0": "重复 %1 次 %2",
            "args0": [
                _num("TIMES", 3, 1, 100),
                {"type": "input_statement", "name": "DO"},
            ],
            "previousStatement": None,
            "nextStatement": None,
            "colour": "#f97316",
            "tooltip": "重复执行里面的积木",
        },
    },
    {
        "type": "forever",
        "category": "control",
        "blockly": {
            "type": "forever",
            "message0": "一直重复 %1",
            "args0": [{"type": "input_statement", "name": "DO"}],
            "previousStatement": None,
            "nextStatement": None,
            "colour": "#f97316",
            "tooltip": "一直重复执行，直到点击停止",
        },
    },
]


def get_schema() -> dict:
    return {
        "version": 1,
        "categories": CATEGORIES,
        "blocks": BLOCKS,
    }


BLOCK_TYPES = {b["type"] for b in BLOCKS}
