# -*- coding: utf-8 -*-
"""
core/chat_agent.py — 大模型对话代理
=====================================
把 messages + tools 交给 LLM, 拿到回复, 执行 tool_calls, 循环直到没工具调用。
最终返回 ChatResponse。
"""

from __future__ import annotations

import sys
import os
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar import config
from petcar.core.llm_backends import LLMBackend, create_llm_backend
from petcar.core.skill_manager import SkillManager


@dataclass
class ChatResponse:
    reply: str = ""
    emotion: str = "neutral"
    tools_called: List[str] = field(default_factory=list)
    raw_llm_content: str = ""


class ChatAgent:
    """LLM 对话 + 工具调用"""

    def __init__(self,
                 backend: Optional[LLMBackend] = None,
                 mood_engine=None,
                 skill_manager: Optional[SkillManager] = None):
        self.backend = backend or create_llm_backend()
        self.mood_engine = mood_engine
        self.skills = skill_manager or SkillManager()

        # 对话历史 (最多 20 条)
        self._messages: List[dict] = []
        self._max_history = 20
        self._lock = threading.Lock()

        self._build_system_prompt()
        print(f"[ChatAgent] 已初始化, backend={type(self.backend).__name__}")

    # ========================================================================
    def _build_system_prompt(self):
        tools_prompt = self.skills.list_tools_prompt()
        self._system_prompt = f"""你是一只名叫 {config.PET_NAME} 的 AI 宠物机器人，住在一台小车上。
性格: {config.PET_PERSONALITY}

## 回答格式
每次回复都用以下三个标签包裹，不要额外内容：
<reply>你想说的话 (30字以内，口语化)</reply>
<emotion>从 [happy, sad, angry, surprised, love, neutral, thinking, sleepy, scared] 中选一个最贴切的</emotion>

## 工具调用
当你需要调用工具时，在 <tool_call> 标签里写 JSON：
<tool_call>{{"name": "工具名", "args": {{...}}}}</tool_call>
等工具执行完，下一轮再继续回答。

## 可用工具列表
{tools_prompt}

## 示例
用户: 你好
回复: <reply>你好呀！我是小宝~</reply><emotion>happy</emotion>

用户: 帮我查天气
回复: <reply>好的，让我查一下！</reply><emotion>thinking</emotion><tool_call>{{"name": "weather", "args": {{"city": "北京"}}}}</tool_call>
"""

    def register_skill(self, skill):
        self.skills.register(skill)
        # 重建 system prompt (让 LLM 看到新工具)
        self._build_system_prompt()

    # ========================================================================
    def chat(self, user_text: str, max_tool_rounds: int = 3) -> ChatResponse:
        """
        一轮完整对话:
        1. 把用户输入加入 messages
        2. 调 LLM
        3. 解析 tool_calls → 执行 → 把结果塞回 messages → 再调一次 LLM
        4. 最终从回复里提取 <reply> 和 <emotion>
        5. 通知 MoodEngine 更新情感
        """
        with self._lock:
            self._messages.append({"role": "user", "content": user_text})
            self._trim_history()

            all_tool_calls: List[str] = []
            final_content = ""
            executed_tool_signatures: set = set()  # (name, json_args) → 检测重复

            for round_i in range(max_tool_rounds):
                # 组装 messages: system + history
                messages = self._build_messages()
                tools = self.skills.list_tool_specs()

                try:
                    result = self.backend.chat(messages, tools)
                except Exception as e:
                    print(f"[ChatAgent] LLM 调用失败: {e}")
                    self._messages.append({
                        "role": "assistant",
                        "content": f"抱歉，我好像出了点小问题... ({e})",
                    })
                    return ChatResponse(
                        reply=f"抱歉，我好像出了点小问题... ({e})",
                        emotion="neutral",
                    )

                content = result.get("content", "")
                tool_calls = result.get("tool_calls", [])
                final_content = content

                if tool_calls:
                    # 检测是否有重复的 tool_call (name + args 完全相同)
                    import json as _json
                    deduplicated = []
                    for tc in tool_calls:
                        sig = (tc.get("name", ""), _json.dumps(tc.get("arguments", {}),
                                                                sort_keys=True, default=str))
                        if sig in executed_tool_signatures:
                            # 已经执行过了，跳过
                            continue
                        executed_tool_signatures.add(sig)
                        deduplicated.append(tc)

                    if not deduplicated:
                        # 所有 tool_call 都是重复的，结束
                        break
                    tool_calls = deduplicated

                    # 记录 assistant 的 tool_call 消息
                    self._messages.append({
                        "role": "assistant",
                        "content": content,
                        "tool_calls": [
                            {"type": "function",
                             "function": {"name": tc["name"],
                                          "arguments": str(tc["arguments"])}}
                            for tc in tool_calls
                        ],
                    })

                    # 执行每个工具
                    for tc in tool_calls:
                        name = tc["name"]
                        args = tc.get("arguments", {})
                        print(f"[ChatAgent] 调用工具: {name}({args})")
                        all_tool_calls.append(name)

                        tool_result = self.skills.execute(name, **args)
                        print(f"[ChatAgent]   → {tool_result[:80]}")

                        self._messages.append({
                            "role": "tool",
                            "content": tool_result,
                            "name": name,
                        })
                else:
                    # 没工具调用了，结束
                    break

            # 最后一条 assistant 消息
            self._messages.append({"role": "assistant", "content": final_content})

        # 解析最终内容
        reply, emotion = self._extract_reply_and_emotion(final_content)

        # 通知 MoodEngine
        if self.mood_engine and emotion:
            self.mood_engine.trigger(emotion, intensity=0.8)

        return ChatResponse(
            reply=reply or final_content[:60],
            emotion=emotion or "neutral",
            tools_called=all_tool_calls,
            raw_llm_content=final_content,
        )

    # ========================================================================
    def _build_messages(self) -> List[dict]:
        # system + history
        msgs = [{"role": "system", "content": self._system_prompt}]
        msgs.extend(self._messages)
        return msgs

    def _trim_history(self):
        # 保持 user/assistant 交替, 去掉最早的
        while len(self._messages) > self._max_history:
            self._messages.pop(0)
            # 如果最早的是 tool, 再多删一条 assistant
            while self._messages and self._messages[0].get("role") == "tool":
                self._messages.pop(0)

    def _extract_reply_and_emotion(self, content: str) -> tuple:
        """从 LLM 回复里提取 <reply>...</reply> 和 <emotion>...</emotion>"""
        reply = ""
        emotion = ""
        m = re.search(r"<reply>(.*?)</reply>", content, re.DOTALL)
        if m:
            reply = m.group(1).strip()
        m = re.search(r"<emotion>(.*?)</emotion>", content)
        if m:
            emotion = m.group(1).strip().lower()
            # 校验
            valid = {"happy", "sad", "angry", "surprised", "love", "neutral",
                     "thinking", "sleepy", "scared", "confused", "laugh", "wink"}
            if emotion not in valid:
                emotion = "neutral"
        return reply, emotion

    # ========================================================================
    def reset(self):
        with self._lock:
            self._messages.clear()
        self._build_system_prompt()
