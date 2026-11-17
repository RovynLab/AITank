# -*- coding: utf-8 -*-
"""petcar/core/color_cfg.py — 颜色阈值唯一数据源
===============================================
中控面板、积木、PID 追踪统一读这个模块，解决 "面板调好的阈值与积木不通" 的坑。

用法:
    from petcar.core.color_cfg import get_cfg, get_custom, set_custom, COLOR_PRESETS
    cfg = get_cfg("red")       # 预设
    cfg = get_cfg("custom")    # 面板当前值
    set_custom({"h_min": 10})  # 面板保存
"""

from __future__ import annotations

import copy
import threading

# OpenCV HSV: H 0~180, S/V 0~255
COLOR_PRESETS: dict[str, dict] = {
    "red":    {"label": "红色",   "h_min": 170, "h_max": 10,  "s_min": 120, "s_max": 255, "v_min": 80,  "v_max": 255},
    "orange": {"label": "橙色",   "h_min": 8,   "h_max": 22,  "s_min": 120, "s_max": 255, "v_min": 100, "v_max": 255},
    "yellow": {"label": "黄色",   "h_min": 23,  "h_max": 38,  "s_min": 90,  "s_max": 255, "v_min": 90,  "v_max": 255},
    "green":  {"label": "绿色",   "h_min": 45,  "h_max": 80,  "s_min": 80,  "s_max": 255, "v_min": 70,  "v_max": 255},
    "cyan":   {"label": "青色",   "h_min": 85,  "h_max": 98,  "s_min": 80,  "s_max": 255, "v_min": 70,  "v_max": 255},
    "blue":   {"label": "蓝色",   "h_min": 100, "h_max": 125, "s_min": 80,  "s_max": 255, "v_min": 60,  "v_max": 255},
    "purple": {"label": "紫色",   "h_min": 130, "h_max": 165, "s_min": 60,  "s_max": 255, "v_min": 60,  "v_max": 255},
}

# custom 默认值（最初写死在感知线程里的黄绿色 H 25~45）
_DEFAULT_CUSTOM = {"label": "自定义", "h_min": 25, "h_max": 45, "s_min": 90, "s_max": 255, "v_min": 90, "v_max": 255}

_lock = threading.RLock()
_custom = dict(_DEFAULT_CUSTOM)

# 允许作为 key 的集合（catalog.COLORS + "custom"）
VALID_KEYS = set(COLOR_PRESETS.keys()) | {"custom"}


def get_cfg(key: str) -> dict:
    """按 key 取阈值；key 非法时回退 custom"""
    if key == "custom" or key is None:
        return get_custom()
    preset = COLOR_PRESETS.get(key)
    if preset is None:
        return get_custom()
    return copy.deepcopy(preset)


def get_custom() -> dict:
    """读面板当前 custom 阈值（深拷贝，避免外部污染）"""
    with _lock:
        return copy.deepcopy(_custom)


def set_custom(updates: dict) -> dict:
    """写 custom 阈值，带钳位和线程安全，返回更新后的完整 dict"""
    if not isinstance(updates, dict):
        return get_custom()
    with _lock:
        for k, v in updates.items():
            if k not in _DEFAULT_CUSTOM or k == "label":
                continue
            try:
                v = int(v)
            except (TypeError, ValueError):
                continue
            if k.startswith("h"):
                v = max(0, min(180, v))
            else:
                v = max(0, min(255, v))
            _custom[k] = v
        return copy.deepcopy(_custom)


def reset_custom() -> dict:
    """恢复 custom 到默认值"""
    with _lock:
        _custom.clear()
        _custom.update(_DEFAULT_CUSTOM)
        return copy.deepcopy(_custom)


def all_keys() -> list[str]:
    """返回所有颜色 key，包括 custom"""
    return list(COLOR_PRESETS.keys()) + ["custom"]
