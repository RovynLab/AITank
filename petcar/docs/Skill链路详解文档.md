# AI-PetCar Skill 链路详解

> 版本: v1.0 | 日期: 2026-11-09
>
> 读完本文档，你应该能：
> 1. 画出"用户说话 → 大模型 → 本地 skill → 硬件动作"的完整调用路径
> 2. 看懂三条通道（本地规则短路 / function calling / prompt 兜底）的区别和触发条件
> 3. 独立新增一个 skill 并让它自动出现在 LLM 可用工具列表、system prompt、面板 API 里

---

## 目录

- [一、整体架构](#一整体架构)
- [二、四个核心角色](#二四个核心角色)
- [三、三条调用通道](#三三条调用通道)
- [四、完整调用时序](#四完整调用时序)
- [五、所有已有 Skill 速查表](#五所有已有-skill-速查表)
- [六、新增 Skill 实战指南](#六新增-skill-实战指南)
- [七、本地规则短路表 (_LOCAL_RULES)](#七本地规则短路表-_local_rules)
- [八、FAQ](#八faq)

---

## 一、整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                        上层调用入口                                │
│                                                                  │
│  语音交互: VoiceIO._loop() → chat.chat(text)                    │
│  Web 面板: Flask /api/chat?text=xxx → chat.chat(text)          │
│  积木页:  (不走 ChatAgent, 直接 BlockRuntime → 驱动层)            │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────── ChatAgent ──────────────────────────┐
│                                                                 │
│  chat(user_text, max_tool_rounds=3)                            │
│                                                                 │
│  ① _match_local_command(): 正则匹配 _LOCAL_RULES                │
│     └─ 命中? → skills.execute(name, **args) → 直接返回 reply   │
│        (完全绕过 LLM, 适合小模型不稳定场景)                       │
│                                                                 │
│  ② 未命中 → 进入 LLM 原生 function calling 链路                │
│     ├─ skills.list_tool_specs()        ──► 生成 tools 参数       │
│     ├─ skills.list_tools_prompt()      ──► 生成 system prompt  │
│     │                                                                  │
│     ├─ backend.chat(messages, tools)    ──► 调 Ollama/Doubao    │
│     ├─ 解析 result["tool_calls"]        ◄── LLM 决定调什么      │
│     ├─ 去重 (executed_tool_signatures)                          │
│     ├─ 执行: skills.execute(name, **args)  ← 核心回调点        │
│     ├─ 把 tool 结果塞回 messages                                │
│     └─ 循环, 最多 max_tool_rounds=3 轮                         │
│                                                                 │
│  ③ 从最终回复提取 <reply> 和 <emotion> 标签                    │
│  ④ 通知 MoodEngine.trigger(emotion) 更新情感                    │
│  ⑤ 返回 ChatResponse(reply, emotion, tools_called)             │
│                                                                 │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌─────────────────────── SkillManager ────────────────────────────┐
│                                                                 │
│  内部: _skills: Dict[str, BaseSkill]                            │
│                                                                 │
│  execute(name, **kwargs) → str                                  │
│    └─ 查字典 _skills[name] → sk.execute(**kwargs)              │
│                                                                 │
│  list_tool_specs() → List[dict]                                 │
│    └─ [sk.get_openai_tool_spec() for sk in _skills.values()]   │
│                                                                 │
│  list_tools_prompt() → str                                      │
│    └─ "\n".join(sk.get_tool_prompt() for sk in _skills.values())│
│                                                                 │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────── BaseSkill ─────────────────────────┐
│                                                                 │
│  子类必须填三个类属性:                                           │
│    name: str = "xxx"          ← 唯一标识, 同时是 SkillManager   │
│                                 dict key + LLM tool name        │
│    description: str = "..."   ← LLM 看的工具描述                │
│    parameters: dict = {...}   ← OpenAI function schema         │
│                                                                 │
│  子类必须实现一个方法:                                           │
│    execute(**kwargs) → str    ← 实际执行, 返回给 LLM 的结果    │
│                                                                 │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
                     具体 Skill 的 execute()
                     (move / weather / photo / track_face / ...)
                               │
                               ▼
                     驱动层 (mecanum / ptz / camera / oled)
```

### 核心设计原则

1. **Skill 与 LLM 解耦** — SkillManager 只认 `name` 字符串，不管这个 `name` 是 ChatAgent 通过 LLM 拿到的，还是正则匹配拿到的，还是面板 `/api/skill/run` 直接调的
2. **一条 Skill，两种描述** — 每个 Skill 同时有"纯文本描述"（给 system prompt 里的小模型看）和"OpenAI function schema"（走原生 function calling）
3. **执行结果是纯字符串** — Skill.execute() 返回 str，LLM 下一轮会把它当 tool result 看，然后决定最终回复
4. **所有硬件调用必须容错** — Skill 内部对 `driver is None` 和异常都要返回 Mock 或友好的提示字符串，不能让整个 ChatAgent 崩溃

---

## 二、四个核心角色

### 2.1 BaseSkill — Skill 基类

**位置**: [petcar/skills/base_skill.py](file:///e:/work/AITank/petcar/skills/base_skill.py)

所有 Skill 的模板。三个类属性 + 一个抽象方法：

```python
class BaseSkill(ABC):
    # ── 必须填 ──
    name: str = "base"           # ← 唯一标识
    description: str = "..."     # ← LLM 看的工具描述
    parameters: Dict[str, Any]   # ← OpenAI function schema

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """实际执行, 返回给 LLM 的结果字符串"""
        ...

    # ── 自动生成的两种描述 ──
    def get_openai_tool_spec(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def get_tool_prompt(self) -> str:
        """纯文本格式, 塞进 system prompt 给小模型兜底"""
        return f"- {self.name}: {self.description}\n  参数: {self._param_text()}"
```

### 2.2 SkillManager — 注册中心 + 分发器

**位置**: [petcar/core/skill_manager.py](file:///e:/work/AITank/petcar/core/skill_manager.py)

```python
class SkillManager:
    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}

    # ── 注册 / 注销 ──
    def register(self, skill: BaseSkill):
        self._skills[skill.name] = skill       # ← 用 skill.name 做 dict key
        skill.on_register()

    def unregister(self, name: str):
        sk = self._skills.pop(name, None)
        if sk:
            sk.on_unregister()

    # ── 核心分发 ──
    def execute(self, name: str, **kwargs) -> str:
        sk = self._skills.get(name)
        if sk is None:
            return f"抱歉，我不知道怎么 '{name}' 呢"
        try:
            return sk.execute(**kwargs)
        except TypeError as e:
            return f"参数不对哦: {e}"
        except Exception as e:
            return f"执行出错了: {e}"

    # ── 给 LLM 的两种描述 ──
    def list_tool_specs() -> List[dict]:
        return [sk.get_openai_tool_spec() for sk in self._skills.values()]

    def list_tools_prompt() -> str:
        return "\n".join(sk.get_tool_prompt() for sk in self._skills.values())
```

### 2.3 ChatAgent — 循环调度器（整条链路的核心）

**位置**: [petcar/core/chat_agent.py](file:///e:/work/AITank/petcar/core/chat_agent.py)

```python
class ChatAgent:
    def chat(self, user_text: str, max_tool_rounds: int = 3) -> ChatResponse:
        # ① 加进历史
        self._messages.append({"role": "user", "content": user_text})

        # ② 通道 A: 本地规则短路
        local = self._match_local_command(user_text)
        if local is not None:
            name, args, reply = local
            self.skills.execute(name, **args)   # ← 不经过 LLM
            return ChatResponse(reply=reply, ...)

        # ③ 通道 B: LLM 原生 function calling
        for round_i in range(max_tool_rounds):
            messages = self._build_messages()
            tools = self.skills.list_tool_specs()

            result = self.backend.chat(messages, tools)  # ← 调 Ollama/Doubao
            tool_calls = result.get("tool_calls", [])    # ← LLM 决定调什么

            if not tool_calls:
                break

            # 去重 + 执行
            for tc in tool_calls:
                tool_result = self.skills.execute(tc["name"], **tc["arguments"])
                self._messages.append({"role": "tool", "content": tool_result, ...})

            # 循环回去再调一次 LLM, 让它看到 tool 结果
            ...

        # ④ 解析最终回复 + 通知 MoodEngine
        reply, emotion = self._extract_reply_and_emotion(final_content)
        self.mood_engine.trigger(emotion)
        return ChatResponse(reply=reply, emotion=emotion, tools_called=all_tool_calls)
```

### 2.4 LLMBackend — 把 tools 传给模型 + 解析返回的 tool_calls

**位置**: [petcar/core/llm_backends.py](file:///e:/work/AITank/petcar/core/llm_backends.py)

```python
class LLMBackend(ABC):
    def chat(self, messages, tools) -> dict:
        """
        返回:
        {
            "content": "...",                    # LLM 想说的话
            "tool_calls": [                      # ← LLM 决定调哪些工具
                {"name": "weather", "arguments": {"city": "北京"}},
                ...
            ]
        }
        """
```

三个实现：

| Backend | 类 | 解析 tool_calls | 降级 |
|---------|-----|-----------------|------|
| Ollama | `OllamaBackend` | `msg["tool_calls"]` → `json.loads(func["arguments"])` | 连不上 → MockBackend |
| Doubao | `DoubaoBackend` | `choices[0]["message"]["tool_calls"]` | 没配 Key → MockBackend |
| Mock | `MockBackend` | 正则匹配本地 RULES → 假造 tool_calls | 兜底 |

---

## 三、三条调用通道

### 通道 A：本地规则短路（最快，完全绕过 LLM）

**位置**: [chat_agent.py:40-76](file:///e:/work/AITank/petcar/core/chat_agent.py#L40-L76)

```
用户输入 → _LOCAL_RULES 正则匹配 → 命中 → skills.execute() → 返回 ChatResponse
```

**触发条件**：用户输入命中 `ChatAgent._LOCAL_RULES` 里的正则表达式。

**为什么有这个？** qwen2.5:0.5b 这种小模型不一定稳定输出 OpenAI function calling 格式的 `tool_calls` 字段。但固定动作指令（"摇头"、"转圈"）用正则 100% 能命中，且执行时间 < 1ms，比走 LLM（3~10s）快得多。

**注意**：这里的 `_LOCAL_RULES` 和 `MockBackend.RULES` 是**两份几乎相同的正则匹配表**，分别在 ChatAgent 和 MockBackend 里。ChatAgent 的版本只做"本地短路"（不给 LLM 看），MockBackend 的版本会构造假的 tool_calls 返回给 ChatAgent（走完整 function calling 链路）。

### 通道 B：LLM 原生 function calling（主力通道）

**位置**: [chat_agent.py:160-229](file:///e:/work/AITank/petcar/core/chat_agent.py#L160-L229) + [llm_backends.py:60-100](file:///e:/work/AITank/petcar/core/llm_backends.py#L60-L100)

```
未命中本地规则
  → messages = system_prompt + _messages
  → tools = SkillManager.list_tool_specs()   # OpenAI function schema 格式
  → backend.chat(messages, tools)
  → 解析 result["tool_calls"]
  → 去重 (executed_tool_signatures)
  → 逐个 SkillManager.execute(name, **args)
  → tool result 塞回 messages
  → 循环回去再调 LLM (最多 3 轮)
```

关键细节：

```python
# 最多 3 轮 tool_call 循环
for round_i in range(max_tool_rounds):
    result = self.backend.chat(messages, tools)
    tool_calls = result.get("tool_calls", [])
    if not tool_calls:
        break                    # LLM 说"我说完了", 结束

    # 同一个 (name, args) 只执行一次 → 防 LLM 重复调用
    dedup_key = (tc["name"], json.dumps(tc["arguments"], sort_keys=True))
    if dedup_key in executed_tool_signatures:
        continue

    tool_result = self.skills.execute(tc["name"], **tc["arguments"])

    # tool 结果塞回 messages, 让 LLM 下一轮能看到
    self._messages.append({
        "role": "tool",
        "content": tool_result,
        "name": tc["name"],
    })
```

### 通道 C：System Prompt 纯文本格式约定（兜底）

**位置**: [chat_agent.py:95-118](file:///e:/work/AITank/petcar/core/chat_agent.py#L95-L118)

**原理**：除了 OpenAI function calling 格式（走 `tools` 参数），ChatAgent 还把工具列表以**纯文本格式**塞进 system prompt，加上一个 `<tool_call>{{"name": "...", "args": {...}}}</tool_call>` 的约定标签。

```python
def _build_system_prompt(self):
    tools_prompt = self.skills.list_tools_prompt()  # 纯文本列表
    self._system_prompt = f"""...
## 可用工具列表
{tools_prompt}                                    # ← 每个 skill 的 name + description + 参数说明

## 工具调用格式
当你需要调用工具时，在 <tool_call> 标签里写 JSON:
<tool_call>{{"name": "工具名", "args": {{...}}}}</tool_call>
...
```

**为什么有这个？** qwen2.5:0.5b 不一定原生支持 Ollama 的 `tools` 参数。但即使它不支持原生 function calling，看到 prompt 里的 `<tool_call>` 约定，也有机会输出符合约定的标签。ChatAgent 当前版本**不解析 `<tool_call>` 标签**（只看原生 `tool_calls` 字段），所以通道 C 目前是"描述性"的——让 LLM 知道自己能做什么。如果需要真正支持 prompt 驱动的 tool call，在 `backend.chat()` 返回后加一段正则解析 `<tool_call>...</tool_call>` 即可。

---

## 四、完整调用时序

以"用户说：帮我查一下北京的天气"为例：

```
用户: "帮我查一下北京的天气"
 │
 ▼ ChatAgent.chat()
 ├─ 加入历史: messages.append({role: "user", content: "帮我查一下北京的天气"})
 │
 ├─ ① _match_local_command()
 │    └─ 遍历 _LOCAL_RULES 的正则...
 │       ├─ "天气|下雨|气温" → 命中!
 │       │
 │       └─ return ("weather", {}, "好的，我让小强查一下~")
 │
 ├─ ② skills.execute("weather")               ← 通道 A, 完全绕过 LLM
 │    └─ WeatherSkill.execute()
 │         └─ requests.get("https://wttr.in/北京?format=j1")
 │            └─ return "北京现在22°C, 晴, 湿度45%"
 │
 ├─ ③ 加入历史: messages.append({role: "assistant", content: "好的..."})
 │
 ├─ ④ 返回 ChatResponse(reply="好的，我让小强查一下~", emotion="happy", tools_called=["weather"])
 │
 ▼ VoiceIO / Flask 面板
 ├─ emotion.set_emotion("happy")
 └─ tts.speak("好的，我让小强查一下~")
```

---

另一个场景："帮我看看今天谁在家"（本地规则不命中，走通道 B）

```
用户: "帮我看看今天谁在家"
 │
 ▼ ChatAgent.chat()
 ├─ _match_local_command() → None (没命中)
 │
 ├─ ① 组装 messages = [system_prompt] + history
 │    system_prompt 里已包含 list_tools_prompt() 的纯文本工具列表
 │
 ├─ ② tools = SkillManager.list_tool_specs()
 │    → [
 │        {type:"function", function:{name:"weather",    parameters:{...}}},
 │        {type:"function", function:{name:"move",      parameters:{...}}},
 │        {type:"function", function:{name:"detect_face",parameters:{...}}},
 │        {type:"function", function:{name:"photo",      parameters:{...}}},
 │        ...
 │      ]
 │
 ├─ ③ LLMBackend.chat(messages, tools)
 │    → POST /api/chat  (Ollama) 或 POST ark.cn-beijing.volces.com (Doubao)
 │    → 返回 {
 │          content: "好的，我帮你看看~",
 │          tool_calls: [
 │            {name: "detect_face", arguments: {}},    ← LLM 决定调 detect_face
 │            {name: "photo",       arguments: {}},    ← 又调 photo
 │          ]
 │        }
 │
 ├─ ④ 执行 tool_calls
 │    ├─ skills.execute("detect_face") → FaceDetectSkill.execute()
 │    │    └─ camera.detect_faces()
 │    │       └─ return "画面里有 1 张脸"
 │    │
 │    ├─ skills.execute("photo") → PhotoSkill.execute()
 │    │    └─ camera.take_photo()
 │    │       └─ return "照片已保存: 1234567890.jpg"
 │    │
 │    └─ 把两条 tool result 塞回 messages
 │
 ├─ ⑤ 循环回去, 再调一次 backend.chat(messages, tools)
 │    这次 messages 里已经有了 tool 结果
 │    → LLM 看到 tool_calls 都执行完了, 返回:
 │        {
 │          content: "看到有 1 张脸哦！[拍了张照片](1234567890.jpg)",
 │          tool_calls: []    ← 空了, LLM 说完了
 │        }
 │
 ├─ ⑥ 退出循环 (tool_calls 为空)
 │
 ├─ ⑦ _extract_reply_and_emotion(final_content)
 │    → reply = "看到有 1 张脸哦！", emotion = "happy"
 │
 ├─ ⑧ mood_engine.trigger("happy", 0.8)
 │
 └─ 返回 ChatResponse(reply=..., emotion=..., tools_called=["detect_face", "photo"])
```

---

## 五、所有已有 Skill 速查表

### 5.1 完整列表

| Skill name | 类 | 文件 | 一句话 | 被谁调走 |
|------------|-----|------|--------|----------|
| `move` | MoveSkill | [skills/move.py](file:///e:/work/AITank/petcar/skills/move.py) | 控制底盘 (forward/backward/turnLeft/turnRight/stop/...) | 通道 A 规则 + 通道 B |
| `ptz` | PTZSkill | [skills/ptz.py](file:///e:/work/AITank/petcar/skills/ptz.py) | 云台转动 (up/down/left/right/center) | 通道 B |
| `photo` | PhotoSkill | [skills/photo.py](file:///e:/work/AITank/petcar/skills/photo.py) | 拍照并保存到本地 | 通道 A 规则 + 通道 B |
| `detect_face` | FaceDetectSkill | [skills/face_detect.py](file:///e:/work/AITank/petcar/skills/face_detect.py) | 检测画面里的人脸数量 | 通道 B |
| `track_face` | FaceTrackSkill | [skills/face_track.py](file:///e:/work/AITank/petcar/skills/face_track.py) | 让云台自动追踪最大人脸 (30秒) | 通道 A 规则 + 通道 B |
| `weather` | WeatherSkill | [skills/weather.py](file:///e:/work/AITank/petcar/skills/weather.py) | wttr.in 查城市天气, 无需 Key | 通道 A 规则 + 通道 B |
| `set_alarm` | AlarmSkill | [skills/alarm.py](file:///e:/work/AITank/petcar/skills/alarm.py) | 倒计时 / 闹钟 (HH:MM) | 通道 B |
| `show_emotion` | EmoteSkill | [skills/emote.py](file:///e:/work/AITank/petcar/skills/emote.py) | 设置 OLED 表情 | 通道 A 规则 + 通道 B |
| `express` | ExpressSkill | [skills/express.py](file:///e:/work/AITank/petcar/skills/express.py) | 宠物动作 (nod/shake/tilt/wag/spin/...) | 通道 A 规则 + 通道 B |

### 5.2 每个 Skill 的关键代码结构

```python
# ─── 模板 ───

class XxxSkill(BaseSkill):
    name = "xxx"                          # ← LLM 调这个 name
    description = "一句话描述, LLM 看的"
    parameters = {                        # ← OpenAI function schema
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "..."},
            "param2": {"type": "number", "enum": [...], ...},
        },
        "required": ["param1"],           # ← LLM 必须提供的参数
    }

    def __init__(self, driver=None):
        self.driver = driver              # ← 注入的硬件驱动

    def execute(self, param1: str, param2: float = 2.0) -> str:
        """执行, 返回给 LLM 的纯字符串结果"""
        if self.driver is None:
            return f"(Mock) 好的, 我{param1}..."     # ← Mock 模式也能跑
        try:
            self.driver.do_something(param1)
            return f"好的, 已{param1}!"               # ← 成功路径
        except Exception as e:
            return f"执行失败了 {e}"                    # ← 错误路径
```

### 5.3 按依赖分组

```
依赖底盘:  move, express (ExpressionPlayer 内部)
依赖云台:  ptz, express, track_face
依赖摄像头: photo, detect_face, track_face
依赖 OLED: show_emotion
依赖网络:  weather
无依赖:    set_alarm (只用 threading.Timer)
```

### 5.4 main.py 里的注册顺序

[main.py:93-102](file:///e:/work/AITank/petcar/main.py#L93-L102)

```python
sm = SkillManager()
sm.register(MoveSkill(mecanum))
sm.register(PTZSkill(ptz))
sm.register(PhotoSkill(camera))
sm.register(FaceDetectSkill(camera))
sm.register(FaceTrackSkill(camera, ptz))
sm.register(WeatherSkill())
sm.register(AlarmSkill())
sm.register(EmoteSkill(emotion))
sm.register(ExpressSkill(action_player))
```

注册**没有先后依赖**——SkillManager 只是往 `_skills` 字典里塞，不做初始化检查。但**每个 Skill 的 execute() 内部要自己检查依赖是否为 None**（走 Mock 降级）。

---

## 六、新增 Skill 实战指南

### Step 1：写一个新 Skill 文件

在 `petcar/skills/` 下新建文件，比如 `greet.py`：

```python
# petcar/skills/greet.py

from __future__ import annotations
from petcar.skills.base_skill import BaseSkill


class GreetSkill(BaseSkill):
    name = "greet"
    description = "对指定的人打招呼, 显示开心表情"
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "打招呼的对象, 默认 '大家'",
            },
        },
        "required": [],
    }

    def __init__(self, emotion_engine=None, tts_driver=None):
        self.emotion = emotion_engine
        self.tts = tts_driver

    def execute(self, target: str = "大家") -> str:
        if self.emotion is not None:
            try:
                self.emotion.set_emotion("happy")
            except Exception:
                pass
        if self.tts is not None:
            try:
                self.tts.speak_async(f"你好呀{target}~")
            except Exception:
                pass
        return f"已经跟{target}打招呼啦"
```

### Step 2：在 main.py 里注册

[main.py:93-102](file:///e:/work/AITank/petcar/main.py#L93-L102) 附近加一行：

```python
from petcar.skills.greet import GreetSkill
sm.register(GreetSkill(emotion, tts))
```

### Step 3：验证

**自动生效的地方**（不需要改任何其他代码）：

| 位置 | 怎么验证 |
|------|----------|
| System prompt 工具列表 | 看 LLM 回复里 `<reply>` 前有没有在描述可用工具时提到 `greet` |
| OpenAI function spec | 调 `curl http://<IP>:5000/api/skills` 看返回里有没有 `greet` |
| SkillManager 执行 | 调 `curl -X POST http://<IP>:5000/api/skill/run -H "Content-Type: application/json" -d '{"name":"greet","params":{"target":"小明"}}'` |
| LLM 实际调用 | 说"跟小明打个招呼"，看 LLM 会不会主动调 `greet({"target": "小明"})` |

### Step 4（可选）：加本地规则短路

如果这个动作经常被直接指令触发，可以在 [chat_agent.py:40-56](file:///e:/work/AITank/petcar/core/chat_agent.py#L40-L56) 的 `_LOCAL_RULES` 列表里加一条：

```python
_LOCAL_RULES = [
    ...
    (r"跟(.+?)打招呼|对(.+?)说你好", "greet",
     lambda m: {"target": m.group(1) or m.group(2)},
     "好的，让我跟你打招呼~"),
]
```

正则里可以用捕获组把用户说的对象提取出来当参数。

---

### 一个完整 Skill 的文件清单参考

| 文件 | 说明 |
|------|------|
| `skills/greet.py` | Skill 实现 |
| `main.py` | 注册入口 |
| ~~`skill_manager.py`~~ | **不需要改** — 动态 `_skills[name] = skill` |
| ~~`chat_agent.py`~~ | **不需要改** — 自动出现在 system prompt + function spec 里 |
| ~~`llm_backends.py`~~ | **不需要改** — 通用解析逻辑 |
| ~~`flask_app.py`~~ | **不需要改** — `/api/skills` 和 `/api/skill/run` 是动态的 |

---

## 七、本地规则短路表 (_LOCAL_RULES)

[chat_agent.py:40-56](file:///e:/work/AITank/petcar/core/chat_agent.py#L40-L56)

| 正则 | 调哪个 Skill | 参数 | 本地回复 |
|------|-------------|------|----------|
| `摇(一)?摇?(摇)?头\|摇一摇` | express | `{action: "shake"}` | 好的，我摇摇头~ |
| `点(一)?点?头` | express | `{action: "nod"}` | 好的，我点点头~ |
| `歪(一)?歪?头` | express | `{action: "tilt"}` | 好的，我歪歪头~ |
| `跳舞\|跳个舞` | express | `{action: "dance"}` | 好呀，我跳个舞~ |
| `抬(一)?抬头\|向上看\|往上看` | look (本地, 不是 ptz Skill) | `{direction: "up", delta: 15}` | 好的，我抬头看~ |
| `低(一)?低头\|向下看\|往下看` | look (本地) | `{direction: "down", delta: 15}` | 好的，我低头看~ |
| `向左看\|往左看\|看左边` | look (本地) | `{direction: "left", delta: 15}` | 好的，我往左看~ |
| `向右看\|往右看\|看右边` | look (本地) | `{direction: "right", delta: 15}` | 好的，我往右看~ |
| `左转\|向左转` | move | `{direction: "turnLeft", duration: 2}` | 好的，我左转~ |
| `右转\|向右转` | move | `{direction: "turnRight", duration: 2}` | 好的，我右转~ |
| `转(一)?个?圈\|旋转\|转一下` | move | `{direction: "spin", duration: 3}` | 好的，我转个圈~ |
| `往前走\|前进\|向前走\|往前走` | move | `{direction: "forward", duration: 2}` | 好的，我往前走~ |
| `后退\|往后走\|往后退` | move | `{direction: "backward", duration: 2}` | 好的，我后退一点~ |
| `停下\|停止\|别动` | move | `{direction: "stop"}` | 好的，我停下啦 |
| `拍(一)?张?照\|拍照\|相片` | photo | `{}` | 咔嚓，拍好啦~ |

**注意**：表中 "look" 不是一个独立 Skill 名，而是 ChatAgent 内部调的 `ptz_driver` 方法。这部分走的是 `self.skills.execute("ptz", direction=..., delta=...)`。严格来说应该叫 PTZSkill 或 ptz，只是表里写的是逻辑上的"向左看"。

**执行位置**：`_match_local_command()` 返回的 `(name, args, reply)` 三元组里的 `name` 会直接传给 `SkillManager.execute(name, **args)`。所以 `name` 必须是某个已注册 Skill 的 `name` 字段值。

---

## 八、FAQ

### Q1: 我加了一个新 Skill，怎么知道它有没有被 LLM 看到？

看两个地方：
1. 面板 `/api/skills` 返回的 JSON 里有没有你的 skill（这个是 SkillManager 直接 enumerate 的，只要注册了就一定有）
2. 让 LLM 说一句"你能做什么"，看它会不会提到你的 skill

### Q2: LLM 不调我新写的 skill？

排查顺序：
1. **注册了吗**？`main.py` 里有没有 `sm.register()`
2. **Skill.name 对吗**？`name = "weather"` 里的字符串和你以为的一致吗？
3. **description 写清楚了吗**？LLM 靠 description 判断什么时候用这个工具。"查询城市天气" 就比 "天气" 好
4. **parameters.required 对吗**？required 里列的参数，LLM 会尝试都填上；留空 `{}` 表示没有必填参数
5. **Ollama 重启了吗**？Ollama 是有状态的，新工具加载可能需要 Ollama 进程重启

### Q3: Skill 返回 Mock 字符串会不会有问题？

不会。`return "(Mock) 好的, 我xxx..."` 这样的字符串：
- 通道 A（本地规则短路）：直接作为 reply 返回给用户，用户能看到 "(Mock)" 前缀，知道没连硬件
- 通道 B（function calling）：tool result 会被 LLM 当普通文本看，LLM 会把它组织进最终回复

### Q4: 同一个 skill 能被同时执行多次吗？

**当前代码里没有互斥锁**。如果两个用户同时说"帮我查天气"，WeatherSkill.execute() 会并行执行两次。WeatherSkill 是无状态的（每次都是新建 HTTP 请求），没问题。

但 MoveSkill、ExpressSkill 这类会操作底盘的，如果被并行调用就会抢硬件。ExpressSkill 内部有 `threading.Lock()` + `_halt(wait=True)` 等待上一个动作停稳再播下一个，所以相对安全。MoveSkill 是 `threading.Timer` 延迟停止，两次并行调用可能冲突。

**如果你的 Skill 操作硬件，建议**：
```python
class XxxSkill(BaseSkill):
    def __init__(self, driver):
        self.driver = driver
        self._lock = threading.Lock()   # ← 加锁

    def execute(self, ...) -> str:
        with self._lock:
            # 硬件操作
            ...
```

### Q5: ChatAgent 里的 _LOCAL_RULES 和 MockBackend.RULES 为什么有两份？

这是一个已知设计缺陷（见 [迭代路线图 P2-10](file:///e:/work/AITank/docs/AI-PetCar迭代路线图与优化方案.md)）。当前：
- ChatAgent._LOCAL_RULES 是"不经过 LLM 的快速短路"——命中就直接 `skills.execute()` 返回
- MockBackend.RULES 是"LLM 后端返回假 tool_calls"——走完整 function calling 链路

两者有重叠但不完全相同（MockBackend 多了一条"追踪我"、MockBackend 还包含表情规则的 tool_call）。

**建议未来**：抽一份公共 `SKILL_RULES` 定义，两处共用。改一处即可。

### Q6: 一个 skill 的 execute() 能再调另一个 skill 吗？

技术上可以（构造一个 SkillManager 引用），但**不推荐**。原因：
- `ChatAgent.chat()` 里有 tool_call 去重逻辑（防 LLM 重复调用），如果 skill 内部再调用会绕过这个保护
- Skill 返回值是 str 类型，传递复杂结果不方便
- 调试困难

推荐做法：让 LLM 决定调用顺序。用户说"查完天气告诉我"，LLM 会先调 `weather`，拿到结果后在最终回复里告诉用户。这是更自然的多步调用方式。

### Q7: 通道 C 的 prompt 纯文本格式约定什么时候会真正生效？

当前 Ollama 后端只解析原生 `tool_calls` 字段。如果换一个**不支持原生 function calling** 的模型（比如纯文本生成模型），通道 C 就有用了——ChatAgent 需要加一段正则解析 `<tool_call>...</tool_call>` 标签。

但目前 Ollama 和 Doubao 都原生支持，所以通道 C 主要起"让 LLM 知道自己能做什么"的描述性作用。

### Q8: Skill 的 execute() 里抛异常会怎么样？

SkillManager.execute() 里有 try/except：

```python
def execute(self, name, **kwargs) -> str:
    sk = self._skills.get(name)
    if sk is None:
        return f"抱歉，我不知道怎么 '{name}' 呢"
    try:
        return sk.execute(**kwargs)
    except TypeError as e:
        return f"参数不对哦: {e}"
    except Exception as e:
        return f"执行出错了: {e}"
```

异常会被捕获，转成友好的字符串返回。ChatAgent 拿到这个字符串继续走链路——不会崩溃，LLM 可能会在最终回复里体现出来。

**但更好的做法**：让 Skill 内部自己容错，返回更贴合用户预期的友好提示：

```python
def execute(self, city: str = "北京") -> str:
    try:
        resp = requests.get(...)
        return f"{city}现在22°C, 晴, 湿度45%"
    except Exception as e:
        return f"查天气失败了 {e}，要不稍后再试？"
```

---

> **关联文档**:
> - [AI-PetCar迭代路线图与优化方案.md](file:///e:/work/AITank/docs/AI-PetCar迭代路线图与优化方案.md) — 整体架构优化建议
> - [详细设计文档.md](file:///e:/work/AITank/petcar/docs/详细设计文档.md) — 各模块接口规格
> - [积木编程引擎设计文档.md](file:///e:/work/AITank/petcar/docs/积木编程引擎设计文档.md) — Blockly 积木层设计
> - [自然语言生成积木设计文档.md](file:///e:/work/AITank/petcar/docs/自然语言生成积木设计文档.md) — LLM → Blockly

