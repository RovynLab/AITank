# -*- coding: utf-8 -*-
"""petcar/blocks/compiler.py — Blockly JSON → IR
================================================
只接受白名单积木，输出解释器可直接执行的简单 AST。
不做变量、表达式、嵌套事件。
"""

from __future__ import annotations

from .catalog import (BLOCK_TYPES, ACTIONS, COLORS, EMOTIONS, GESTURES,
                      MOTIONS, PTZ_DIRS, TARGETS, TRACK_TARGETS,
                      WAIT_TARGETS)

MAX_BLOCKS = 300
MAX_DEPTH = 15

_MOTION_DIRS = {v for _, v in MOTIONS}
_PTZ_DIRS = {v for _, v in PTZ_DIRS}
_EMOTIONS = {v for _, v in EMOTIONS}
_TARGETS = {v for _, v in TARGETS}
_COLORS = {v for _, v in COLORS}
_ACTIONS = {v for _, v in ACTIONS}
_GESTURES = {v for _, v in GESTURES}
_TRACK_TARGETS = {v for _, v in TRACK_TARGETS}
_WAIT_TARGETS = {v for _, v in WAIT_TARGETS}


class CompileError(Exception):
    """编译失败，errors 为 [{blockId, message}]"""

    def __init__(self, errors):
        super().__init__("; ".join(e["message"] for e in errors))
        self.errors = errors


def _fail(block: dict, message: str):
    raise CompileError([{
        "blockId": block.get("id"),
        "message": message,
    }])


def _field(block: dict, name: str, label: str) -> str:
    fields = block.get("fields") or {}
    value = fields.get(name)
    if value is None:
        _fail(block, f"积木缺少「{label}」")
    return value


def _num(block: dict, name: str, label: str,
         low: float, high: float) -> float:
    fields = block.get("fields") or {}
    try:
        value = float(fields.get(name))
    except (TypeError, ValueError):
        _fail(block, f"「{label}」必须是一个数字")
    if value < low or value > high:
        _fail(block, f"「{label}」必须在 {low:g} 到 {high:g} 之间")
    return value


def _next_block(block: dict) -> dict | None:
    nxt = block.get("next")
    return nxt.get("block") if isinstance(nxt, dict) else None


def _statement_body(block: dict, name: str, depth: int,
                    counter: dict, ctx: dict) -> list:
    inputs = block.get("inputs") or {}
    slot = inputs.get(name) or {}
    first = slot.get("block") or slot.get("shadow")
    return _compile_chain(first, depth + 1, counter, ctx)


def _compile_chain(first: dict | None, depth: int, counter: dict,
                   ctx: dict) -> list:
    body = []
    block = first
    while block:
        if depth > MAX_DEPTH:
            _fail(block, f"积木嵌套太深（最多 {MAX_DEPTH} 层）")
        counter["n"] += 1
        if counter["n"] > MAX_BLOCKS:
            _fail(block, f"积木太多了（最多 {MAX_BLOCKS} 块）")
        body.append(_compile_block(block, depth, counter, ctx))
        block = _next_block(block)
    return body


def _record_color(ctx: dict, key: str):
    ctx.setdefault("used_colors", set()).add(key)


def _record_gesture(ctx: dict, key: str):
    ctx.setdefault("used_gestures", set()).add(key)


def _record_target(ctx: dict, target: str):
    """按等待/追踪目标记录需要感知的颜色或手势"""
    if target in _COLORS:
        _record_color(ctx, target)
    elif target.startswith("gesture:"):
        key = target.split(":", 1)[1]
        if key:
            _record_gesture(ctx, key)


def _compile_block(block: dict, depth: int, counter: dict,
                   ctx: dict) -> dict:
    btype = block.get("type")
    bid = block.get("id")

    if btype not in BLOCK_TYPES:
        _fail(block, f"不认识的积木: {btype}")

    if btype == "move_for":
        direction = _field(block, "DIR", "方向")
        if direction not in _MOTION_DIRS:
            _fail(block, f"不支持的移动方向: {direction}")
        return {
            "op": "move_for",
            "id": bid,
            "dir": direction,
            "speed": int(_num(block, "SPEED", "速度", 50, 255)),
            "seconds": _num(block, "SECONDS", "移动时间", 0.1, 30),
        }

    if btype == "move_stop":
        return {"op": "move_stop", "id": bid}

    if btype == "wait":
        return {
            "op": "wait",
            "id": bid,
            "seconds": _num(block, "SECONDS", "等待时间", 0, 600),
        }

    if btype == "wait_until":
        target = _field(block, "TARGET", "等待目标")
        if target not in _WAIT_TARGETS:
            _fail(block, f"不支持的等待目标: {target}")
        _record_target(ctx, target)
        return {
            "op": "wait_until",
            "id": bid,
            "target": target,
            "timeout": _num(block, "TIMEOUT", "最长等待", 0.5, 60),
        }

    if btype == "look":
        direction = _field(block, "DIR", "方向")
        if direction not in _PTZ_DIRS:
            _fail(block, f"不支持的云台方向: {direction}")
        return {
            "op": "look",
            "id": bid,
            "dir": direction,
            "degrees": _num(block, "DEGREES", "转动角度", 1, 45),
        }

    if btype == "show_emotion":
        emotion = _field(block, "EMOTION", "表情")
        if emotion not in _EMOTIONS:
            _fail(block, f"不支持的表情: {emotion}")
        return {"op": "emotion", "id": bid, "name": emotion}

    if btype == "do_action":
        action = _field(block, "ACTION", "动作")
        if action not in _ACTIONS:
            _fail(block, f"不支持的动作: {action}")
        return {"op": "action", "id": bid, "name": action}

    if btype == "say":
        text = str(_field(block, "TEXT", "说话内容")).strip()
        if not text:
            _fail(block, "说话内容不能为空")
        if len(text) > 100:
            _fail(block, "说话内容最多 100 个字")
        return {"op": "say", "id": bid, "text": text}

    if btype == "photo":
        return {"op": "photo", "id": bid}

    if btype == "if_sees":
        target = _field(block, "TARGET", "识别目标")
        if target not in _TARGETS:
            _fail(block, f"不支持的识别目标: {target}")
        # "颜色" target 实际走 custom
        if target == "color":
            _record_color(ctx, "custom")
        return {
            "op": "if_sees",
            "id": bid,
            "target": target,
            "body": _statement_body(block, "DO", depth, counter, ctx),
        }

    # ---------- 手势识别新积木 ----------
    if btype == "if_gesture":
        gesture = _field(block, "GESTURE", "手势")
        if gesture not in _GESTURES:
            _fail(block, f"不支持的手势: {gesture}")
        _record_gesture(ctx, gesture)
        return {
            "op": "if_gesture",
            "id": bid,
            "gesture": gesture,
            "body": _statement_body(block, "DO", depth, counter, ctx),
            "else": _statement_body(block, "ELSE", depth, counter, ctx),
        }

    # ---------- 颜色识别新积木 ----------
    if btype == "if_sees_color":
        color = _field(block, "COLOR", "颜色")
        if color not in _COLORS:
            _fail(block, f"不支持的颜色: {color}")
        _record_color(ctx, color)
        return {
            "op": "if_sees_color",
            "id": bid,
            "color": color,
            "body": _statement_body(block, "DO", depth, counter, ctx),
            "else": _statement_body(block, "ELSE", depth, counter, ctx),
        }

    if btype == "color_track_start":
        color = _field(block, "COLOR", "颜色")
        if color not in _COLORS:
            _fail(block, f"不支持的颜色: {color}")
        _record_color(ctx, color)
        return {
            "op": "color_track_start",
            "id": bid,
            "color": color,
        }

    if btype == "color_track_stop":
        return {
            "op": "color_track_stop",
            "id": bid,
        }

    if btype == "track_start":
        target = _field(block, "TARGET", "追踪目标")
        if target not in _TRACK_TARGETS:
            _fail(block, f"不支持的追踪目标: {target}")
        _record_target(ctx, target)
        return {
            "op": "track_start",
            "id": bid,
            "target": target,
        }

    if btype == "track_stop":
        return {
            "op": "track_stop",
            "id": bid,
        }

    if btype == "repeat":
        times = int(_num(block, "TIMES", "重复次数", 1, 100))
        return {
            "op": "repeat",
            "id": bid,
            "times": times,
            "body": _statement_body(block, "DO", depth, counter, ctx),
        }

    if btype == "forever":
        return {
            "op": "forever",
            "id": bid,
            "body": _statement_body(block, "DO", depth, counter, ctx),
        }

    _fail(block, f"积木暂未实现: {btype}")


def compile_program(workspace: dict) -> dict:
    """把 Blockly workspace JSON 编译成 IR。

    兼容两种结构：
      {"blocks": {"languageVersion": 0, "blocks": [...]}}
      {"blocks": [...]}
    """
    if not isinstance(workspace, dict):
        raise CompileError([{"blockId": None, "message": "程序格式不正确"}])

    root = workspace.get("blocks")
    if isinstance(root, dict):
        top = root.get("blocks") or []
    elif isinstance(root, list):
        top = root
    else:
        top = []

    starts = [b for b in top
              if isinstance(b, dict) and b.get("type") == "event_start"]

    if not starts:
        raise CompileError([{
            "blockId": None,
            "message": "程序里缺少「当程序开始」积木",
        }])
    if len(starts) > 1:
        raise CompileError([{
            "blockId": starts[1].get("id"),
            "message": "只能有一个「当程序开始」积木",
        }])

    counter = {"n": 1}
    ctx = {"used_colors": set(), "used_gestures": set()}
    body = _compile_chain(_next_block(starts[0]), 0, counter, ctx)

    used_colors = sorted(ctx.get("used_colors") or set())
    used_gestures = sorted(ctx.get("used_gestures") or set())
    return {
        "version": 1,
        "block_count": counter["n"],
        "used_colors": used_colors,
        "used_gestures": used_gestures,
        "hats": [{"event": "start", "body": body}],
    }
