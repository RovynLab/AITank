# AI-PetCar 迭代路线图与优化方案

> **评审范围**：`petcar/` 下全部源码（驱动层、核心层、技能层、积木层、API 层）
>
> **评审日期**：2026-11-09
>
> **总体评价**：PetCar 已经过了"从零搭建"阶段，核心功能闭环完成（情感引擎 + 语音交互 + LLM 对话 + 积木编程）。进入"打磨体验 + 发挥差异化"阶段。当前最大风险点是**硬件资源并发仲裁缺失**和**积木层能力上限受限**。

---

## 目录

- [一、项目现状总览](#一项目现状总览)
- [二、架构健康度评估](#二架构健康度评估)
- [三、P0 — 生产阻塞问题（必须立即修复）](#三p0--生产阻塞问题必须立即修复)
- [四、P1 — 架构优化](#四p1--架构优化)
- [五、P2 — 代码质量](#五p2--代码质量)
- [六、值得实现的新功能](#六值得实现的新功能)
- [七、推荐迭代路线图（4 周）](#七推荐迭代路线图4-周)
- [八、附录：完整问题清单](#八附录完整问题清单)

---

## 一、项目现状总览

### 1.1 五层架构

```
petcar/
├── drivers/            ← 驱动层（oled / mecanum / ptz / camera / tts / asr / detectors）
├── core/               ← 核心层（emotion_engine / mood_engine / chat_agent / voice_io / pid_tracker / skill_manager）
├── skills/             ← 技能层（move / ptz / photo / face_detect / face_track / weather / alarm / emote / express）
├── blocks/             ← 积木层（compiler / runtime / service / perception / catalog）
└── api/                ← API 层（Flask 中控面板 + Blockly 积木编程）
```

### 1.2 核心亮点

| 能力 | 实现位置 | 成熟度 |
|------|----------|--------|
| 🎨 OLED 帧动画表情 | `core/emotion_engine.py` | ✅ 12 种预设表情 + 眨眼/说话/思考/跳动动画，渲染去重防 I2C 阻塞 |
| 🧠 情感状态机 | `core/mood_engine.py` | ✅ valence-arousal 二维模型 + 自然衰减 + 空闲行为 |
| 🛡️ LLM 三层降级链 | `core/llm_backends.py` | ✅ Ollama → Doubao → Mock 规则引擎，断网断电都能跑 |
| 🧩 Blockly 积木编程 | `blocks/` | ✅ 最小可用：运动 + 云台 + 表情 + 说话 + 拍照 + 视觉检测 + 控制流 |
| 🎯 PID 视觉伺服 | `core/pid_tracker.py` | ✅ 支持 face / color / tennis 三种目标，绝对角度伺服无振荡 |
| 📹 MJPEG 视频流 + 检测器注册 | `api/flask_app.py` | ✅ 9 种可切换检测器 + TFLite SSD 通用物体检测（COCO 80 类） |
| 🎹 中控面板 | `api/static/dashboard.html` | ✅ 状态聚合 + 配置热更新 + 单轮 ASR / 对话测试工具 |

### 1.3 已注册的检测器

| 检测器 | 来源 | 模型依赖 | 说明 |
|--------|------|----------|------|
| face | OpenCV YuNet / Haar | face_detection_yunet_2023mar.onnx | 优先 YuNet，退回 Haar |
| tennis | 传统视觉 | 无模型 | HSV 分割 + 圆形度门限 |
| color | 传统视觉 | 无模型 | HSV 可调阈值 |
| person / pet / cup / ball / tv | TFLite SSD | detect.tflite (COCO 80 类) | 每 2 帧一次推理，其他帧复用缓存 |
| motion | 帧差 | 无模型 | 跨帧灰度差 |
| gesture | MediaPipe | gesture.py | 静态手势识别 |

---

## 二、架构健康度评估

### 2.1 代码规模

| 模块 | 文件数 | 预估行数 | 复杂度 |
|------|--------|----------|--------|
| drivers/ | 8 | ~1200 | ⭐⭐ |
| core/ | 8 | ~2500 | ⭐⭐⭐⭐ |
| skills/ | 10 | ~1500 | ⭐⭐ |
| blocks/ | 6 | ~1000 | ⭐⭐⭐ |
| api/ | 2 (.py) + 前端 | ~1500 + JS | ⭐⭐⭐⭐⭐ |
| **总计** | **34** | **~7700** | |

### 2.2 健康度评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 功能完整性 | ⭐⭐⭐⭐⭐ | 核心闭环全部完成 |
| 硬件安全 | ⭐⭐⭐ | 运动租约看门狗有了，但跨线程仲裁缺失 |
| 错误处理 | ⭐⭐ | 大量 `except Exception: pass` 静默吞异常 |
| 日志系统 | ⭐⭐ | print 散落各处，EventLog 只在 flask_app 里 |
| 并发安全 | ⭐⭐ | 部分模块有 lock，但缺乏统一资源仲裁 |
| 可测试性 | ⭐⭐ | 没有测试目录，部分接口耦合硬件 |
| 前端体验 | ⭐⭐⭐⭐ | Blockly 编辑器完整，dashboard 聚合到位 |

### 2.3 关键设计决策回顾（哪些做对了）

1. **MockBackend 规则引擎** — Ollama 不可用时自动降级到正则匹配，教学演示不会因为模型加载失败而无法上课
2. **EmotionEngine 渲染去重** — 发现 OLED 的 I2C 写入会阻塞电机总线，做了画面 key 去重，实测消除了"4 个轮子间隔 1s 依次启动"的问题
3. **运动租约看门狗** — 0.6s 超时自动停车，积木循环里意外卡死也不会让底盘一直转
4. **PID 追踪用绝对角度伺服** — 不累积增量直接算目标角度，无延迟超调振荡
5. **PerceptionCache 低频采样** — 3~4Hz 后台采样，解释器读快照不阻塞

---

## 三、P0 — 生产阻塞问题（必须立即修复）

### Bug #1：硬件资源缺少统一仲裁机制

**严重性**：🔴 P0 — 可能导致底盘/云台同时收到矛盾指令

**位置**：

| 模块 | 路径 |
|------|------|
| 积木运行时 | [blocks/runtime.py](file:///e:/work/AITank/petcar/blocks/runtime.py) |
| PID 追踪器 | [core/pid_tracker.py](file:///e:/work/AITank/petcar/core/pid_tracker.py#L44) |
| ChatAgent 技能 | [core/chat_agent.py](file:///e:/work/AITank/petcar/core/chat_agent.py#L40) (_LOCAL_RULES) |
| flask_app | [api/flask_app.py](file:///e:/work/AITank/petcar/api/flask_app.py#L381) (/api/base/move, /api/ptz) |

**问题描述**：

当前有 **三条独立的指令路径** 都能直接操作同一个 PTZ 和 Mecanum：

```
路径 A: BlockService → ProgramRunner → BlockRuntime → mecanum/ptz    (积木页)
路径 B: PIDTracker → ptz.h_rotate/v_rotate                           (追踪器后台线程)
路径 C: ChatAgent._LOCAL_RULES → skill_manager → express/move/ptz     (语音指令)
路径 D: flask_app 路由 → mecanum/ptz                                  (面板手动操作)
```

flask_app 里有 `_blocks_busy()` 检查，积木运行时屏蔽了面板手动操作。但：
- **PID 追踪器是后台线程**，不受 `_blocks_busy()` 约束
- **ChatAgent 的技能调用** 也不受约束（`_LOCAL_RULES` 里直接调 `self.skills.execute()`）
- **BlockRuntime._lock** 只保护运动状态字段，不保护 PTZ 舵机的并发写入

**后果**：
- 积木在"左转 2 秒"的同时，用户说"向右看"，ChatAgent 直接调 `ptz.look_right()`，云台和底盘打架
- PID 追踪器正在追踪一个人脸，积木同时发了一个 `look up 10`，PID 的控制值被覆盖，追踪抖动

**修复方案**：引入一个轻量的 `HardwareGuard` 仲裁器：

```python
# petcar/core/hardware_guard.py

class HardwareGuard:
    """硬件资源仲裁器。谁持有 token 谁能操作，积木运行期间自动屏蔽其他通道。"""

    GUARD_PTZ = "ptz"
    GUARD_MECANUM = "mecanum"

    def __init__(self):
        self._lock = threading.Lock()
        self._holders = {self.GUARD_PTZ: None, self.GUARD_MECANUM: None}

    def try_acquire(self, resource: str, owner: str, force: bool = False) -> bool:
        """尝试获取资源。force=True 可抢占。"""
        with self._lock:
            current = self._holders.get(resource)
            if current is None or current == owner or force:
                self._holders[resource] = owner
                return True
            return False

    def release(self, resource: str, owner: str):
        with self._lock:
            if self._holders.get(resource) == owner:
                self._holders[resource] = None

    def holder(self, resource: str) -> str | None:
        with self._lock:
            return self._holders.get(resource)
```

然后让 BlockRuntime、PIDTracker、Skill 的硬件调用全部走同一个 guard。积木 `run()` 时先 try 抢占所有资源，PID 和 ChatAgent 发指令前检查 guard 当前 owner 是否是积木。

**工作量**：~150 行新增 + 10 处改动点。

---

### Bug #2：ChatAgent 对话历史 tool 消息清理逻辑错误

**严重性**：🔴 P0 — 导致历史消息格式混乱，可能让下一轮 LLM 调用出错

**位置**：[core/chat_agent.py](file:///e:/work/AITank/petcar/core/chat_agent.py#L255-L261) `_trim_history()`

**当前代码**：

```python
def _trim_history(self):
    while len(self._messages) > self._max_history:
        self._messages.pop(0)
        # 如果最早的是 tool, 再多删一条 assistant
        while self._messages and self._messages[0].get("role") == "tool":
            self._messages.pop(0)
```

**问题分析**：

每次 tool_call 会插入：
```
assistant (带 tool_calls 字段) → tool (结果) → ...
```

一次可能有 **多条 tool 消息**（当前循环没限制），且每条 tool 前面**必须有对应的 assistant**。当前代码只多删一条 assistant，但可能留下孤立的 tool 消息。

当 tool 消息成为最早一条时，LLM 解析历史上下文会报：`Role 'tool' must be preceded by an assistant message`。

**修复方案**：从最早消息开始，成对删除直到不超上限：

```python
def _trim_history(self):
    while len(self._messages) > self._max_history:
        # 从最早一条开始删, 确保 role 序列合法
        self._messages.pop(0)
        # 如果删的是 assistant(tool_call), 必须同时删掉后面所有紧跟着的 tool 消息
        # 如果删的是 tool, 说明 tool 已经孤立了, 继续删直到遇到 assistant
        while self._messages and self._messages[0].get("role") == "tool":
            self._messages.pop(0)
```

**工作量**：5 行。

---

### Bug #3：语音交互主循环无法被 Ctrl+C 及时中断

**严重性**：🔴 P0 — `voice_io.start()` 后无法通过 Ctrl+C 优雅退出

**位置**：[core/voice_io.py](file:///e:/work/AITank/petcar/core/voice_io.py#L61-L131) `_loop()`

**问题描述**：

```python
def _loop(self):
    while self._running:
        text = self.asr.listen(timeout=15.0)   # ← 这里阻塞 15 秒
```

`asr.listen()` 内部在等 VAD 起录/静音，是同步阻塞调用。`KeyboardInterrupt` 能打断 Python 层循环，但 ASR 底层的录音线程可能还在跑。flask_app 的 [asr_once](file:///e:/work/AITank/petcar/api/flask_app.py#L773) 和 [voice_test](file:///e:/work/AITank/petcar/api/flask_app.py#L813) 里已经正确调用了 `asr.abort_listen()`，但 VoiceIO 主循环里没有。

**修复方案**：

```python
def _loop(self):
    while self._running:
        try:
            text = self.asr.listen(timeout=15.0)
        except KeyboardInterrupt:
            self.asr.abort_listen()
            self._running = False
            break
```

同时在 `VoiceIO.stop()` 里也调一下 `asr.abort_listen()`。

**工作量**：3 行。

---

### Bug #4：积木 PerceptionCache 3~4Hz 采样与 `if_sees` 不同步

**严重性**：🟠 P1（暂列 P0 是因为直接影响积木教学演示效果）

**位置**：

| 模块 | 路径 |
|------|------|
| 感知缓存 | [blocks/perception.py](file:///e:/work/AITank/petcar/blocks/perception.py) |
| 解释器 | [blocks/service.py](file:///e:/work/AITank/petcar/blocks/service.py#L312-L323) `if_sees` 处理 |

**问题描述**：

`if_sees` 积木的实现是：

```python
if op == "if_sees":
    if self.runtime.sees(target):    # ← 读快照, 可能是 0.3s 前的
        self._exec_list(node.get("body") or [])
```

积木循环里如果有一段代码每秒执行 10 次 `if_sees`，那 9 次读到的都是**同一份旧快照**。学生在积木页看到"检测到人脸"的 chip 亮了又灭，但积木代码里的条件判断"看起来不响应"。

**修复方案**：给 `if_sees` 加"连续 N 次确认才触发"的语义，前端和后端都升级：

```python
# catalog.py: 给 if_sees 积木加 confirm 次数参数
{
    "type": "if_sees",
    "blockly": {
        "message0": "如果连续 %1 次看到 %2 那么 %3",
        "args0": [
            _num("CONFIRM", 2, 1, 5),
            _dd("TARGET", TARGETS),
            {"type": "input_statement", "name": "DO"},
        ],
        ...
    },
}
```

然后解释器里做 **EMA 计数**（连续看到 +1，没看到归零）：

```python
# service.py 的 _exec() 里, if_sees 分支
if op == "if_sees":
    confirm = int(node.get("confirm", 2))
    key = (node.get("id"), target)
    self._see_counts[key] = (self._see_counts.get(key, 0) + 1
                             if self.runtime.sees(target) else 0)
    if self._see_counts[key] >= confirm:
        self._exec_list(node.get("body") or [])
```

同时还可以加一个 `wait_sees(target, timeout)` 阻塞等待版本，在循环里轮询直到看到目标再继续。

**工作量**：~50 行（含前端 catalog 和后端解释器改动）。

---

### Bug #5：大量硬件调用被静默吞掉异常

**严重性**：🟠 P1（影响可调试性）

**位置**：多处。

典型例子 — [BlockRuntime.move_start](file:///e:/work/AITank/petcar/blocks/runtime.py#L55-L63)：

```python
if self.mecanum is not None:
    try:
        self.mecanum.set_speed(self._speed)
    except Exception:
        pass          # ❌ 电机 I2C 失败, 用户只会看到"机器人没动"
    fn = getattr(self.mecanum, direction, None)
    if fn:
        fn()          # ❌ fn() 本身也可能抛异常
```

同文件 `look()`、`set_emotion()`、`say()` 里都有类似的 `except Exception: pass`。

**修复方案**：至少记录日志并让 watchdog 感知到失败：

```python
try:
    self.mecanum.set_speed(self._speed)
except Exception as e:
    self._log("error", f"底盘设置速度失败: {e}")
    self.stop_if_owner(owner)    # 失败立即释放租约, watchdog 不会超时等待
```

把 `self._log` 接入统一的 logging 体系（见 P1 第 7 条）。

**工作量**：每处 2 行修改，~20 处。

---

## 四、P1 — 架构优化

### 优化 #6：flask_app.py 拆成路由蓝图

**文件**：[api/flask_app.py](file:///e:/work/AITank/petcar/api/flask_app.py)（800+ 行）

**当前结构**：所有路由塞在一个 `create_app()` 函数里，带一个 200+ 行的检测器注册闭包。

**目标结构**：

```
petcar/api/
├── __init__.py
├── flask_app.py              # 组装蓝图的胶水代码, < 50 行
├── block_api.py              # 积木路由 (已经独立了, 注册方式待统一)
├── detectors.py              # 检测器注册表 & annotators dict
├── routes/
│   ├── __init__.py
│   ├── emotion.py            # /api/emotion /api/emotions
│   ├── control.py            # /api/base/* /api/ptz /api/estop /api/action*
│   ├── vision.py             # /api/video_feed /api/detect /api/faces /api/photo*
│   │                         #   /api/track /api/color_cfg /api/camera/*
│   ├── chat.py               # /api/chat /api/skills /api/skill/run
│   ├── voice.py              # /api/tts /api/asr/* /api/voice_test*
│   └── config.py             # /api/config* /api/status /api/logs
├── static/                   # 静态资源 (不变)
└── dashboard.html            # 中控面板
```

**flask_app.py 改造后**：

```python
def create_app(...):
    from petcar.api.routes import emotion, control, vision, chat, voice, config as cfg_route
    from petcar.api.detectors import register_detectors

    app = Flask(__name__, static_folder=...)

    # 检测器注册一次, 各路由共享
    annotators, pid_tracker = register_detectors(camera, ptz, log=EventLog())

    # 各蓝图只负责路由, 共享 app 上下文中的依赖
    register_routes(app, {
        "chat": chat, "emotion": emotion, "mecanum": mecanum,
        "ptz": ptz, "camera": camera, "mood_engine": mood_engine,
        "tts": tts, "asr": asr, "skill_manager": skill_manager,
        "block_service": block_service, "action_player": action_player,
        "annotators": annotators, "pid_tracker": pid_tracker,
    })

    return app
```

**好处**：
- 每个路由文件 80~150 行，可读性好
- 检测器注册、颜色配置、PID tracker 初始化逻辑独立成模块
- 单元测试时可以只测单个蓝图

**工作量**：重构而非重写，~1 天。

---

### 优化 #7：技能层与积木层统一执行入口

**问题回顾**：当前技能和积木是两条独立的硬件控制路径，互相看不见。

```
技能路径: ChatAgent → SkillManager → skills/*.py → mecanum/ptz
积木路径: BlockService → ProgramRunner → BlockRuntime → mecanum/ptz
```

**目标**：让两条路径都经过同一个 **硬件网关**，技能和积木只是"上层意图"，网关决定控制权。

```
技能/积木 → 硬件网关 (HardwareGuard) → 仲裁 → mecanum/ptz
```

具体做法：

1. 引入 `petcar/core/hardware_gateway.py`，封装 MecanumDriver / PTZDriver / TTSDriver / CameraDriver
2. 网关继承 HardwareGuard 的 try_acquire/release 语义
3. BlockRuntime 和 Skill 的硬件调用都走网关
4. 网关暴露 `force_break_hold(owner)` 让积木 `estop` 能抢占 PID 的资源

**工作量**：~300 行新增 + 10 处改动。

---

### 优化 #8：引入标准 logging 统一日志

**现状**：`print("[模块] 消息")` 散落 200+ 处。EventLog 只在 flask_app 里。

**目标**：

```python
# petcar/__init__.py 或 core/logging_setup.py
import logging

logger = logging.getLogger("petcar")
logger.setLevel(logging.INFO)

# 控制台 handler
console = logging.StreamHandler()
console.setFormatter(logging.Formatter(
    "%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S"
))
logger.addHandler(console)

# EventLog handler → 把日志同时写入环形缓冲区, 供面板轮询
class EventLogHandler(logging.Handler):
    def emit(self, record):
        log.add(record.levelname.lower(), record.getMessage())

logger.addHandler(EventLogHandler())
```

然后把所有 `print(f"[xxx] yyy")` 改成 `logger.info("yyy")` / `logger.error("yyy")`。

**工作量**：新增 30 行 + 全局搜索替换 200 处，30 分钟搞定。

---

### 优化 #9：感知层检测器注册共享

**问题**：`PerceptionCache` 和 `flask_app.annotators` 各自初始化了一套检测器：

| 检测器 | PerceptionCache | flask_app.annotators |
|--------|----------------|---------------------|
| YuNet/Haar 人脸 | `cam.detect_faces()` | 同一个 cam，不同调用 |
| TFLite SSD | ❌ 没有 | ✅ `get_detector()` |
| 网球 | `detect_tennis_ball()` | 同一个函数 |
| 颜色 | `detect_color()` with hardcoded cfg | 同一个函数，但 cfg 是面板可改的 |

**修复**：在驱动层搞一个统一的 detector registry：

```python
# petcar/drivers/__init__.py

class DetectorRegistry:
    def __init__(self):
        self._instances = {}
        self._color_cfg = {"h_min": 25, ...}

    @property
    def color_cfg(self):
        return self._color_cfg

    def get_detector(self, name):
        if name not in self._instances:
            if name == "tflite":
                from .detectors import get_detector
                self._instances[name] = get_detector()
        return self._instances.get(name)

registry = DetectorRegistry()
```

PerceptionCache 和 flask_app.annotators 都从 registry 拿实例和 color_cfg，省模型加载时间 + 统一配置源。

**工作量**：~80 行。

---

## 五、P2 — 代码质量

### 优化 #10：MockBackend 与 ChatAgent._LOCAL_RULES 规则重复

两处正则匹配逻辑几乎相同，但维护两份容易漂移：

| 位置 | 文件 |
|------|------|
| ChatAgent 本地指令 | [core/chat_agent.py](file:///e:/work/AITank/petcar/core/chat_agent.py#L40-L56) `_LOCAL_RULES` |
| MockBackend 规则引擎 | [core/llm_backends.py](file:///e:/work/AITank/petcar/core/llm_backends.py#L165-L213) `RULES` |

**建议**：抽一份 `SKILL_RULES` 公共定义，ChatAgent 和 MockBackend 都引用它：

```python
# petcar/core/skill_rules.py

# 每条: (regex_pattern, skill_name, args_builder, reply)
SKILL_RULES = [
    (r"摇(一)?摇(摇)?头|摇一摇", "express", lambda: {"action": "shake"}, "好的，我摇摇头~"),
    (r"点(一)?点?头",            "express", lambda: {"action": "nod"},   "好的，我点点头~"),
    ...
]
```

ChatAgent._match_local_command 和 MockBackend.chat 都遍历同一份。

**工作量**：~30 行定义 + 改两处消费逻辑。

---

### 优化 #11：配置项散落

config.py 有 60+ 常量：

```
硬件地址:       PCA9685_ADDR, MOTOR_FL/FR/TL/TR, SERVO_H/V...
速度:          MOTOR_NORMAL_SPEED, MOTOR_MAX_SPEED
LLM 参数:      LLM_BACKEND, OLLAMA_HOST, OLLAMA_MODEL, DOUBAO_*, LLM_*
Pet 人格:      PET_NAME, PET_PERSONALITY, STARTUP_GREETING
ASR 参数:      ASR_MODE, WHISPER_MODEL, WAKE_WORD, ASR_DEVICE, VAD_*
TTS 参数:      TTS_MODE, TTS_DEVICE, TTS_VOICE, TTS_PITCH, PIPER_*
情感参数:      MOOD_DECAY_*, IDLE_SLEEPY_SEC, BLINK_INTERVAL
Flask:         FLASK_HOST, FLASK_PORT
路径:          BASE_DIR, PHOTO_DIR, LOG_DIR
```

runtime_config.py 又把它们按分组重新定义了一遍（GROUPS 字段、snapshot 字段映射、update 校验）。改一个参数要改两处。

**建议**：在 config.py 里用 dataclass + Pydantic/attrs 风格统一声明：

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class HardwareConfig:
    pca9685_addr: int = 0x60
    pwm_freq: int = 50
    motor_fl: int = 2
    motor_fr: int = 1
    ...

@dataclass
class LLMConfig:
    backend: str = "ollama"            # ollama | doubao | mock
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:0.5b"
    temperature: float = 0.7
    ...

@dataclass
class PetConfig:
    name: str = "小强"
    personality: str = "活泼友善的编程伙伴..."
    ...

@dataclass
class PetCarConfig:
    hw: HardwareConfig = field(default_factory=HardwareConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    pet: PetConfig = field(default_factory=PetConfig)
    ...
```

然后 runtime_config.py 的 GROUPS 字段直接引用 `config_fields(PetCarConfig)` 自动生成。

**工作量**：~200 行定义 + runtime_config.py 适配。值得做。

---

## 六、值得实现的新功能

### 6.1 积木编程增强（最高 ROI）

| 功能 | 积木 op | 描述 | 改动量 |
|------|---------|------|--------|
| 阻塞等待视觉 | `wait_sees(target, timeout)` | 等看到目标再往下走，积木表演必备 | 小（解释器加一个 op） |
| 视觉条件循环 | `while_sees(target)` / `while_not_sees` | 看到人脸就打招呼循环 | 小 |
| 运动中的视觉 | `move_while(target, dir, timeout)` | 边走边看，看到人脸停 | 中（需要解释器循环里掺视觉查询） |
| 多事件帽子 | `event_face_seen` / `event_color_seen` | 当前 compiler 只取第一个 `event_start`，扩展 IR 支持多 hat | 中（compiler + service） |
| 变量 | `set_var` / `get_var` / `compare` | 计数、计时、条件判断 | 中（解释器加 symbol table） |
| 子积木（函数） | `define_proc` / `call_proc` | 把"打招呼"打包成可复用积木 | 大（Blockly 前端 + compiler 作用域） |

当前 [compiler.py](file:///e:/work/AITank/petcar/blocks/compiler.py#L170-L208) 只返回单个 `event_start` hat：

```python
return {
    "version": 1,
    "block_count": counter["n"],
    "hats": [{"event": "start", "body": body}],   # ← 只有一个 hat
}
```

扩展成多 hat 的 IR 结构很简单，解释器几乎不用改（`ProgramRunner` 本来就是顺序执行，改成分发到多个 hat 就行）。

### 6.2 智能对话增强

| 功能 | 现状 | 建议 |
|------|------|------|
| 对话历史持久化 | 内存中 20 条 | 存到 SQLite/JSON，重启恢复，加 `/api/chat/history` 查看 |
| 真正的唤醒词 | config.py 预留了 `WAKE_WORD`，但 VoiceIO._loop 里没实现 | 用 Porcupine 的 Lightweight Keyword Detection，后台常驻监听，识别到唤醒词才触发 ASR |
| 情感上下文注入 | MoodEngine 独立跑，不影响对话 | 让 MoodEngine 的当前 valence/arousal 状态拼到 system prompt 里（"你现在心情还不错"） |
| 自然语言生成积木 | [docs/自然语言生成积木设计文档.md](file:///e:/work/AITank/petcar/docs/自然语言生成积木设计文档.md) 已经写好设计 | 用 LLM 把"如果看到人脸就说你好"翻译成 Blockly workspace JSON，面板加一个"让小强帮我写积木"按钮 |
| 技能/积木互调 | 各自独立 | 让 ChatAgent 多一个 `run_blocks(workspace)` skill，积木里多一个 `chat(text)` 积木直接向 LLM 提问 |

### 6.3 视觉能力扩展

| 功能 | 现状 | 建议 |
|------|------|------|
| COCO 通用检测接入积木 | detectors.py 已有 TFLite SSD（80 类），但积木层只用 face/tennis/color | 在 catalog.py TARGETS 里加 person / cup / tv / pet，PerceptionCache 里共享同一个 detector 实例 |
| 颜色追踪积木 | PIDTracker 已支持 color target，但积木层没有 | 加一个 `track_color(h_min, h_max, ...)` 积木，启动/停止 PID 追踪 |
| 手势识别触发 | flask_app.annotators 已注册 GestureDetector，积木层用不到 | 加一个 `if_gesture(gesture_name)` 积木 |

### 6.4 安全与硬件扩展

| 功能 | 描述 |
|------|------|
| 防碰撞（超声波） | 加 HC-SR04 GPIO 传感器，积木层加 `wait_until_clear(distance)` |
| 电量监控 | 读电池电压 GPIO，面板显示百分比，低电量自动提醒 + 归位 |
| 音频告警 | skills/alarm.py 已有骨架，需要实现真正的倒计时 + 时间触发 |
| 定时归位 | skill 或积木：电量 < 20% 自动掉头回充电座 |
| 远程日志上传 | 事件日志定期压缩上传到 webhook，老师远程能看到学生的课堂行为数据 |

---

## 七、推荐迭代路线图（4 周）

```
┌─────────────────────────────────────────────────────────────────────┐
│ Week 1 — 稳定性加固（让教学演示不再崩）                               │
│                                                                     │
│ ✅ HardwareGuard 仲裁器 + 全路径改造                                │
│ ✅ ChatAgent._trim_history 修复                                      │
│ ✅ VoiceIO 可中断 (asr.abort_listen)                                │
│ ✅ if_sees 连续 N 次确认 + wait_sees 阻塞版本                        │
│ ✅ 消除所有 except Exception: pass, 接入 logging                    │
│ ✅ 统一 logging 体系                                                 │
│                                                                     │
│ 交付物: 积木跑一整天不会因为并发而崩                                  │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Week 2 — 积木能力升级（最大差异化价值）                               │
│                                                                     │
│ ✅ 加 3 个积木 op: wait_sees / while_sees / move_while               │
│ ✅ 多事件帽子 (event_face_seen / event_color_seen)                  │
│ ✅ flask_app 拆路由蓝图                                              │
│ ✅ 抽取 HardwareGateway 让技能层和积木层共享硬件入口                 │
│ ✅ 检测器注册共享 (PerceptionCache ↔ flask_app.annotators)          │
│                                                                     │
│ 交付物: 能搭出完整表演脚本 (看到人→说你好→摇头→开心表情)             │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Week 3 — 教学场景增强                                               │
│                                                                     │
│ ✅ COCO 通用检测接入积木 (person / cup / tv / pet)                  │
│ ✅ 手势识别触发积木 (if_gesture)                                    │
│ ✅ 变量积木 (set_var / get_var / compare) — 计时、计数              │
│ ✅ 抽取 SKILL_RULES 公共定义, 消除 ChatAgent/MockBackend 规则重复    │
│ ✅ config → dataclass 化, runtime_config 自动生成字段                │
│                                                                     │
│ 交付物: 积木能覆盖从入门到进阶的完整课程                             │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ Week 4 — 演示 & 智能化                                              │
│                                                                     │
│ ✅ 预写 3 个示例积木程序 (打招呼 / 追踪网球 / 巡逻表演)              │
│ ✅ 自然语言生成积木 MVP (LLM → Blockly)                             │
│ ✅ 唤醒词检测 (Porcupine Lightweight Keyword)                       │
│ ✅ 情感上下文注入 system prompt                                     │
│ ✅ 对话历史持久化                                                    │
│ ✅ 写一份"PetCar 快速上手"和"积木编程教学"                          │
│                                                                     │
│ 交付物: 老师拿过去就能上课，学生 30 分钟搭出第一个表演                │
└─────────────────────────────────────────────────────────────────────┘
```

### 风险提示

| 风险 | 规避 |
|------|------|
| HardwareGuard 改造时引入新的死锁 | 所有 acquire 调用必须带 timeout 或 force_break_hold；HardwareGuard 自己带 watchdog，某 owner 持锁超过 5s 自动释放 |
| 多事件帽子 IR 格式变化导致老程序不兼容 | `compile_program()` 加 `legacy_mode=False`，遇到老的单 hat 格式自动转换 |
| 自然语言生成积木幻觉 | 先做 MVP：LLM 只输出 catalog.py 白名单里的积木组合 + 固定模板填充参数；后端做严格的白名单校验 |
| Porcupine 需要 API Key | 配置里加 `--mock` 开关，MockBackend 也能通过关键词触发；或者用开源的 openWakeWord 替换 |

---

## 八、附录：完整问题清单

### P0 — 生产阻塞

| # | 模块 | 文件 | 问题 | 预计修复 |
|---|------|------|------|----------|
| 1 | 全局 | 多处 | 硬件资源无统一仲裁，积木/PID/技能/面板可能同时写底盘和云台 | 150 行 HardwareGuard + 10 处接入点 |
| 2 | core | [chat_agent.py](file:///e:/work/AITank/petcar/core/chat_agent.py#L255) | `_trim_history()` 孤立 tool 消息未清理干净 | 5 行 |
| 3 | core | [voice_io.py](file:///e:/work/AITank/petcar/core/voice_io.py#L61) | `listen(timeout=15)` 阻塞无法被 Ctrl+C 及时中断 | 3 行 + `asr.abort_listen()` |
| 4 | blocks | [perception.py](file:///e:/work/AITank/petcar/blocks/perception.py) + [service.py](file:///e:/work/AITank/petcar/blocks/service.py#L312) | 3~4Hz 快照与 `if_sees` 不同步导致判断抖动 | catalog + compiler + service 改，~50 行 |
| 5 | 多处 | runtime.py / emotion_engine.py / detectors.py | 大量 `except Exception: pass` 静默吞异常 | ~20 处改 logging |

### P1 — 架构优化

| # | 模块 | 文件 | 问题 |
|---|------|------|------|
| 6 | api | flask_app.py 800+ 行 | 路由挤在一个函数里，检测器注册闭包难维护 |
| 7 | 全局 | skills/ ↔ blocks/ | 技能和积木两套独立硬件路径，互相看不见 |
| 8 | 全局 | 200+ print 散落 | 缺少统一 logging 体系 |
| 9 | drivers+api | detectors.py / flask_app.py / perception.py | 检测器各自初始化，color_cfg 配置源分裂 |

### P2 — 代码质量

| # | 模块 | 文件 | 问题 |
|---|------|------|------|
| 10 | core | [chat_agent.py](file:///e:/work/AITank/petcar/core/chat_agent.py#L40) vs [llm_backends.py](file:///e:/work/AITank/petcar/core/llm_backends.py#L165) | `_LOCAL_RULES` 和 MockBackend.RULES 规则重复 |
| 11 | config+core | config.py + runtime_config.py | 配置项在两处维护 |

### 值得实现的新功能

| # | 类型 | 功能 | 复杂度 | 价值 |
|---|------|------|--------|------|
| F1 | 积木 | wait_sees / while_sees / move_while | 🟢 小 | 表演脚本必备 |
| F2 | 积木 | 多事件帽子 event_face_seen | 🟡 中 | 从"脚本"变成"反应式" |
| F3 | 积木 | 变量 + 条件比较 | 🟡 中 | 计时/计数/状态机 |
| F4 | 积木 | COCO 通用检测接入 | 🟢 小 | 现成模型零成本 |
| F5 | 积木 | 手势触发 if_gesture | 🟢 小 | 已有 detector |
| F6 | 对话 | 自然语言生成积木 | 🟠 大 | LLM → Blockly，教学杀手级 |
| F7 | 对话 | 唤醒词检测 | 🟡 中 | 配置已预留，缺实现 |
| F8 | 对话 | 情感上下文注入 prompt | 🟢 小 | 系统提示词里加一行 |
| F9 | 对话 | 对话历史持久化 | 🟡 中 | SQLite 存 messages |
| F10 | 安全 | 超声波防碰撞积木 | 🟠 大 | 需新增 GPIO 驱动 |
| F11 | 安全 | 电量监控 | 🟡 中 | GPIO + 面板显示 |
| F12 | 技能 | alarm.py 真正实现倒计时 | 🟢 小 | 已有骨架 |

---

> **版本**: v1.0
>
> **日期**: 2026-11-09
>
> **评审范围**: petcar/ 全部源码 + 前端 + 已有设计文档
>
> **基于**: petcar/main.py / core/ / skills/ / blocks/ / api/ 共 34 个 .py 文件

