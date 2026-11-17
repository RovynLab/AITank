# -*- coding: utf-8 -*-
"""
core/llm_backends.py — LLM 后端抽象
=====================================
两个实现: Ollama (本地), Doubao (火山引擎)
"""

from __future__ import annotations

import sys
import os
import json
import threading
from abc import ABC, abstractmethod
from typing import List, Optional

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
# 工厂
# ============================================================================

def create_llm_backend(backend: Optional[str] = None) -> LLMBackend:
    """根据配置创建后端"""
    backend = config.LLM_BACKEND if backend is None else backend
    if backend == "ollama":
        print(f"[LLM] Ollama, 模型: {config.OLLAMA_MODEL}")
        return OllamaBackend()

    if backend == "doubao":
        if not config.DOUBAO_API_KEY:
            print("[LLM] 警告: 未配置 DOUBAO_API_KEY, 对话会调用失败")
        return DoubaoBackend()

    raise ValueError(f"未知 LLM 后端: {backend}")

