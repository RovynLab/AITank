# -*- coding: utf-8 -*-
"""
core/runtime_config.py — 面板运行时配置
======================================

中控面板「设置」里可改的配置项集中在这里:
- SCHEMA 白名单决定哪些项允许改、取值范围、分组、是否需重启
- 值直接写回 petcar.config 模块属性, 驱动层读 config.XXX 即可生效
- 持久化到 petcar/config_local.json (只保存面板改过的 key, 不进 Git)
- 环境变量视为「启动参数默认值」; 面板保存过的 key 优先于环境变量
"""

from __future__ import annotations

import importlib
import json
import os
import threading

from petcar import config

# 放在仓库根目录的 data/ 下, 而不是 petcar/ 内:
# deploy_petcar.py 推送时会 rm -rf petcar/, 放在里面会导致面板配置被清空
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOCAL_PATH = os.path.join(_ROOT, "data", "config_local.json")

_LOCK = threading.RLock()
_LOADED = False

# ============================================================================
# 分组 (面板按顺序渲染)
# ============================================================================
GROUPS = [
    {"id": "identity", "label": "🐾 身份",
     "desc": "决定机器人叫什么、什么性格、开机第一句话说什么。"},
    {"id": "llm", "label": "🧠 大模型",
     "desc": "决定它用哪个模型思考。选 mock 可完全离线、秒回，适合只做指令控制。"},
    {"id": "voice", "label": "🎙️ 语音",
     "desc": "决定它怎么听、怎么说。听不清或声音奇怪时优先调这里。"},
]

# ============================================================================
# 字段白名单
# ============================================================================
SCHEMA = [
    # ---------------- 身份 ----------------
    {"key": "pet_name", "attr": "PET_NAME", "group": "identity",
     "label": "宠物名字", "type": "text", "maxlen": 20,
     "help": "改名后立即重建人格提示词与面板标题",
     "desc": "机器人以后对外展示的名字。聊天、打招呼、面板里都会用这个名字。"
             "改名后立即生效，不需要重启服务。"},
    {"key": "personality", "attr": "PET_PERSONALITY", "group": "identity",
     "label": "人格提示词", "type": "textarea", "maxlen": 500,
     "help": "立即重建 System Prompt",
     "desc": "告诉大模型“它是谁、该怎么说话”的人设。写得越具体，语气越稳定，"
             "例如：你是一只活泼的小猫，每次最多回答两句话，喜欢用语气词。"
             "留空则使用默认人格。"},
    {"key": "startup_greeting", "attr": "STARTUP_GREETING", "group": "identity",
     "label": "开机问候", "type": "textarea", "maxlen": 200,
     "help": "下次启动自动播报的文本",
     "desc": "服务启动后自动朗读的第一句话，用来做开场介绍。"
             "留空表示启动时不主动说话。修改后下次启动才生效。"},

    # ---------------- LLM ----------------
    {"key": "llm_backend", "attr": "LLM_BACKEND", "group": "llm",
     "label": "LLM 后端", "type": "select",
     "options": ["ollama", "doubao", "mock"],
     "help": "mock = 本地规则秒回, 不依赖大模型",
     "desc": "决定由谁生成回复。ollama：模型跑在板子本地，断网也能用，但速度较慢；"
             "doubao：云端大模型，更聪明，需要联网并填写 API Key；"
             "mock：不调用模型，用内置规则秒回，适合只做指令控制或现场演示。"},
    {"key": "ollama_host", "attr": "OLLAMA_HOST", "group": "llm",
     "label": "Ollama 地址", "type": "text",
     "when": {"field": "llm_backend", "in": ["ollama"]},
     "help": "本机默认 http://localhost:11434；模型跑在别的电脑上时填那台电脑的 IP",
     "desc": "本地 Ollama 服务的地址。默认 http://127.0.0.1:11434 表示模型跑在同一块板子上；"
             "如果模型跑在另一台电脑，填那台电脑的局域网 IP，例如 http://192.168.1.10:11434。"},
    {"key": "ollama_model", "attr": "OLLAMA_MODEL", "group": "llm",
     "label": "Ollama 模型", "type": "text",
     "when": {"field": "llm_backend", "in": ["ollama"]},
     "help": "如 qwen2.5:0.5b / qwen2.5:1.5b",
     "desc": "要使用的本地模型名称，必须是 Ollama 里已经下载过的名字。"
             "qwen2.5:0.5b 更快、占用小；qwen2.5:1.5b 更聪明但更吃内存。"
             "名字填错时会自动回退到 mock。"},
    {"key": "doubao_api_key", "attr": "DOUBAO_API_KEY", "group": "llm",
     "label": "豆包 API Key", "type": "password", "secret": True,
     "when": {"field": "llm_backend", "in": ["doubao"]},
     "help": "留空表示不修改; 保存后只回显掩码",
     "desc": "豆包/火山引擎开放平台的 API Key，相当于云端模型的登录密码。"
             "只保存在板子本地，面板只显示后 4 位。留空表示保持原来的 Key 不变。"},
    {"key": "doubao_model", "attr": "DOUBAO_MODEL", "group": "llm",
     "label": "豆包模型", "type": "text",
     "when": {"field": "llm_backend", "in": ["doubao"]},
     "help": "按账号实际开通的模型填写，如 doubao-pro-32k / doubao-lite-4k",
     "desc": "豆包侧要调用的模型名称或推理接入点 ID，需要和你在火山引擎控制台创建的一致。"
             "只有 LLM 后端选 doubao 时才会用到。"},
    {"key": "llm_temperature", "attr": "LLM_TEMPERATURE", "group": "llm",
     "label": "回答发散度 (温度)", "type": "number", "min": 0, "max": 2,
     "step": 0.05,
     "when": {"field": "llm_backend", "in": ["ollama", "doubao"]},
     "help": "0 最稳定、2 最放飞。小模型建议 0.5~0.8，避免胡言乱语",
     "desc": "控制回答的随机程度。0 最稳定，几乎每次一样；0.7 比较自然；"
             "1 以上更发散，也更容易跑题。小模型建议 0.5~0.8。"},
    {"key": "llm_num_predict", "attr": "LLM_NUM_PREDICT", "group": "llm",
     "label": "单次最长回复 (token)", "type": "number", "min": 16, "max": 512,
     "step": 1, "integer": True,
     "when": {"field": "llm_backend", "in": ["ollama", "doubao"]},
     "help": "越大回复越长也越慢。树莓派小模型建议 100~200",
     "desc": "单次回复最多生成多少 token，越大回答越完整，但等待时间越长。"
             "树莓派上的小模型建议 100~200，避免一句话等太久。"},
    {"key": "llm_timeout", "attr": "LLM_TIMEOUT", "group": "llm",
     "label": "模型请求超时 (秒)", "type": "number", "min": 10, "max": 600,
     "step": 5, "integer": True,
     "when": {"field": "llm_backend", "in": ["ollama", "doubao"]},
     "help": "板子慢或模型大时调大，避免回答到一半被判超时",
     "desc": "等待模型回复的最长时间，超过就判定失败。"
             "本地模型首次加载会慢一些，可以调到 180~300 秒；云端通常 30 秒就够。"},

    # ---------------- 语音 ----------------
    {"key": "tts_mode", "attr": "TTS_MODE", "group": "voice",
     "label": "发音方式 (TTS)", "type": "select",
     "options": ["edge", "piper", "espeak", "pyttsx3", "mock"],
     "help": "edge = 云端自然童声（需联网）；piper = 本地离线童声；"
             "espeak = 机械音兜底；mock = 只打印不发音",
     "desc": "机器人怎么发声。edge：微软云端自然童声，最像小朋友，但需要联网；"
             "piper：本地离线童声，断网也能说；espeak：系统机械音，作为兜底；"
             "mock：不出声，只在日志里打印文字，适合排查问题。"},
    {"key": "tts_voice", "attr": "TTS_VOICE", "group": "voice",
     "label": "edge 音色", "type": "text",
     "when": {"field": "tts_mode", "in": ["edge"]},
     "help": "zh-CN-XiaoyiNeural 女童 / zh-CN-YunxiaNeural 男童",
     "desc": "edge 模式使用的音色。zh-CN-XiaoyiNeural 是女童音，"
             "zh-CN-YunxiaNeural 是男童音。只有发音方式选 edge 时生效。"},
    {"key": "tts_pitch", "attr": "TTS_PITCH", "group": "voice",
     "label": "edge 音调", "type": "text",
     "when": {"field": "tts_mode", "in": ["edge"]},
     "help": "如 +15Hz, 调高更像小朋友",
     "desc": "edge 模式的音调偏移，例如 +15Hz 会更高、更像小朋友。"
             "调太高可能失真，一般用 +10Hz 到 +30Hz。"},
    {"key": "tts_device", "attr": "TTS_DEVICE", "group": "voice",
     "label": "播放设备", "type": "text",
     "when": {"field": "tts_mode", "in": ["edge", "piper", "espeak", "pyttsx3"]},
     "help": "留空自动探测 USB 声卡; 如 plughw:CARD=UACDemoV10,DEV=0",
     "desc": "声音从哪块声卡播放。留空会自动寻找 USB 声卡；"
             "如果插了多个声卡、或机器人在跑但没声音，可以在这里指定设备名，"
             "例如 plughw:CARD=UACDemoV10,DEV=0。"},
    {"key": "piper_pitch", "attr": "PIPER_PITCH", "group": "voice",
     "label": "Piper 变调", "type": "number", "min": 0.8, "max": 1.6,
     "step": 0.01, "when": {"field": "tts_mode", "in": ["piper"]}, "help": "1.0 原声, 越大越像小孩",
     "desc": "离线童声的变调倍数。1.0 是原声，1.1~1.3 更接近小朋友。"
             "改完下一句话就会生效。"},
    {"key": "edge_timeout", "attr": "EDGE_TIMEOUT", "group": "voice",
     "label": "云端合成超时 (秒)", "type": "number", "min": 2, "max": 60,
     "step": 1, "when": {"field": "tts_mode", "in": ["edge"]}, "help": "超时自动降级本地 piper",
     "desc": "云端语音合成最多等多久。网络慢或超时会自动改用本地 piper，"
             "避免机器人突然不说话。网络不好时适当调大。"},
    {"key": "asr_mode", "attr": "ASR_MODE", "group": "voice",
     "label": "收音识别方式 (ASR)", "type": "select",
     "options": ["whisper", "mock"], "restart": True,
     "help": "whisper = 真实语音识别（需重启并加载模型）；"
             "mock = 不收音，只用网页文字对话",
     "desc": "机器人怎么听你说话。whisper：真实录音并识别，需要加载模型，启动较慢；"
             "mock：不录音，只接受网页文字输入，适合快速演示。切换后需要重启服务。"},
    {"key": "whisper_model", "attr": "WHISPER_MODEL", "group": "voice",
     "label": "Whisper 模型", "type": "select",
     "options": ["tiny", "base", "small", "medium"],
     "when": {"field": "asr_mode", "in": ["whisper"]},
     "restart": True, "help": "越大越准也越慢, 2GB 板推荐 base",
     "desc": "语音识别模型的大小。tiny 最快但准确率低；base 平衡，2GB 内存的板子推荐；"
             "small/medium 更准，但更占内存、启动更慢。切换后需要重启服务。"},
    {"key": "asr_device", "attr": "ASR_DEVICE", "group": "voice",
     "label": "麦克风设备", "type": "text",
     "when": {"field": "asr_mode", "in": ["whisper"]},
     "help": "留空自动探测; 可填序号或名字片段",
     "desc": "用哪个麦克风收音。留空自动寻找 USB 麦克风；"
             "如果有多个麦克风，或机器人听不到声音，可以填设备序号（如 1）"
             "或名字片段（如 USB）。"},
    {"key": "vad_threshold_max", "attr": "VAD_THRESHOLD_MAX", "group": "voice",
     "label": "起录灵敏度上限", "type": "number", "min": 0.005, "max": 0.2,
     "step": 0.005, "when": {"field": "asr_mode", "in": ["whisper"]}, "help": "越小越灵敏, 环境嘈杂时调大",
     "desc": "多大声才算“开始说话”的上限。数值越小越灵敏，安静环境可调小；"
             "风扇、空调噪声大时调大，避免把噪声当成说话。"},
    {"key": "vad_speech_ms", "attr": "VAD_SPEECH_MS", "group": "voice",
     "label": "连续有声起录 (ms)", "type": "number", "min": 50, "max": 1000,
     "step": 50, "integer": True,
     "when": {"field": "asr_mode", "in": ["whisper"]},
     "desc": "声音要连续持续多久才正式开录。太短容易把咳嗽、碰桌子当成说话；"
             "太长可能吃掉开头一两个字。200ms 适合大多数情况。"},
    {"key": "vad_silence_ms", "attr": "VAD_SILENCE_MS", "group": "voice",
     "label": "静音结束 (ms)", "type": "number", "min": 300, "max": 3000,
     "step": 100, "integer": True,
     "when": {"field": "asr_mode", "in": ["whisper"]},
     "desc": "说完之后安静多久算一句话结束。太短会把句子截断，"
             "太长会让机器人反应变慢。一般 1000~1500ms。"},
]

_BY_KEY = {f["key"]: f for f in SCHEMA}

# 字段 → 环境变量 (只用于面板提示「启动参数值」)
ENV_KEYS = {
    "startup_greeting": "PETCAR_STARTUP_GREETING",
    "llm_backend": "PETCAR_LLM_BACKEND",
    "ollama_host": "PETCAR_OLLAMA_HOST",
    "ollama_model": "PETCAR_OLLAMA_MODEL",
    "doubao_api_key": "PETCAR_DOUBAO_KEY",
    "doubao_model": "PETCAR_DOUBAO_MODEL",
    "llm_temperature": "PETCAR_LLM_TEMPERATURE",
    "llm_num_predict": "PETCAR_LLM_NUM_PREDICT",
    "llm_timeout": "PETCAR_LLM_TIMEOUT",
    "tts_mode": "PETCAR_TTS_MODE",
    "tts_voice": "PETCAR_TTS_VOICE",
    "tts_pitch": "PETCAR_TTS_PITCH",
    "tts_device": "PETCAR_TTS_DEVICE",
    "piper_pitch": "PETCAR_PIPER_PITCH",
    "edge_timeout": "PETCAR_EDGE_TIMEOUT",
    "asr_mode": "PETCAR_ASR_MODE",
    "whisper_model": "PETCAR_WHISPER_MODEL",
    "asr_device": "PETCAR_ASR_DEVICE",
    "vad_threshold_max": "PETCAR_VAD_THRESHOLD_MAX",
    "vad_speech_ms": "PETCAR_VAD_SPEECH_MS",
    "vad_silence_ms": "PETCAR_VAD_SILENCE_MS",
}


# ============================================================================
# 内部工具
# ============================================================================
def _mask(value) -> str:
    s = str(value or "")
    return "****" + s[-4:] if len(s) > 4 else ("****" if s else "")


def _coerce(field: dict, value):
    """把面板传来的值转成 config 需要的类型并做范围钳制"""
    key, ftype = field["key"], field["type"]
    if ftype == "number":
        try:
            num = float(value)
        except (TypeError, ValueError):
            raise ValueError("必须是数字")
        if "min" in field:
            num = max(field["min"], num)
        if "max" in field:
            num = min(field["max"], num)
        return int(round(num)) if field.get("integer") else num
    if ftype == "select":
        val = str(value)
        if val not in field.get("options", []):
            raise ValueError("不在可选范围内")
        return val
    # text / textarea / password
    val = "" if value is None else str(value)
    if key == "pet_name":
        val = val.strip()
        if not val:
            raise ValueError("名字不能为空")
    maxlen = field.get("maxlen")
    if maxlen and len(val) > maxlen:
        val = val[:maxlen]
    return val


def _read_file() -> dict:
    try:
        with open(LOCAL_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_file(data: dict):
    os.makedirs(os.path.dirname(LOCAL_PATH), exist_ok=True)
    tmp = LOCAL_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, LOCAL_PATH)
    try:
        os.chmod(LOCAL_PATH, 0o600)   # 里面有 API Key
    except OSError:
        pass


# ============================================================================
# 对外接口
# ============================================================================
def load() -> dict:
    """启动时调用: 用 config_local.json 覆盖 config 模块的默认值 (只执行一次)"""
    global _LOADED
    if _LOADED:
        return {}
    _LOADED = True
    data = _read_file()
    applied = {}
    with _LOCK:
        for f in SCHEMA:
            if f["key"] not in data:
                continue
            try:
                val = _coerce(f, data[f["key"]])
                setattr(config, f["attr"], val)
                applied[f["key"]] = val
            except Exception as e:
                print(f"[Config] 忽略无效配置 {f['key']}={data[f['key']]!r}: {e}")
    if applied:
        print(f"[Config] 已加载面板配置 {len(applied)} 项: "
              f"{', '.join(applied)}")
    return applied


def snapshot() -> dict:
    """返回面板渲染所需的字段元数据 + 当前值"""
    saved = _read_file()
    fields = []
    for f in SCHEMA:
        raw = getattr(config, f["attr"], "")
        item = {k: f[k] for k in ("key", "label", "group", "type") if k in f}
        for k in ("options", "min", "max", "step", "restart", "secret",
                  "help", "desc", "when"):
            if k in f:
                item[k] = f[k]
        if f.get("secret"):
            item["value"] = ""
            item["is_set"] = bool(raw)
            item["masked"] = _mask(raw)
        else:
            item["value"] = raw
        item["saved"] = f["key"] in saved
        env_key = ENV_KEYS.get(f["key"])
        env_val = os.environ.get(env_key) if env_key else None
        if env_val is not None and not f.get("secret"):
            item["env"] = env_val
        fields.append(item)
    return {"groups": GROUPS, "fields": fields}


def update(patch: dict) -> dict:
    """局部更新: 校验 → 写回 config → 持久化。返回变更与需重启项"""
    if not isinstance(patch, dict):
        raise ValueError("patch 必须是对象")

    data = _read_file()
    changed, restart, errors = [], [], {}
    with _LOCK:
        for key, raw in patch.items():
            f = _BY_KEY.get(key)
            if f is None:
                errors[key] = "不支持的配置项"
                continue
            if f.get("secret") and (raw is None or str(raw) == ""):
                continue          # 留空 = 保持原 Key
            try:
                val = _coerce(f, raw)
            except Exception as e:
                errors[key] = str(e)
                continue
            setattr(config, f["attr"], val)
            data[key] = val
            changed.append(key)
            if f.get("restart"):
                restart.append(key)
        if changed:
            _write_file(data)

    return {
        "changed": changed,
        "restart": restart,
        "restart_required": bool(restart),
        "errors": errors,
    }


def reset() -> dict:
    """删除本地配置并恢复 config.py / 环境变量默认值"""
    with _LOCK:
        try:
            os.remove(LOCAL_PATH)
        except FileNotFoundError:
            pass
        except OSError as e:
            raise RuntimeError(f"删除配置失败: {e}")
        # 重新执行 config.py, 重新读取环境变量默认值 (其他模块引用同一模块对象)
        importlib.reload(config)
    return snapshot()
