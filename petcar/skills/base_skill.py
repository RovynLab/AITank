# -*- coding: utf-8 -*-
"""
skills/base_skill.py — Skill 基类
================================
所有本地工具继承这个类，实现 execute()。
"""

from __future__ import annotations

import sys
import os
from abc import ABC, abstractmethod
from typing import Any, Dict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


class BaseSkill(ABC):
    """本地工具基类"""

    # 子类必须填这三个:
    name: str = "base"
    description: str = "基类，不应该直接使用"
    parameters: Dict[str, Any] = {"type": "object", "properties": {}}

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """执行工具，返回给 LLM / 用户的结果字符串"""
        ...

    # ---- 可选: 生命周期 ----
    def on_register(self):
        """被 SkillManager 注册时调用，可用于连接硬件等"""
        pass

    def on_unregister(self):
        pass

    # ---- 给 LLM 的描述 ----
    def get_tool_prompt(self) -> str:
        """给 system prompt 里用的文本描述"""
        param_desc = self._param_text()
        return f"- {self.name}: {self.description}\n  参数: {param_desc}"

    def get_openai_tool_spec(self) -> dict:
        """OpenAI / Ollama function calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def _param_text(self) -> str:
        props = self.parameters.get("properties", {})
        req = self.parameters.get("required", [])
        if not props:
            return "无"
        parts = []
        for k, v in props.items():
            t = v.get("type", "any")
            d = v.get("description", "")
            enum = v.get("enum", [])
            req_mark = "*" if k in req else ""
            enum_str = f" [{', '.join(enum)}]" if enum else ""
            parts.append(f"{k}{req_mark}: {t}{enum_str} ({d})")
        return ", ".join(parts)
