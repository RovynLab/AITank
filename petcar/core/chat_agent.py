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
    reply_spoken: bool = False


class ChatAgent:
    """LLM 对话 + 工具调用"""

    # 0.5B 小模型不会稳定输出 tool_calls, 常见动作指令用本地规则直连技能
    _LOCAL_RULES = [
        (r"摇(一)?摇?(摇)?头|摇一摇", "express", {"action": "shake"}, "好的，我来摇头。"),
        (r"点(一)?点?头", "express", {"action": "nod"}, "好的，我来点头。"),
        (r"歪(一)?歪?头", "express", {"action": "tilt"}, "好的，我歪歪头~"),
        (r"跳舞|跳个舞", "express", {"action": "dance"}, "好呀，我跳个舞~"),
        (r"抬(一)?抬头|向上看|往上看", "look", {"direction": "up", "delta": 15}, "好的，我抬头看~"),
        (r"低(一)?低头|向下看|往下看", "look", {"direction": "down", "delta": 15}, "好的，我低头看~"),
        (r"向左看|往左看|看左边", "look", {"direction": "left", "delta": 15}, "好的，我往左看~"),
        (r"向右看|往右看|看右边", "look", {"direction": "right", "delta": 15}, "好的，我往右看~"),
        (r"左转|向左转", "move", {"direction": "turnLeft", "duration": 2}, "好的，我左转~"),
        (r"右转|向右转", "move", {"direction": "turnRight", "duration": 2}, "好的，我右转~"),
        (r"转(一)?个?圈|旋转|转一下", "move", {"direction": "spin", "duration": 3}, "好的，我转个圈~"),
        (r"往前走|前进|向前走|往前走", "move", {"direction": "forward", "duration": 2}, "好的，我往前走~"),
        (r"后退|往后走|往后退", "move", {"direction": "backward", "duration": 2}, "好的，我后退一点~"),
        (r"停下|停止|别动", "move", {"direction": "stop"}, "好的，我停下啦"),
        (r"拍(一)?张?照|拍照|相片", "take_photo", {}, "好的，我来拍照。"),
    ]

    _TRAD = str.maketrans({
        "搖": "摇", "頭": "头", "轉": "转", "後": "后", "動": "动",
        "個": "个", "張": "张", "點": "点", "圈": "圈", "請": "请",
    })

    def _match_local_command(self, text: str):
        """仅识别动作，不执行；由 chat 在播报确认后执行。"""
        if not text:
            return None
        t = text.translate(self._TRAD)
        for pattern, name, args, reply in self._LOCAL_RULES:
            if re.search(pattern, t):
                return name, dict(args), reply.replace("~", "。")
        return None

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
        self._action_lock = threading.Lock()

        self._build_system_prompt()
        print(f"[ChatAgent] 已初始化, backend={type(self.backend).__name__}")

    # ========================================================================
    def _build_system_prompt(self):
        tools_prompt = self.skills.list_tools_prompt()
        self._system_prompt = f"""你是一只名叫 {config.PET_NAME} 的编程小伙伴机器人，住在一台小车上。
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
回复: <reply>你好呀！我是{config.PET_NAME}~</reply><emotion>happy</emotion>

用户: 帮我查天气
回复: <reply>好的，让我查一下！</reply><emotion>thinking</emotion><tool_call>{{"name": "weather", "args": {{"city": "北京"}}}}</tool_call>
"""

    def apply_config(self, rebuild_backend: bool = True):
        """面板改完身份 / LLM 配置后重建人格提示词 (可选重建后端)"""
        if rebuild_backend:
            self.backend = create_llm_backend()
        self._build_system_prompt()
        print(f"[ChatAgent] 配置已应用, backend={type(self.backend).__name__}")

    def register_skill(self, skill):
        self.skills.register(skill)
        # 重建 system prompt (让 LLM 看到新工具)
        self._build_system_prompt()

    # ========================================================================
    def chat(self, user_text: str, max_tool_rounds: int = 3,
             before_action=None) -> ChatResponse:
        """
        一轮完整对话:
        1. 把用户输入加入 messages
        2. 调 LLM
        3. 解析 tool_calls → 执行 → 把结果塞回 messages → 再调一次 LLM
        4. 最终从回复里提取 <reply> 和 <emotion>
        5. 通知 MoodEngine 更新情感
        """
        local = self._match_local_command(user_text)
        if local is not None:
            name, args, reply = local
            immediate_stop = name == "move" and args.get("direction") == "stop"
            spoken = False
            if immediate_stop:
                self.skills.execute(name, **args)
            else:
                with self._action_lock:
                    if before_action:
                        before_action(reply, "happy")
                        spoken = True
                    self.skills.execute(name, **args)
            # An unrelated slow LLM request must not delay a local command.
            if self._lock.acquire(blocking=False):
                try:
                    self._messages.extend([
                        {"role": "user", "content": user_text},
                        {"role": "assistant", "content": reply},
                    ])
                    self._trim_history()
                finally:
                    self._lock.release()
            print(f"[ChatAgent] 本地指令 → {name} {args}")
            return ChatResponse(reply=reply, emotion="happy",
                                tools_called=[name], reply_spoken=spoken)

        with self._lock:
            self._messages.append({"role": "user", "content": user_text})
            self._trim_history()

            all_tool_calls: List[str] = []
            final_content = ""
            executed_tool_signatures: set = set()  # (name, json_args) → 检测重复
            spoken_replies = []

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

                        if (before_action and name in {
                                "express", "look", "move", "take_photo",
                                "track_face", "show_emotion"}
                                and not (name == "move" and args.get("direction") == "stop")):
                            acknowledgements = {
                                "express": "好的，我来做这个动作。",
                                "look": "好的，我来转动云台。",
                                "move": "好的，我来移动。",
                                "take_photo": "好的，我来拍照。",
                                "track_face": "好的，我来追踪人脸。",
                                "show_emotion": "好的，我来换个表情。",
                            }
                            acknowledgement = acknowledgements[name]
                            before_action(acknowledgement, "happy")
                            spoken_replies.append(acknowledgement)
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
            reply_spoken=reply in spoken_replies,
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
        if not reply:
            # 小参数模型常不按格式输出, 兜底: 去掉残留标记再当正文
            text = re.sub(r"</?[a-zA-Z_]+>", "", content)
            text = re.sub(r"emotion\s*[:：].*", "", text, flags=re.I | re.S)
            reply = " ".join(text.split())
        return reply, emotion

    # ========================================================================
    def reset(self):
        with self._lock:
            self._messages.clear()
        self._build_system_prompt()
