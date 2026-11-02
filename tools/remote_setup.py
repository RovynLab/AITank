"""
AITank 树莓派远程部署脚本
========================
用法: python remote_setup.py [mode]
  probe   - 采集系统信息 (默认)
  key     - 写入本机公钥实现免密
  sys     - 安装系统依赖 + 开启I2C
  deps    - 安装 Python 依赖
  push    - 推送 AITank 代码
  hwtest  - 硬件检测 (i2cdetect)
  run     - 跑实验
  all     - 一键全套: probe → key → sys → deps → push → hwtest

前提: pip install paramiko scp
"""

import sys, os, time, subprocess, json
from pathlib import Path

# ---------- 连接参数 ----------
HOST = "192.168.0.100"
USER = "pi"
PASS = "raspberry"
PROJECT_LOCAL = r"e:\work\AITank"
PROJECT_REMOTE = "/home/pi/AITank"

# ---------- 工具函数 ----------
def ssh_connect():
    import paramiko
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASS, timeout=10, auth_timeout=10)
    print(f"[OK] SSH 已连接 {USER}@{HOST}")
    return client

def run(client, cmd, sudo=False, timeout=60, check=True):
    """执行远程命令，sudo=True 时自动加 -S 喂密码"""
    if sudo:
        cmd = f"echo '{PASS}' | sudo -S {cmd}"
    print(f"\n$ {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    code = stdout.channel.recv_exit_status()
    if out: print(out)
    if err and code != 0: print(f"[STDERR] {err}")
    if check and code != 0:
        print(f"[WARN] 退出码 {code}")
    return code, out, err

def scp_push(client, local_path, remote_path):
    """推文件/目录到远端"""
    from scp import SCPClient
    sftp = client.open_sftp()
    scp = SCPClient(sftp.get_transport(), socket_timeout=30)
    try:
        if os.path.isdir(local_path):
            scp.put(local_path, remote_path, recursive=True)
            print(f"[OK] 目录推送: {local_path} → {remote_path}")
        else:
            scp.put(local_path, remote_path)
            print(f"[OK] 文件推送: {local_path} → {remote_path}")
    finally:
        scp.close()

# ---------- 各步骤 ----------
def step_probe(client):
    print("\n" + "="*60)
    print("[1/7] 系统信息采集")
    print("="*60)
    cmds = {
        "HOSTNAME":  "hostname",
        "OS":        "cat /etc/os-release | grep PRETTY_NAME",
        "ARCH":      "uname -m",
        "PYTHON":    "python3 --version",
        "PIP":       "pip3 --version",
        "I2C_MOD":   "lsmod | grep i2c || echo 'NO_I2C_MOD'",
        "DEV_I2C":   "ls /dev/i2c* 2>/dev/null || echo 'NO_DEV_I2C'",
        "FREE_MEM":  "free -h | head -2",
        "DISK":      "df -h / | tail -1",
        "GPIO":      "ls -l /dev/gpiochip* 2>/dev/null || echo 'NO_GPIOCHIP'",
    }
    for k, c in cmds.items():
        _, out, _ = run(client, c, check=False)
        print(f"  {k:10s}: {out}")

def step_key(client):
    print("\n" + "="*60)
    print("[2/7] 写入 SSH 公钥实现免密")
    print("="*60)
    pubkey_path = os.path.expanduser(r"~/.ssh/id_ed25519.pub")
    if not os.path.exists(pubkey_path):
        print("[SKIP] 未找到本机公钥，跳过")
        return
    with open(pubkey_path) as f:
        pubkey = f.read().strip()
    run(client, f"mkdir -p ~/.ssh && chmod 700 ~/.ssh", check=False)
    # 检查是否已存在
    _, out, _ = run(client, f"grep -c '{pubkey[:30]}' ~/.ssh/authorized_keys 2>/dev/null || echo 0", check=False)
    if out.strip() == "0":
        run(client, f"echo '{pubkey}' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys")
        print("[OK] 公钥已写入，下次 SSH 免密")
    else:
        print("[SKIP] 公钥已存在")

def step_sys(client):
    print("\n" + "="*60)
    print("[3/7] 系统依赖 + 开启 I2C")
    print("="*60)
    # 开 I2C (raspi-config 非交互方式)
    run(client, "raspi-config nonint do_i2c 0", sudo=True, check=False)
    # apt update + 装包
    pkgs = "i2c-tools python3-smbus python3-pip python3-numpy python3-venv libatlas-base-dev libhdf5-dev libjpeg-dev libpng-dev"
    run(client, "apt-get update -y", sudo=True, timeout=120)
    run(client, f"apt-get install -y {pkgs}", sudo=True, timeout=180)
    # 重启 i2c 模块
    run(client, "modprobe i2c-dev && modprobe i2c-bcm2835", sudo=True, check=False)
    # 验证
    run(client, "ls /dev/i2c*", check=False)
    _, out, _ = run(client, "raspi-config nonint get_i2c", check=False)
    print(f"  I2C 状态: {'已开启' if '0' in out else '未开启'}")

def step_deps(client):
    print("\n" + "="*60)
    print("[4/7] Python 依赖安装")
    print("="*60)
    # 先升级 pip
    run(client, "pip3 install --upgrade pip setuptools wheel", timeout=60, check=False)
    # RPi.GPIO
    run(client, "pip3 install RPi.GPIO", timeout=60, check=False)
    # opencv headless (树莓派上装不带 GUI 的版本，省空间)
    run(client, "pip3 install opencv-python-headless imutils", timeout=120, check=False)
    # Flask + Werkzeug
    run(client, "pip3 install Flask Werkzeug", timeout=60, check=False)
    # pygame (无头模式需要 SDL)
    run(client, "pip3 install pygame", timeout=60, check=False)
    # getkey + Pillow
    run(client, "pip3 install getkey Pillow", timeout=60, check=False)
    # MediaPipe 可选
    print("  [INFO] MediaPipe 需要额外 wheel，暂时跳过（AI 实验时再装）")
    # 验证关键包
    run(client, "python3 -c 'import cv2; print(f\"  OpenCV {cv2.__version__}\")'", check=False)
    run(client, "python3 -c 'import RPi.GPIO as GPIO; print(\"  RPi.GPIO OK\")'", check=False)
    run(client, "python3 -c 'import smbus; print(\"  smbus OK\")'", check=False)

def step_push(client):
    print("\n" + "="*60)
    print("[5/7] 推送 AITank 代码")
    print("="*60)
    run(client, f"mkdir -p {PROJECT_REMOTE}")
    # 推送核心目录和文件
    items = [
        "config.py",
        "requirements.txt",
        "deps",
        "labs",
        "demos",
        "ai",
        "core",
        "student_api",
    ]
    for item in items:
        local = os.path.join(PROJECT_LOCAL, item)
        remote = f"{PROJECT_REMOTE}/{item}"
        if os.path.exists(local):
            # 如果远端已存在，先删再推（省得 scp 覆盖目录出问题）
            run(client, f"rm -rf {remote}", check=False)
            scp_push(client, local, f"{PROJECT_REMOTE}/")
    run(client, f"ls -la {PROJECT_REMOTE}/")

def step_hwtest(client):
    print("\n" + "="*60)
    print("[6/7] 硬件检测 —— I2C 设备扫描")
    print("="*60)
    run(client, "i2cdetect -y 1", sudo=True, check=False)
    # PCA9685 回读测试 (0x60)
    _, out, _ = run(client, "i2cget -y 1 0x60 0x00", sudo=True, check=False)
    print(f"  PCA9685 MODE1 @0x00: {out.strip()} (期望 0x00)")

def step_run(client):
    print("\n" + "="*60)
    print("[7/7] 冒烟测试 —— lab01 LED 闪烁")
    print("="*60)
    run(client, f"cd {PROJECT_REMOTE} && timeout 5 python3 labs/lab01_led_blink.py 2>&1 || true", timeout=15, check=False)

# ---------- main ----------
STEPS = {
    "probe": step_probe,
    "key":   step_key,
    "sys":   step_sys,
    "deps":  step_deps,
    "push":  step_push,
    "hwtest":step_hwtest,
    "run":   step_run,
}

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    client = ssh_connect()
    try:
        if mode == "all":
            for s in ["probe", "key", "sys", "deps", "push", "hwtest"]:
                STEPS[s](client)
            print("\n" + "="*60)
            print("✅ 全部完成！现在可以手动跑:")
            print(f"   ssh {USER}@{HOST}")
            print(f"   cd {PROJECT_REMOTE}")
            print(f"   python3 labs/lab01_led_blink.py   # LED 闪烁")
            print(f"   python3 labs/lab05_wheel_test.py  # 轮组测试")
            print("="*60)
        elif mode in STEPS:
            STEPS[mode](client)
        else:
            print(f"未知 mode: {mode}")
            print(f"可选: {list(STEPS.keys()) + ['all']}")
    finally:
        client.close()
        print("\n[SSH] 已断开")

if __name__ == "__main__":
    main()
