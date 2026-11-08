# -*- coding: utf-8 -*-
"""
drivers/tts.py — 语音合成 (TTS)
=================================
五种实现: edge (云端童声), piper (本地离线童声), espeak, pyttsx3, mock
"""

from __future__ import annotations

import sys
import os
import re
import json
import asyncio
import hashlib
import subprocess
import tempfile
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from petcar import config


class TTSDriver:
    """语音合成"""

    def __init__(self, mode: str = config.TTS_MODE):
        self.mode = mode
        self._engine = None
        self._play_device = self._resolve_play_device()
        # piper 离线管线 (懒启动)
        self._piper_proc = None
        self._piper_lock = threading.Lock()
        self._speaking = threading.Event()
        self._piper_checked = False
        self._piper_ok = False
        self._piper_rate = 22050

        if mode == "edge":
            self._init_edge()
        elif mode == "piper":
            self._init_piper()
        elif mode == "espeak":
            self._test_espeak()
            if self.mode == "espeak":
                print(f"[TTS] 播放设备: {self._play_device or '系统默认'}")
        elif mode == "pyttsx3":
            self._init_pyttsx3()
        elif mode == "mock":
            print("[TTS] Mock 模式 (只打印文本)")
        else:
            print(f"[TTS] 未知模式 {mode}, 退回 mock")
            self.mode = "mock"

    def _test_espeak(self):
        try:
            result = subprocess.run(["espeak", "--version"],
                                    capture_output=True, text=True, timeout=5)
            print(f"[TTS] espeak 可用: {result.stdout.strip()[:60]}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print("[TTS] espeak 未安装, 退回 mock (sudo apt install espeak)")
            self.mode = "mock"

    def _init_edge(self):
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            print("[TTS] edge-tts 未安装, 退回 espeak (pip3 install edge-tts)")
            self.mode = "espeak"
            self._test_espeak()
            return
        print(f"[TTS] edge-tts 童声: {config.TTS_VOICE} (pitch {config.TTS_PITCH})")
        print(f"[TTS] 播放设备: {self._play_device or '系统默认'}")

    def _init_piper(self):
        """本地离线童声: Piper 中文模型 + 音调提升 (不联网)"""
        if not self._piper_ready():
            self.mode = "espeak"
            self._test_espeak()
            return
        print(f"[TTS] piper 离线童声: {os.path.basename(config.PIPER_MODEL)} "
              f"(pitch x{config.PIPER_PITCH})")
        print(f"[TTS] 播放设备: {self._play_device or '系统默认'}")

    def _piper_ready(self) -> bool:
        """检查 piper 可执行文件和模型是否存在 (只提示一次)"""
        if self._piper_checked:
            return self._piper_proc is not None or self._piper_ok
        self._piper_checked = True
        self._piper_ok = (os.path.exists(config.PIPER_BIN)
                          and os.path.exists(config.PIPER_MODEL))
        if not self._piper_ok:
            print(f"[TTS] piper 不可用 ({config.PIPER_BIN} / "
                  f"{config.PIPER_MODEL}), 见 docs/使用说明.md 安装")
        return self._piper_ok

    def _start_piper_pipeline(self):
        """启动常驻 piper 进程 (模型只加载一次, 之后每句话只是一行输入)

        用 --output_dir 让 piper 每句写一个 wav 并把路径打到 stdout:
        这样既能复用已加载的模型, 又不用一直占着声卡 (云端 edge 随时可用)。
        """
        self._piper_rate = self._read_piper_rate()
        bin_dir = os.path.dirname(config.PIPER_BIN)
        out_dir = os.path.join(tempfile.gettempdir(), "petcar_piper")
        os.makedirs(out_dir, exist_ok=True)
        env = dict(os.environ)
        env["LD_LIBRARY_PATH"] = bin_dir + ":" + env.get("LD_LIBRARY_PATH", "")

        self._piper_proc = subprocess.Popen(
            [config.PIPER_BIN, "-m", config.PIPER_MODEL, "-d", out_dir,
             "--espeak_data", os.path.join(bin_dir, "espeak-ng-data")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=env)
        self._piper_dir = out_dir
        print("[TTS] piper 已启动 (离线童声)")

    def _read_piper_rate(self) -> int:
        try:
            with open(config.PIPER_MODEL + ".json", encoding="utf-8") as f:
                return int(json.load(f)["audio"]["sample_rate"])
        except Exception:
            return 22050

    def _speak_piper(self, text: str) -> bool:
        """离线合成并播放; 失败返回 False"""
        if not self._piper_ready():
            return False
        with self._piper_lock:
            try:
                if self._piper_proc is None or self._piper_proc.poll() is not None:
                    self._start_piper_pipeline()
                self._piper_proc.stdin.write((text + "\n").encode("utf-8"))
                self._piper_proc.stdin.flush()
                # piper 合成完会把 wav 路径打到 stdout (没有输出即失败)
                line = self._piper_proc.stdout.readline()
                wav = line.decode("utf-8", errors="replace").strip()
                if not wav or not os.path.exists(wav):
                    print(f"[TTS] piper 未输出音频: {wav[:60]}")
                    return False
                self._play_piper_wav(wav)
                return True
            except Exception as e:
                print(f"[TTS] piper 播放失败 ({e}), 改用 espeak")
                self._piper_proc = None
                return False

    def _play_piper_wav(self, path: str):
        """原 wav 音调提升 (童声化) 后播放, 播完删除临时文件"""
        rate = self._piper_rate
        pitch = config.PIPER_PITCH
        kid = path.replace(".wav", "_kid.wav")
        try:
            af = (f"asetrate={rate}*{pitch},aresample=44100,atempo={1.0 / pitch:.4f}"
                  if pitch and pitch != 1.0 else "anull")
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", path,
                 "-af", af, "-ar", "44100", kid],
                check=True, capture_output=True, timeout=60)
            self._play_audio_file(kid)
        finally:
            for p in (path, kid):
                try:
                    os.remove(p)
                except OSError:
                    pass

    def _init_pyttsx3(self):
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            # 尝试设中文语音
            try:
                voices = self._engine.getProperty('voices')
                for v in voices:
                    if 'zh' in (v.language or '').lower():
                        self._engine.setProperty('voice', v.id)
                        break
            except Exception:
                pass
            self._engine.setProperty('rate', 150)
            print("[TTS] pyttsx3 初始化成功")
        except ImportError:
            print("[TTS] pyttsx3 未安装, 退回 espeak")
            self.mode = "espeak"
            self._test_espeak()
        except Exception as e:
            print(f"[TTS] pyttsx3 初始化失败 ({e}), 退回 mock")
            self.mode = "mock"

    def _resolve_play_device(self) -> str:
        """决定用哪个 ALSA 设备播放: 配置优先, 否则自动找 USB 声卡 / 板载耳机口"""
        if config.TTS_DEVICE:
            return config.TTS_DEVICE
        try:
            with open("/proc/asound/cards", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            return ""
        cards = re.findall(r"^\s*\d+\s+\[([^\]]+)\]:\s*(.+)$", text, re.M)
        for keyword in ("USB-Audio", "bcm2835_headpho"):
            for card_id, driver in cards:
                if keyword in driver:
                    return f"plughw:CARD={card_id.strip()},DEV=0"
        return ""

    def apply_config(self):
        """面板改完 TTS 配置后重建引擎 (音色/音调/变调/超时在调用时现读)"""
        self.mode = config.TTS_MODE
        self._play_device = self._resolve_play_device()
        self._engine = None
        if self.mode == "edge":
            self._init_edge()
        elif self.mode == "piper":
            self._piper_checked = False
            self._init_piper()
        elif self.mode == "espeak":
            self._test_espeak()
        elif self.mode == "pyttsx3":
            self._init_pyttsx3()
        elif self.mode == "mock":
            print("[TTS] Mock 模式 (只打印文本)")
        else:
            print(f"[TTS] 未知模式 {self.mode}, 退回 mock")
            self.mode = "mock"

    # ========================================================================
    def speak(self, text: str, emotion: str = "neutral"):
        """同步播放语音"""
        if not text:
            return
        # 截断避免说太长
        text = text[:100]

        self._speaking.set()
        try:
            if self.mode == "edge":
                # 云端童声 → 断网/超时降级本地 piper → 最后才用 espeak
                if not self._speak_edge(text) and not self._speak_piper(text):
                    self._speak_espeak(text)
            elif self.mode == "piper":
                if not self._speak_piper(text):
                    self._speak_espeak(text)
            elif self.mode == "espeak":
                self._speak_espeak(text)
            elif self.mode == "pyttsx3":
                self._speak_pyttsx3(text)
            elif self.mode == "mock":
                print(f"[TTS Mock] ({emotion}) {text}")
        finally:
            self._speaking.clear()

    def is_speaking(self) -> bool:
        """是否正在播放 (语音识别期间要避开, 否则会把自己的声音当用户)"""
        return self._speaking.is_set()

    def speak_async(self, text: str, emotion: str = "neutral"):
        """异步播放 (后台线程)"""
        threading.Thread(target=self.speak, args=(text, emotion),
                         daemon=True).start()

    # ========================================================================
    def _speak_edge(self, text: str) -> bool:
        """云端童声合成并播放; 失败返回 False, 交给 espeak 兜底"""
        key = hashlib.md5(
            f"{config.TTS_VOICE}|{config.TTS_PITCH}|{text}".encode("utf-8")
        ).hexdigest()[:16]
        mp3 = os.path.join(tempfile.gettempdir(), f"petcar_tts_{key}.mp3")
        try:
            if not os.path.exists(mp3):
                asyncio.run(self._edge_save(text, mp3))
            self._play_audio_file(mp3)
            return True
        except Exception as e:
            print(f"[TTS] edge 不可用 ({e}), 降级本地 piper")
            return False

    @staticmethod
    async def _edge_save(text: str, path: str):
        import edge_tts
        kwargs = {"pitch": config.TTS_PITCH} if config.TTS_PITCH else {}
        # 断网时 edge-tts 可能卡很久, 限制等待时间让上层快速降级到 piper
        await asyncio.wait_for(
            edge_tts.Communicate(text, config.TTS_VOICE, **kwargs).save(path),
            timeout=config.EDGE_TIMEOUT)

    def _play_audio_file(self, path: str):
        """ffmpeg 解码 → aplay 输出到指定设备"""
        ffmpeg = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", path, "-f", "wav", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        cmd = ["aplay", "-q"] + (["-D", self._play_device] if self._play_device else [])
        aplay = subprocess.Popen(cmd, stdin=ffmpeg.stdout,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        ffmpeg.stdout.close()
        _, err = aplay.communicate(timeout=60)
        ffmpeg.wait(timeout=10)
        if aplay.returncode != 0:
            raise RuntimeError(err.decode(errors="replace").strip() or "aplay 失败")

    # ========================================================================
    def _speak_espeak(self, text: str):
        # -v zh: 中文语音 (-v zh+m 男, -v zh+f 女), -s 速度
        if not self._play_device:
            try:
                subprocess.run(["espeak", "-v", "zh+f", "-s", "150", text],
                               timeout=30, capture_output=True)
            except Exception as e:
                print(f"[TTS] espeak 播放失败: {e}")
            return
        # 指定了设备: espeak 合成到 stdout, 再交给 aplay 输出到该设备
        try:
            espeak = subprocess.Popen(
                ["espeak", "-v", "zh+f", "-s", "150", "--stdout", text],
                stdout=subprocess.PIPE)
            aplay = subprocess.Popen(["aplay", "-q", "-D", self._play_device],
                                     stdin=espeak.stdout,
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE)
            espeak.stdout.close()
            _, err = aplay.communicate(timeout=30)
            espeak.wait(timeout=5)
            if aplay.returncode != 0:
                print(f"[TTS] aplay 播放失败 ({self._play_device}): "
                      f"{err.decode(errors='replace').strip()}")
        except Exception as e:
            print(f"[TTS] espeak 播放失败: {e}")

    def _speak_pyttsx3(self, text: str):
        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception as e:
            print(f"[TTS] pyttsx3 播放失败: {e}")


if __name__ == "__main__":
    print("测试 TTS...")
    tts = TTSDriver(mode="mock")
    tts.speak(f"你好呀，我是{config.PET_NAME}！")
    tts.speak("今天天气怎么样？", emotion="happy")
