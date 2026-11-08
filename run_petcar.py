# -*- coding: utf-8 -*-
"""
run_petcar.py — AI-PetCar 一键启动脚本
======================================

用法:
    python run_petcar.py              # 板上启动中控面板 (快速模式: ASR 走 mock)
    python run_petcar.py --push       # 先推最新代码, 再启动
    python run_petcar.py --voice      # 开启麦克风语音对话 (whisper base, 较慢)
    python run_petcar.py --full       # 真实语音链路 (加载 whisper small)
    python run_petcar.py --port 5000  # 指定端口
    python run_petcar.py --stop       # 停止板上进程
    python run_petcar.py --logs       # 查看最近日志
    python run_petcar.py --restart    # 重启

也可以双击同目录的 run_petcar.bat。

说明:
    petcar 是"进程内"启动的: main.py 先初始化驱动/核心层, 再在后台线程里跑
    Flask, 所以只需在板上起一个 python3 -m petcar.main 进程即可, 不需要 nginx
    之类的额外服务。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

import paramiko

HOST = os.environ.get("PETCAR_HOST", "192.168.0.100")
USER = os.environ.get("PETCAR_SSH_USER", "pi")
PASS = os.environ.get("PETCAR_SSH_PASS", "raspberrypi")

LOCAL_ROOT = os.path.dirname(os.path.abspath(__file__))
REMOTE_ROOT = f"/home/{USER}/AITank"
LOG_FILE = f"{REMOTE_ROOT}/petcar/logs/petcar.log"
# 用 [p] 避免 pkill/pgrep 匹配到命令自身
PROC_PATTERN = "[p]etcar.main"


def connect() -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASS, timeout=15)
    print(f"[OK] SSH → {USER}@{HOST}")
    return c


def sh(c, cmd: str, timeout: int = 30) -> str:
    _, so, se = c.exec_command(cmd, timeout=timeout)
    out = so.read().decode(errors="replace").strip()
    err = se.read().decode(errors="replace").strip()
    so.channel.recv_exit_status()
    return out or err


def is_running(c) -> bool:
    return bool(sh(c, f"pgrep -f '{PROC_PATTERN}'").strip())


def stop(c, quiet: bool = False) -> None:
    if not is_running(c):
        if not quiet:
            print("[..] 板上没有运行中的 petcar")
        return
    sh(c, f"pkill -f '{PROC_PATTERN}'")
    for _ in range(20):
        if not is_running(c):
            print("[OK] 已停止旧进程")
            return
        time.sleep(0.5)
    sh(c, f"pkill -9 -f '{PROC_PATTERN}'")
    print("[OK] 已强制停止旧进程")


def start(c, port: int, full: bool, voice: bool = False,
          offline: bool = False) -> None:
    sh(c, f"mkdir -p {os.path.dirname(LOG_FILE)}")
    # PYTHONUNBUFFERED: 日志重定向到文件时 print 是块缓冲的, 不实时
    env = "PYTHONUNBUFFERED=1 "
    env += f"PETCAR_LLM_BACKEND={os.environ.get('PETCAR_LLM_BACKEND', 'ollama')} "
    if offline:
        # 语音走本地 piper 离线童声, 不依赖外网
        env += "PETCAR_TTS_MODE=piper "
    if voice:
        # 语音对话: 真实 ASR; base 模型在 2GB 内存板上更稳
        env += f"PETCAR_WHISPER_MODEL={os.environ.get('PETCAR_WHISPER_MODEL', 'base')} "
        # 板子直连 huggingface 不通, whisper 模型走国内镜像下载
        env += "HF_ENDPOINT=https://hf-mirror.com "
    elif not full:
        # 快速模式只跳过 whisper 模型加载, TTS 保留 (启动自我介绍/语音播报需要)
        env += "PETCAR_ASR_MODE=mock "

    mode = f"语音对话 (whisper {os.environ.get('PETCAR_WHISPER_MODEL', 'base')})" \
        if voice else ("完整语音" if full else "快速模式")
    # 不传 --flask: 让 main.py 同时跑 Flask 和语音循环, 否则机器人根本不收音
    args = f"--port {port}"

    cmd = (
        f"cd {REMOTE_ROOT} && {env}"
        f"setsid python3 -m petcar.main {args} "
        f"> {LOG_FILE} 2>&1 < /dev/null & disown"
    )
    c.exec_command(cmd, timeout=10)  # 不读取输出, 否则会被后台进程占住
    print(f"[..] 启动中 (端口 {port}, {mode})")

    ok = False
    for i in range(120):   # whisper 模型加载可能超过 60s
        time.sleep(1)
        code = sh(c, f"curl -s -o /dev/null -w '%{{http_code}}' http://127.0.0.1:{port}/")
        if code == "200":
            ok = True
            break
        if i > 20 and not is_running(c):
            break

    if ok:
        print(f"[OK] 已启动 → http://{HOST}:{port}/")
        print(f"     积木编程 → http://{HOST}:{port}/blocks")
    elif is_running(c):
        # whisper 首次加载可能超过等待时间, 进程还活着就不是失败
        print(f"[..] 进程已启动, Web 尚未就绪 (模型加载较慢), 稍等再访问 http://{HOST}:{port}/")
        print(sh(c, f"tail -n 20 {LOG_FILE}"))
    else:
        print("[FAIL] 启动失败, 最近日志:")
        print(sh(c, f"tail -n 40 {LOG_FILE}"))


def tail(c, lines: int = 40) -> None:
    print(sh(c, f"tail -n {lines} {LOG_FILE}"))


def push() -> None:
    print("[..] 推送代码 (deploy_petcar.py push)")
    code = subprocess.call([sys.executable, os.path.join(LOCAL_ROOT, "deploy_petcar.py"), "push"],
                           cwd=LOCAL_ROOT)
    if code != 0:
        sys.exit(code)


def main() -> None:
    p = argparse.ArgumentParser(description="AI-PetCar 一键启动")
    p.add_argument("--port", type=int, default=5000, help="Web 端口, 默认 5000")
    p.add_argument("--full", action="store_true", help="加载真实 ASR (whisper small, 较慢)")
    p.add_argument("--voice", action="store_true", help="开启麦克风语音对话 (whisper base)")
    p.add_argument("--rules", action="store_true",
                   help="回复走本地规则 (不用 LLM, 秒回, 适合指令控制)")
    p.add_argument("--offline", action="store_true",
                   help="语音改用本地离线童声 (piper), 不依赖外网")
    p.add_argument("--push", action="store_true", help="启动前先推送代码")
    p.add_argument("--restart", action="store_true", help="先停止再启动")
    p.add_argument("--stop", action="store_true", help="停止板上进程")
    p.add_argument("--logs", action="store_true", help="查看最近日志")
    args = p.parse_args()

    if args.push:
        push()
        args.restart = True  # 推了新代码就必须重启, 否则跑的还是旧代码

    if args.rules:
        os.environ["PETCAR_LLM_BACKEND"] = "mock"

    c = connect()
    try:
        # 保证板端启动脚本可执行（Windows 提交的文件默认没有 +x）
        sh(c, f"chmod +x {REMOTE_ROOT}/petcar/start.sh 2>/dev/null || true")
        if args.stop:
            stop(c)
            return
        if args.logs:
            tail(c)
            return
        if args.restart:
            stop(c, quiet=True)
        elif is_running(c):
            print(f"[OK] 已在运行 → http://{HOST}:{args.port}/  (要重启请加 --restart)")
            return
        start(c, args.port, args.full, args.voice, args.offline)
    finally:
        c.close()


if __name__ == "__main__":
    main()
