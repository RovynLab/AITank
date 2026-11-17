#!/bin/bash
# aitank-menu 一键部署脚本
# 在板子上执行: bash ~/aitank-menu-deploy/deploy.sh
# 需要 sudo 密码（默认 raspberry，如不对会报错）

set -e
cd "$HOME/aitank-menu-deploy"

SUDO_PASS="${1:-raspberry}"

echo "=== 1. 安装 evdev（如果还没） ==="
pip3 install --break-system-packages evdev 2>&1 | tail -2 || true

echo "=== 2. 配置 polkit nmcli 免密码 ==="
echo "$SUDO_PASS" | sudo -S mkdir -p /etc/polkit-1/localauthority/50-local.d/
echo "$SUDO_PASS" | sudo -S cp 45-aitank-nm.pkla /etc/polkit-1/localauthority/50-local.d/
echo "$SUDO_PASS" | sudo -S chmod 644 /etc/polkit-1/localauthority/50-local.d/45-aitank-nm.pkla

echo "=== 3. 让 NetworkManager 托管 eth0/wlan0 ==="
echo "$SUDO_PASS" | sudo -S nmcli device set eth0 managed yes 2>/dev/null || true
echo "$SUDO_PASS" | sudo -S nmcli device set wlan0 managed yes 2>/dev/null || true
echo "$SUDO_PASS" | sudo -S systemctl restart NetworkManager

echo "=== 4. 安装 systemd service ==="
echo "$SUDO_PASS" | sudo -S cp aitank-menu.service /etc/systemd/system/
echo "$SUDO_PASS" | sudo -S daemon-reload
echo "$SUDO_PASS" | sudo -S enable aitank-menu

echo ""
echo "=== 部署完成 ==="
echo ""
echo "手动启动（调试用，看日志）："
echo "  sudo systemctl start aitank-menu"
echo "  sudo journalctl -u aitank-menu -f"
echo ""
echo "先别急着 enable——建议先上面手动 start 看 OLED 和键盘能不能用，确认 OK 再 enable 开机自启"
