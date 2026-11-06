# -*- coding: utf-8 -*-
"""
core/skill_manager.py — Skill 注册 + 调度
==========================================
给 ChatAgent 调用。
"""

from __future__ import annotations

import sys
import os
from typing import Any, Dict, List

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar.skills.base_skill import BaseSkill


class SkillManager:
    """技能管理器"""

    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill):
        """注册一个 skill"""
        self._skills[skill.name] = skill
        skill.on_register()
        print(f"[SkillManager] 注册: {skill.name}")

    def unregister(self, name: str):
        if name in self._skills:
            sk = self._skills.pop(name)
            sk.on_unregister()

    def get(self, name: str) -> BaseSkill | None:
        return self._skills.get(name)

    def list(self) -> List[str]:
        return list(self._skills.keys())

    def execute(self, name: str, **kwargs) -> str:
        """执行一个 skill，返回结果字符串"""
        sk = self._skills.get(name)
        if sk is None:
            return f"抱歉，我不知道怎么 '{name}' 呢"
        try:
            return sk.execute(**kwargs)
        except TypeError as e:
            return f"参数不对哦: {e}"
        except Exception as e:
            return f"执行出错了: {e}"

    def list_tools_prompt(self) -> str:
        """生成给 LLM 的工具列表文本"""
        if not self._skills:
            return "(当前没有可用工具)"
        return "\n".join(sk.get_tool_prompt() for sk in self._skills.values())

    def list_tool_specs(self) -> List[dict]:
        """生成 OpenAI function calling 格式的工具列表"""
        return [sk.get_openai_tool_spec() for sk in self._skills.values()]
