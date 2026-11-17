#!/usr/bin/env bash
# =============================================================================
# petcar/start.sh — AI Tank / PetCar 板端启动脚本
# -----------------------------------------------------------------------------
# 放在 petcar 根目录，SSH 登录树莓派后直接使用：
#
#   ./petcar/start.sh                  # 启动（面板 + 完整语音交互）
#   ./petcar/start.sh --voice          # 启动并开启语音对话（whisper base）
#   ./petcar/start.sh --full           # 完整语音链路（whisper 使用配置默认模型）
#   ./petcar/start.sh --voice --offline # 语音 + 本地 Piper 离线童声
#   ./petcar/start.sh --port 5001      # 指定端口
#
#   ./petcar/start.sh status           # 查看运行状态
#   ./petcar/start.sh logs             # 查看最近 80 行日志
#   ./petcar/start.sh logs -f          # 实时跟踪日志
#   ./petcar/start.sh restart          # 重启
#   ./petcar/start.sh stop             # 停止
#   ./petcar/start.sh foreground       # 前台运行（调试用，Ctrl+C 退出）
#
# 说明：
#   - 必须在仓库根目录的上一级能找到 petcar 包，即 ~/AITank/petcar；
#   - 日志写入 petcar/logs/petcar.log，PID 写入 petcar/logs/petcar.pid；
#   - 用 setsid 脱离 SSH 会话，退出 SSH 后进程继续运行；
#   - 重复执行 start 不会启动第二个实例，会直接提示已在运行；
#   - 注意：面板保存的 data/config_local.json 优先级高于本脚本设置的环境变量，
#     若面板里保存过 llm_backend / tts_mode，对应配置会以面板配置为准；
#     需要让本脚本的 --offline 生效时，先在面板「恢复默认」
#     或删除 data/config_local.json。详见 docs/进程与启动控制.md。
# =============================================================================

set -u

# ---------- 路径 ----------
PETCAR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$PETCAR_DIR")"
LOG_DIR="$PETCAR_DIR/logs"
LOG_FILE="$LOG_DIR/petcar.log"
PID_FILE="$LOG_DIR/petcar.pid"
PROC_PATTERN="[p]etcar.main"

# ---------- 默认参数 ----------
ACTION="start"
MODE="full"          # voice | full
OFFLINE=0
PORT="${PETCAR_PORT:-5000}"
WHISPER_URL="${PETCAR_WHISPER_URL:-http://127.0.0.1:8091}"

usage() {
    cat <<'EOF'
用法: ./petcar/start.sh [命令] [选项]

命令:
  start        启动（默认）
  stop         停止
  restart      重启
  status       查看运行状态
  logs [-f]    查看最近 80 行日志（-f 实时跟踪）
  foreground   前台运行，调试用，Ctrl+C 退出

选项:
  --voice      开启语音对话（whisper base，启动较慢）
  --full       完整语音链路（whisper 使用配置默认模型，默认行为）
  --offline    语音合成改用本地 Piper，不依赖外网
  --port N     指定 Web 端口，默认 5000
  -h, --help   显示本帮助

示例:
  ./petcar/start.sh --voice
  ./petcar/start.sh restart --port 5000
  ./petcar/start.sh logs -f
EOF
}

# ---------- 解析参数 ----------
if [ $# -gt 0 ]; then
    case "$1" in
        start|stop|restart|status|logs|foreground) ACTION="$1"; shift ;;
        -h|--help) usage; exit 0 ;;
        --*) : ;;
        *) echo "未知命令: $1"; echo; usage; exit 1 ;;
    esac
fi

while [ $# -gt 0 ]; do
    case "$1" in
        --port) PORT="${2:-}"; shift 2 || shift ;;
        --voice) MODE="voice"; shift ;;
        --full) MODE="full"; shift ;;
        --offline) OFFLINE=1; shift ;;
        -f|--follow) FOLLOW=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "未知参数: $1"; echo; usage; exit 1 ;;
    esac
done

case "$PORT" in
    ''|*[!0-9]*) echo "[FAIL] 端口无效: ${PORT}"; exit 1 ;;
esac

mkdir -p "$LOG_DIR"

# ---------- 工具 ----------
find_pids() {
    # 优先用 PID 文件；PID 失效时回退到进程名匹配
    local pids=""
    if [ -f "$PID_FILE" ]; then
        local p
        p="$(cat "$PID_FILE" 2>/dev/null || true)"
        # 除了进程存在，还要确认它确实是 petcar，避免 PID 被系统复用后误杀
        if [ -n "${p}" ] && kill -0 "$p" 2>/dev/null \
           && tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q "petcar.main"; then
            pids="$p"
        fi
    fi
    if [ -z "$pids" ]; then
        pids="$(pgrep -f "$PROC_PATTERN" 2>/dev/null | tr '\n' ' ' || true)"
    fi
    echo "$pids"
}

is_running() {
    [ -n "$(find_pids)" ]
}

http_code() {
    if command -v curl >/dev/null 2>&1; then
        curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}/" 2>/dev/null || true
    else
        echo "---"
    fi
}

board_ip() {
    hostname -I 2>/dev/null | awk '{print $1}'
}

# ---------- 等 whisper_service ----------
wait_whisper_service() {
    # whisper_service 开机预加载模型约 60s, 等它 ready 再启动 petcar
    local ready=0
    local url="$WHISPER_URL/health"
    echo "[..] 等待 whisper_service 就绪 (最长 120s)..."
    for _ in $(seq 1 60); do
        local code body
        code=$(curl -s -o /tmp/_whisper_health.json -w '%{http_code}' "$url" 2>/dev/null || echo "000")
        if [ "$code" = "200" ] && grep -q '"ok".*true.*"loaded".*true' /tmp/_whisper_health.json 2>/dev/null; then
            ready=1
            break
        fi
        sleep 2
    done
    if [ "$ready" = "1" ]; then
        echo "[OK] whisper_service ready"
    else
        echo "[!] whisper_service 未就绪, petcar 继续启动但 ASR 可能不可用"
        echo "    查看: sudo systemctl status aitank-whisper"
    fi
    rm -f /tmp/_whisper_health.json
}

# ---------- 停止 ----------
do_stop() {
    local pids
    pids="$(find_pids)"
    if [ -z "$pids" ]; then
        echo "[..] petcar 未在运行"
        rm -f "$PID_FILE"
        return 0
    fi

    echo "[..] 停止 petcar (PID: $pids)"
    # shellcheck disable=SC2086
    kill -TERM $pids 2>/dev/null || true
    for _ in $(seq 1 20); do
        if ! is_running; then
            echo "[OK] 已停止"
            rm -f "$PID_FILE"
            return 0
        fi
        sleep 0.5
    done

    echo "[..] 进程未响应，强制结束"
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
    sleep 0.3
    rm -f "$PID_FILE"
    echo "[OK] 已强制停止"
}

# ---------- 启动 ----------
build_env() {
    ENV="PYTHONUNBUFFERED=1"
    ENV="$ENV PETCAR_LLM_BACKEND=${PETCAR_LLM_BACKEND:-ollama}"
    ENV="$ENV PETCAR_WHISPER_URL=${WHISPER_URL}"

    case "$MODE" in
        voice)
            # 语音对话：base 模型在 2GB 内存板上更稳；模型下载走国内镜像
            ENV="$ENV PETCAR_WHISPER_MODEL=${PETCAR_WHISPER_MODEL:-base}"
            ENV="$ENV HF_ENDPOINT=${HF_ENDPOINT:-https://hf-mirror.com}"
            ;;
        full)
            # 完整模式：whisper 模型与麦克风配置沿用 config / 环境变量
            ;;
    esac

    if [ "$OFFLINE" = "1" ]; then
        ENV="$ENV PETCAR_TTS_MODE=${PETCAR_TTS_MODE:-piper}"
    fi
}

do_start() {
    if is_running; then
        echo "[OK] petcar 已在运行 (PID: $(find_pids))"
        echo "     面板   → http://$(board_ip):${PORT}/"
        echo "     积木   → http://$(board_ip):${PORT}/blocks"
        echo "     重启请执行: $0 restart"
        return 0
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        echo "[FAIL] 找不到 python3"
        return 1
    fi

    build_env
    wait_whisper_service

    echo "[..] 启动 petcar (模式: $MODE, 端口: $PORT)"
    cd "$ROOT_DIR" || return 1

    # shellcheck disable=SC2086
    if command -v setsid >/dev/null 2>&1; then
        setsid env $ENV python3 -m petcar.main --port "$PORT" \
            >> "$LOG_FILE" 2>&1 < /dev/null &
    else
        # 没有 setsid 时用 nohup 兜底，同样能在退出 SSH 后继续运行
        nohup env $ENV python3 -m petcar.main --port "$PORT" \
            >> "$LOG_FILE" 2>&1 < /dev/null &
    fi
    sleep 0.5

    local pid
    pid="$(find_pids)"
    if [ -z "$pid" ]; then
        # setsid 可能 fork，$! 不一定是 python 的真实 PID，再等一次
        sleep 1
        pid="$(find_pids)"
    fi
    if [ -n "$pid" ]; then
        echo "$pid" | awk '{print $1}' > "$PID_FILE"
    else
        echo "[FAIL] 进程未能启动，最近日志："
        tail -n 40 "$LOG_FILE" 2>/dev/null || true
        return 1
    fi

    echo "[..] 等待 Web 就绪（首次加载模型可能较慢）..."
    local ready=0
    for _ in $(seq 1 90); do
        if [ "$(http_code)" = "200" ]; then
            ready=1
            break
        fi
        if ! kill -0 "$(cat "$PID_FILE" 2>/dev/null)" 2>/dev/null; then
            break
        fi
        sleep 1
    done

    if [ "$ready" = "1" ]; then
        echo "[OK] 已启动 → http://$(board_ip):${PORT}/"
        echo "     积木编程 → http://$(board_ip):${PORT}/blocks"
    else
        if kill -0 "$(cat "$PID_FILE" 2>/dev/null)" 2>/dev/null; then
            echo "[..] 进程已启动，Web 尚未就绪（可能在加载模型）"
            echo "     稍后访问 http://$(board_ip):${PORT}/，或查看: $0 logs -f"
        else
            echo "[FAIL] 启动失败，最近日志："
            tail -n 40 "$LOG_FILE" 2>/dev/null || true
            rm -f "$PID_FILE"
            return 1
        fi
    fi
    return 0
}

# ---------- 状态 ----------
do_status() {
    local pids
    pids="$(find_pids)"
    if [ -z "$pids" ]; then
        echo "状态: 未运行"
        return 1
    fi
    echo "状态: 运行中"
    echo "PID : $pids"
    echo "端口: $PORT  HTTP=$(http_code)"
    echo "日志: $LOG_FILE"
    if command -v ps >/dev/null 2>&1; then
        # shellcheck disable=SC2086
        ps -o pid=,etime=,rss=,args= -p $pids 2>/dev/null || true
    fi
    echo "访问: http://$(board_ip):${PORT}/"
}

# ---------- 日志 ----------
do_logs() {
    if [ ! -f "$LOG_FILE" ]; then
        echo "[..] 还没有日志文件: $LOG_FILE"
        return 1
    fi
    if [ "${FOLLOW:-0}" = "1" ]; then
        tail -n 80 -f "$LOG_FILE"
    else
        tail -n 80 "$LOG_FILE"
    fi
}

# ---------- 前台运行 ----------
do_foreground() {
    if is_running; then
        echo "[FAIL] 已有 petcar 在运行，请先执行: $0 stop"
        return 1
    fi
    build_env
    cd "$ROOT_DIR" || return 1
    echo "[..] 前台运行 (Ctrl+C 退出)"
    # shellcheck disable=SC2086
    exec env $ENV python3 -m petcar.main --port "$PORT"
}

# ---------- 分发 ----------
case "$ACTION" in
    start)      do_start ;;
    stop)       do_stop ;;
    restart)    do_stop; do_start ;;
    status)     do_status ;;
    logs)       do_logs ;;
    foreground) do_foreground ;;
    *)          usage; exit 1 ;;
esac
