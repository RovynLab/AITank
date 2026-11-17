# -*- coding: utf-8 -*-
"""
whisper_service.py — 独立 whisper 识别服务 (systemd 常驻)
=========================================================

开机自启，模型预加载到内存，petcar 通过 localhost HTTP 调用。

启动:
    python3 -m petcar.services.whisper_service       # 前台调试
    systemctl start aitank-whisper                   # 正式（推荐）

环境变量:
    WHISPER_MODEL    tiny / base / small / medium   (默认 small)
    WHISPER_DEVICE   cpu / cuda                      (默认 cpu)
    WHISPER_COMPUTE  int8 / float16 / float32       (默认 int8)
    WHISPER_LANG     zh / en / ...                   (默认 zh，auto 表示自动检测)
    WHISPER_PORT     8091                            (默认 8091)
    HF_ENDPOINT      HuggingFace 镜像 (国内加速下载)

API:
    GET  /health            → {ok, model, loaded, uptime}
    POST /transcribe        → multipart audio=xxx.wav → {text, duration, language}
"""

from __future__ import annotations

import os
import sys
import time
import tempfile
from typing import Optional

import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse


# ============================================================================
# 配置
# ============================================================================
MODEL_NAME  = os.environ.get("WHISPER_MODEL", "small")
DEVICE      = os.environ.get("WHISPER_DEVICE", "cpu")
COMPUTE     = os.environ.get("WHISPER_COMPUTE", "int8")
LANG        = os.environ.get("WHISPER_LANG", "zh")
PORT        = int(os.environ.get("WHISPER_PORT", "8091"))

_start_time = time.time()
_model = None
_load_error: Optional[str] = None


# ============================================================================
# 启动时同步加载模型（systemd 会等这个结束，之后才 accept 连接）
# ============================================================================
print(f"[WhisperService] 开始加载模型: {MODEL_NAME} ({DEVICE}/{COMPUTE}) ...", flush=True)
try:
    from faster_whisper import WhisperModel
    t0 = time.time()
    _model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE)
    print(f"[WhisperService] 模型加载完成，耗时 {time.time() - t0:.1f}s", flush=True)
except Exception as e:
    _load_error = str(e)
    print(f"[WhisperService] ⚠️ 模型加载失败: {e}", flush=True)
    print(f"[WhisperService] 服务仍会启动，但 /transcribe 会返回错误", flush=True)


# ============================================================================
# FastAPI
# ============================================================================
app = FastAPI(title="AITank Whisper Service", version="1.0.0")


@app.get("/health")
def health():
    uptime = int(time.time() - _start_time)
    if _model is None:
        return JSONResponse(
            status_code=503,
            content={"ok": False, "model": MODEL_NAME, "loaded": False,
                     "error": _load_error, "uptime": uptime},
        )
    return {"ok": True, "model": MODEL_NAME, "loaded": True,
            "device": DEVICE, "compute": COMPUTE, "uptime": uptime}


@app.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    language: Optional[str] = None,
    beam_size: int = 1,
    vad_filter: bool = True,
):
    if _model is None:
        raise HTTPException(
            status_code=503,
            detail=f"模型未加载: {_load_error}",
        )

    # 落盘 faster-whisper 自己做重采样（跟 ASRDriver 的处理一致）
    suffix = os.path.splitext(audio.filename or "audio.wav")[1] or ".wav"
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        content = await audio.read()
        if not content:
            raise HTTPException(status_code=400, detail="音频文件为空")
        with open(tmp_path, "wb") as f:
            f.write(content)

        # 语言: 参数优先 → 环境变量 → auto
        lang = language or (None if LANG == "auto" else LANG)

        t0 = time.time()
        segments, info = _model.transcribe(
            tmp_path,
            language=lang,
            beam_size=beam_size,
            vad_filter=vad_filter,
        )
        segs = list(segments)
        text = "".join(s.text for s in segs).strip()
        elapsed = time.time() - t0

        # 置信度过滤（跟 asr.py 保持一致）
        avg_logprob = None
        if segs:
            avg_logprob = sum(s.avg_logprob for s in segs) / len(segs)
            if avg_logprob < -1.0:
                print(f"[WhisperService] 置信度低 ({avg_logprob:.2f}), "
                      f"忽略: {text[:30]}", flush=True)
                text = ""

        # 重复检测
        if len(text) >= 8 and text[:len(text) // 2] == text[len(text) // 2:]:
            text = text[:len(text) // 2]

        # 纯数字过滤
        text = " ".join(tok for tok in text.split() if not tok.isdigit()).strip()

        return {
            "text": text,
            "duration": round(info.duration, 2),
            "language": info.language,
            "elapsed": round(elapsed, 2),
            "avg_logprob": round(avg_logprob, 2) if avg_logprob is not None else None,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[WhisperService] 转写异常: {e}", flush=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


@app.get("/")
def root():
    return {"service": "aitank-whisper", "version": "1.0.0",
            "model": MODEL_NAME, "loaded": _model is not None,
            "endpoints": ["/health", "/transcribe"]}


# ============================================================================
# 直接运行（前台调试）
# ============================================================================
if __name__ == "__main__":
    print(f"[WhisperService] 监听 0.0.0.0:{PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info",
                access_log=False)
