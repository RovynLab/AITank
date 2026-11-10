# -*- coding: utf-8 -*-
"""
core/llm_backends.py — LLM 后端抽象
=====================================
三个实现: Ollama (本地), Doubao (火山引擎), Mock (规则引擎)
"""

from __future__ import annotations

import sys
import os
import re
import json
import time
import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar import config


class LLMBackend(ABC):
    """LLM 后端抽象基类"""

    @abstractmethod
    def chat(self, messages: List[dict], tools: List[dict]) -> dict:
        """
        返回:
        {
            "content": str,
            "tool_calls": [{"name": str, "arguments": dict}],
            "usage": {...}  (可选)
        }
        """
        ...


# ============================================================================
# Ollama (本地)
# ============================================================================

class OllamaBackend(LLMBackend):
    """调用本地 Ollama HTTP API"""

    def __init__(self, host: Optional[str] = None,
                 model: Optional[str] = None):
        # 默认值在运行时读取, 面板改完配置重建后端即可生效
        host = config.OLLAMA_HOST if host is None else host
        model = config.OLLAMA_MODEL if model is None else model
        self.host = host
        self.model = model
        self._lock = threading.Lock()
        print(f"[Ollama] 目标: {host} / {model}")

    def chat(self, messages: List[dict], tools: List[dict]) -> dict:
        import requests
        url = f"{self.host}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            # 树莓派上 0.5B 速度约 7 token/s, 限制长度避免对话超时 (面板可调)
            "options": {"num_predict": config.LLM_NUM_PREDICT,
                        "temperature": config.LLM_TEMPERATURE,
                        "num_ctx": 2048, "num_batch": 128},
        }
        if tools:
            payload["tools"] = tools

        with self._lock:
            try:
                resp = requests.post(url, json=payload, timeout=config.LLM_TIMEOUT)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"[Ollama] 调用失败: {e}")
                raise

        msg = data.get("message", {})
        content = msg.get("content", "")
        # Ollama tool_calls 格式跟 OpenAI 类似
        raw_calls = msg.get("tool_calls") or []
        tool_calls = []
        for tc in raw_calls:
            func = tc.get("function", {})
            args_str = func.get("arguments", "{}")
            try:
                args = json.loads(args_str)
            except Exception:
                args = {}
            tool_calls.append({
                "name": func.get("name", ""),
                "arguments": args,
            })

        return {"content": content, "tool_calls": tool_calls}


# ============================================================================
# Doubao (火山引擎, 可选)
# ============================================================================

class DoubaoBackend(LLMBackend):
    """火山引擎 Doubao API"""

    def __init__(self, api_key: Optional[str] = None,
                 model: Optional[str] = None):
        self.api_key = config.DOUBAO_API_KEY if api_key is None else api_key
        self.model = config.DOUBAO_MODEL if model is None else model

    def chat(self, messages: List[dict], tools: List[dict]) -> dict:
        import requests
        import json as _json
        # 火山引擎 Ark API (兼容 OpenAI 格式)
        url = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": config.LLM_TEMPERATURE,
            "max_tokens": config.LLM_NUM_PREDICT,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        resp = requests.post(url, headers=headers, json=payload,
                             timeout=config.LLM_TIMEOUT)
        data = resp.json()
        # 兼容处理
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"Doubao 返回异常: {data}")
        msg = choices[0].get("message", {})
        content = msg.get("content", "")
        raw_calls = msg.get("tool_calls") or []
        tool_calls = []
        for tc in raw_calls:
            func = tc.get("function", {})
            args_str = func.get("arguments", "{}")
            try:
                args = _json.loads(args_str)
            except Exception:
                args = {}
            tool_calls.append({"name": func.get("name", ""), "arguments": args})
        return {"content": content, "tool_calls": tool_calls}


# ============================================================================
# MockBackend —— 规则引擎 (无 LLM 也能跑)
# ============================================================================

class MockBackend(LLMBackend):
    """基于正则匹配的规则引擎，用于无 LLM 环境"""

    # 每一条: (regex_pattern, (reply, emotion, [tool_call_name]))
    # 重要: 规则按优先级排序，越具体越靠前！
    RULES: List[Tuple[str, Tuple]] = [
        # ========== 打招呼 ==========
        (r"(你好|hi|hello|在吗|哈喽)", ("你好呀~我是{pet_name}，很开心认识你！", "happy")),
        (r"再见|拜拜|晚安", ("好的拜拜~下次再聊哦", "neutral")),
        (r"早安|早上好", ("早上好呀！今天想做点什么？", "happy")),

        # ========== 表情控制 (必须放在通用情感规则前面) ==========
        (r"开心一下|笑一下|高兴一下", (None, "happy", "show_emotion", {"emotion": "happy"})),
        (r"(难过|伤心|哭)", (None, "sad", "show_emotion", {"emotion": "sad"})),
        (r"(生气|怒).*(一下|表情)", (None, "angry", "show_emotion", {"emotion": "angry"})),
        (r"(惊讶|吃惊).*(一下|表情)", (None, "surprised", "show_emotion", {"emotion": "surprised"})),
        (r"(睡觉|困|累).*(一下|表情)", (None, "sleepy", "show_emotion", {"emotion": "sleepy"})),
        (r"(爱|喜欢|亲).*(一下|表情)", (None, "love", "show_emotion", {"emotion": "love"})),
        (r"(眨眼|放电)", (None, "happy", "show_emotion", {"emotion": "wink"})),
        (r"(困惑|不懂).*(一下|表情)", (None, "confused", "show_emotion", {"emotion": "confused"})),

        # ========== 查天气 ==========
        (r"天气|下雨|气温", (None, "thinking", "weather", {})),

        # ========== 运动 ==========
        (r"(往前走|前进|向前|走一下)", (None, "happy", "move", {"direction": "forward", "duration": 2})),
        (r"(后退|往后走)", (None, "happy", "move", {"direction": "backward", "duration": 2})),
        (r"(左转|向左走)", (None, "happy", "move", {"direction": "turnLeft", "duration": 2})),
        (r"(右转|向右走)", (None, "happy", "move", {"direction": "turnRight", "duration": 2})),
        (r"转圈|转一下", (None, "happy", "move", {"direction": "spin", "duration": 3})),
        (r"停", ("好的，我停下啦", "happy")),

        # ========== 云台 ==========
        (r"(抬头|向上看|往上)", (None, "neutral", "look", {"direction": "up", "delta": 15})),
        (r"(低头|向下看|往下)", (None, "neutral", "look", {"direction": "down", "delta": 15})),
        (r"左看", (None, "neutral", "look", {"direction": "left", "delta": 15})),
        (r"右看", (None, "neutral", "look", {"direction": "right", "delta": 15})),

        # ========== 视觉 ==========
        (r"(拍.*?照|照片|拍一张)", (None, "happy", "take_photo", {})),
        (r"(看看我|盯着我|追踪我|跟着我)", (None, "love", "track_face", {})),
        (r"(停止追踪|别看了)", ("好的~", "neutral")),
        (r"(有人吗|看到人吗|有人脸吗)", (None, "thinking", "detect_face", {})),

        # ========== 闹钟 ==========
        (r"(闹钟|提醒|倒计时).*?(\d+)\s*(秒|分钟)", ("好的，我记住啦！", "happy")),

        # ========== 情感/人格 (通用，放最后) ==========
        (r"你是谁|你叫什么|介绍自己", ("我叫{pet_name}，是你的编程小伙伴~", "happy")),
        (r"(心情|开心|难过|怎么样)", ("我现在心情还不错，你呢？", "happy")),
        (r"(生气|讨厌|烦)", ("呜...我好难过，别生气好不好", "sad")),
        (r"(谢谢|感谢|棒)", ("嘿嘿~谢谢你呀！", "love")),
        (r"(唱|歌|笑一个)", ("嘿嘿嘿~", "laugh")),
    ]

    def chat(self, messages: List[dict], tools: List[dict]) -> dict:
        # 取最后一条用户消息
        last_user = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user = msg.get("content", "")
                break

        if not last_user:
            return {"content": "嗯？你想说啥？", "tool_calls": []}

        text = last_user.strip()

        for pattern, action in self.RULES:
            if re.search(pattern, text):
                return self._action_to_response(action)

        # fallback
        return {
            "content": f"嗯嗯，我听到你说「{text[:15]}」啦~",
            "tool_calls": [],
        }

    def _action_to_response(self, action: Tuple) -> dict:
        # action 可能是 (reply, emotion) 或 (None, emotion, tool_name, tool_args)
        tool_calls = []
        if len(action) >= 3 and action[0] is None:
            # 有工具调用
            tool_name = action[2]
            tool_args = action[3] if len(action) > 3 else {}
            tool_calls.append({"name": tool_name, "arguments": tool_args})
            # 工具调用时 content 给一个引导语
            content = f"好的，我来 {tool_name}..."
        else:
            content = (action[0] or "").format(pet_name=config.PET_NAME)

        return {"content": content, "tool_calls": tool_calls}


# ============================================================================
# 工厂
# ============================================================================

def create_llm_backend(backend: Optional[str] = None) -> LLMBackend:
    """根据配置创建后端，并检测可用性"""
    backend = config.LLM_BACKEND if backend is None else backend
    if backend == "ollama":
        try:
            backend_ = OllamaBackend()
            import requests
            resp = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=3)
            if resp.status_code == 200:
                print(f"[LLM] Ollama 可用, 模型: {config.OLLAMA_MODEL}")
                return backend_
        except Exception as e:
            print(f"[LLM] Ollama 连不上 ({e}), 切 Mock")
        return MockBackend()

    if backend == "doubao":
        if config.DOUBAO_API_KEY:
            return DoubaoBackend()
        print("[LLM] 没配 DOUBAO_API_KEY, 切 Mock")
        return MockBackend()

    # 默认 / mock
    print("[LLM] 使用 MockBackend (规则引擎)")
    return MockBackend()
