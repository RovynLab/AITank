#!/usr/bin/env bash
# ============================================================================
# install_petcar.sh — AI-PetCar 树莓派一键安装脚本
# ----------------------------------------------------------------------------
# 在树莓派上执行（不是开发机）：
#   cd ~/AITank && bash install_petcar.sh
#   bash install_petcar.sh --skip-deps    # 只重新配置扬声器音量
#
# 完成的步骤：
#   1. 安装系统依赖（espeak / ALSA / PortAudio / libsndfile）
#   2. 安装 Python 依赖（petcar/requirements.txt）
#   3. 配置 USB 扬声器音量：硬件混音器拉满 + 软件过载，并开机自动生效
#      （本机喇叭为单声道，左右声道都推满即可，无需特殊下混）
#
# 软件过载倍数可用环境变量覆盖：
#   PETCAR_AUDIO_GAIN=1.5 bash install_petcar.sh --skip-deps
# ============================================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOFT_GAIN="${PETCAR_AUDIO_GAIN:-2.0}"
SKIP_DEPS=0
[ "${1:-}" = "--skip-deps" ] && SKIP_DEPS=1

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

info() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[警告] %s\033[0m\n' "$*"; }

# ----------------------------------------------------------------------------
# 1. 系统依赖
# ----------------------------------------------------------------------------
if [ "$SKIP_DEPS" -eq 0 ]; then
    info "检查系统依赖"
    APT_PKGS=(espeak alsa-utils libportaudio2 libsndfile1)
    missing=()
    for p in "${APT_PKGS[@]}"; do
        dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p")
    done
    if [ ${#missing[@]} -gt 0 ]; then
        info "安装系统依赖: ${missing[*]}"
        sudo apt-get update -qq && sudo apt-get install -y "${missing[@]}" \
            || warn "系统依赖安装失败，请手动执行: sudo apt-get install -y ${missing[*]}"
    else
        echo "  依赖已齐全"
    fi

    # ------------------------------------------------------------------------
    # 2. Python 依赖
    # ------------------------------------------------------------------------
    info "安装 Python 依赖 (petcar/requirements.txt)"
    pip3 install --break-system-packages -q -r "$ROOT/petcar/requirements.txt" \
        || warn "部分 Python 依赖安装失败，请查看上面的报错（mediapipe 在部分板卡上装不上属正常）"
fi

# ----------------------------------------------------------------------------
# 3. 扬声器音量
# ----------------------------------------------------------------------------
info "配置 USB 扬声器音量"

AUDIO_HELPER="$HOME/.local/bin/audio-max-volume.sh"
AUDIO_SERVICE="$HOME/.config/systemd/user/audio-max-volume.service"

mkdir -p "$(dirname "$AUDIO_HELPER")" "$(dirname "$AUDIO_SERVICE")"

cat > "$AUDIO_HELPER" <<'EOS'
#!/usr/bin/env bash
# audio-max-volume.sh — 把 USB 扬声器音量拉到最大
# 用法: audio-max-volume.sh [软件增益倍数]   默认 2.0
#   硬件混音器先拉到 100%，硬件到顶后再叠加软件增益
GAIN="${1:-2.0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

# 等 PipeWire 就绪
for _ in $(seq 1 40); do
    wpctl status >/dev/null 2>&1 && break
    sleep 0.5
done

# 找 USB 音频输出设备（node.name 含 alsa_output.usb）
sink_id=""
for _ in $(seq 1 60); do
    sink_id=$(wpctl status -n 2>/dev/null \
        | sed -n '/Sinks:/,/Sources:/p' \
        | grep 'alsa_output\.usb' \
        | sed -E 's/^[^0-9]*([0-9]+)\..*/\1/' | head -1)
    [ -n "$sink_id" ] && break
    sleep 1
done

if [ -z "$sink_id" ]; then
    echo "[audio] 未找到 USB 音频输出设备，跳过音量设置"
    exit 0
fi

# 1) 硬件混音器拉满（不同声卡控件名不一样，逐个尝试）
card=$(wpctl inspect "$sink_id" 2>/dev/null \
       | sed -n 's/.*alsa\.card = "\([0-9]*\)".*/\1/p' | head -1)
if [ -n "$card" ]; then
    for ctl in PCM Speaker Master Headphone; do
        amixer -c "$card" sset "$ctl" 100% unmute >/dev/null 2>&1
    done
fi

# 2) 系统音量 100%
wpctl set-volume "$sink_id" 1.0 >/dev/null 2>&1

# 3) 软件过载：硬件已到顶，再往上只能靠软增益
ch=$(wpctl inspect "$sink_id" 2>/dev/null \
     | sed -n 's/.*audio\.channels = "\([0-9]*\)".*/\1/p' | head -1)
ch="${ch:-2}"
vols=""
for _ in $(seq 1 "$ch"); do vols="$vols $GAIN"; done
pw-cli s "$sink_id" Props "{ softVolumes: [$vols ] }" >/dev/null 2>&1

echo "[audio] USB 扬声器已设为最大音量 (声卡 ${card:-?}, 声道 $ch, 软增益 ${GAIN}x)"
EOS

chmod +x "$AUDIO_HELPER"

cat > "$AUDIO_SERVICE" <<EOS
[Unit]
Description=Set USB speaker volume to maximum
After=pipewire.service pipewire-pulse.service wireplumber.service
Wants=pipewire.service

[Service]
Type=oneshot
ExecStart=%h/.local/bin/audio-max-volume.sh $SOFT_GAIN
RemainAfterExit=yes

[Install]
WantedBy=default.target
EOS

if command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload
    systemctl --user enable audio-max-volume.service >/dev/null 2>&1 \
        || warn "systemd 用户服务启用失败，音量需手动执行 $AUDIO_HELPER"
    systemctl --user restart audio-max-volume.service >/dev/null 2>&1
    echo "  开机自启服务: audio-max-volume.service ($(systemctl --user is-enabled audio-max-volume.service 2>/dev/null))"
else
    warn "没有 systemctl，音量设置需手动执行 $AUDIO_HELPER"
fi

# 立即生效一次并回显结果
"$AUDIO_HELPER" "$SOFT_GAIN"

info "安装完成"
echo "  启动面板: python3 -m petcar.main --flask --port 5000"
echo "  全功能  : python3 -m petcar.main"
echo "  音量微调: PETCAR_AUDIO_GAIN=1.5 bash install_petcar.sh --skip-deps"
