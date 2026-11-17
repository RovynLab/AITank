"""
network_manager.py — 网络状态查询与 WiFi 连接
===============================================

封装 nmcli 和 ip 命令，提供：
- get_status()   → WiFi/有线 连接状态 + SSID + IP
- scan_wifi()    → 扫描可用 WiFi 列表
- connect_wifi() → 用密码连接指定 WiFi
- disconnect()   → 断开连接

所有命令走 subprocess.check_output，避免 shell 注入。
"""

from __future__ import annotations

import json
import os
import subprocess
import shutil
import re
import time
from typing import Optional


# ============ 默认 WiFi（出厂配置） ============
DEFAULT_SSID = "eserc"
DEFAULT_PASS = "loongson@eserc"

# "上次成功连接 WiFi" 的持久化文件
# 放在用户 home 下，aitank-menu 以 pi 用户运行，有写权限
_LAST_WIFI_FILE = os.path.expanduser("~/.aitank_last_wifi.json")


def _run(cmd: list, timeout: int = 10) -> tuple[int, str, str]:
    """执行命令，返回 (exit_code, stdout, stderr)
    
    nmcli 连接 WiFi 需要 root 权限。
    策略：先直接跑 → 如果被拒绝（Not authorized / Insufficient privileges）→ sudo -n fallback。
    sudo -n 在板子上已配置 NOPASSWD。
    """
    try:
        # 先直接跑（polkit pkla 应该能放行）
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            check=False
        )
        err = (result.stderr or "").lower() + " " + (result.stdout or "").lower()
        # polkit 拒绝的典型错误字符串（polkit>=121 已不支持 .pkla，非 root 常被拒）
        auth_fail = (
            "not authorized" in err
            or "insufficient privileges" in err
            or "not permitted" in err
            or "authorization failed" in err
            or "scanning not allowed" in err
            or "permission denied" in err
        )
        if result.returncode != 0 and auth_fail:
            result2 = subprocess.run(
                ["sudo", "-n"] + cmd,
                capture_output=True, text=True, timeout=timeout,
                check=False
            )
            return result2.returncode, result2.stdout.strip(), result2.stderr.strip()
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def has_nmcli() -> bool:
    """检测 nmcli 是否存在"""
    return shutil.which("nmcli") is not None


def has_nm() -> bool:
    """检测 NetworkManager 是否运行"""
    if not has_nmcli():
        return False
    rc, _, _ = _run(["nmcli", "-t", "-g", "running", "general", "status"])
    return rc == 0


# ============ 状态查询 ============

def get_status() -> dict:
    """
    返回网络状态字典：
    {
        "wifi":       "connected" | "disconnected" | "unavailable" | None,
        "wifi_ssid":  str | "",
        "wifi_ip":    str | "",
        "eth":        "connected" | "disconnected" | "unavailable" | None,
        "eth_ip":     str | "",
    }
    """
    result = {
        "wifi": None, "wifi_ssid": "", "wifi_ip": "",
        "eth": None, "eth_ip": "",
    }

    if not has_nmcli():
        result["wifi"] = "unavailable"
        result["eth"] = "unavailable"
        return result

    # nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device status
    rc, out, _ = _run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"])
    if rc != 0:
        result["wifi"] = "unavailable"
        result["eth"] = "unavailable"
        return result

    eth_dev = "eth0"

    for line in out.split("\n"):
        # 格式: wlan0:wifi:connected:MyHome
        #       eth0:ethernet:connected:wired
        parts = line.split(":")
        if len(parts) < 4:
            continue
        dev, dtype, state, conn = parts[0], parts[1], parts[2], parts[3]

        if dtype == "wifi":
            if state == "connected":
                result["wifi"] = "connected"
                result["wifi_ssid"] = conn
            elif state in ("disconnected", "unmanaged"):
                result["wifi"] = "disconnected"
            else:
                result["wifi"] = state
        elif dtype == "ethernet":
            eth_dev = dev
            if state == "connected":
                result["eth"] = "connected"
            elif state in ("disconnected", "unmanaged"):
                result["eth"] = "disconnected"
            else:
                result["eth"] = state

    # 网线热插拔：NetworkManager 掉线检测有延迟，可能仍报 connected。
    # 直接读 /sys/class/net/ethX/carrier 作为物理链路真相，拔线立刻置为断开。
    if _link_up(eth_dev) is False:
        result["eth"] = "disconnected"

    # 查 IP 地址
    for dev_key, ip_key in [("wlan0", "wifi_ip"), ("eth0", "eth_ip")]:
        ip = _get_ip(dev_key)
        if ip:
            result[ip_key] = ip

    # WiFi 信号强度 + MAC
    result["wifi_signal"] = _get_wifi_signal()
    result["wifi_mac"] = _get_mac("wlan0")
    result["eth_mac"] = _get_mac("eth0")

    # 网关 + DNS
    result["gateway"] = _get_default_gw()
    result["dns"] = _get_dns()

    # 系统运行时间（秒）
    try:
        with open("/proc/uptime") as f:
            result["uptime_sec"] = int(float(f.read().split()[0]))
    except Exception:
        result["uptime_sec"] = 0

    return result


def _link_up(iface: str) -> Optional[bool]:
    """读 /sys/class/net/<iface>/carrier 判断物理链路（网线是否插着）

    True=链路通，False=断开，None=读不到（回落到 nmcli 结果）
    """
    try:
        with open(f"/sys/class/net/{iface}/carrier") as f:
            return f.read().strip() == "1"
    except Exception:
        return None


def _get_mac(iface: str) -> str:
    try:
        with open(f"/sys/class/net/{iface}/address") as f:
            return f.read().strip()[:17]
    except Exception:
        return ""


def _get_wifi_signal() -> int:
    rc, out, _ = _run(["nmcli", "-t", "-f", "SIGNAL", "device", "wifi"])
    if rc == 0 and out.strip():
        try:
            return int(out.strip())
        except ValueError:
            pass
    return 0


def _get_default_gw() -> str:
    rc, out, _ = _run(["ip", "-o", "route", "show", "default"])
    if rc != 0:
        return ""
    m = re.search(r"via\s+(\d+\.\d+\.\d+\.\d+)", out)
    if m:
        return m.group(1)
    return ""


def _get_dns() -> str:
    try:
        with open("/etc/resolv.conf") as f:
            for line in f:
                m = re.match(r"nameserver\s+(\d+\.\d+\.\d+\.\d+)", line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return ""


def _get_ip(iface: str) -> str:
    """用 ip -o -4 addr show iface 提取 IPv4"""
    rc, out, _ = _run(["ip", "-o", "-4", "addr", "show", iface])
    if rc != 0:
        return ""
    # 匹配 inet 192.168.1.101/24
    m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out)
    if m:
        return m.group(1)
    return ""


# ============ WiFi 扫描 ============

def _is_enterprise(security: str) -> bool:
    """企业级认证（802.1X / EAP，如 eduroam、ECNU-1X）需要账号+证书，菜单不支持"""
    s = (security or "").lower().replace(".", "").replace("-", "")
    return "8021x" in s or "eap" in s


def _parse_scan(out: str) -> list[dict]:
    """解析 nmcli 扫描输出为 AP 列表"""
    aps = []
    for line in out.split("\n"):
        parts = re.split(r"(?<!\\):", line)
        if len(parts) < 3:
            continue
        ssid = parts[0].replace("\\:", ":")
        if not ssid:
            continue  # 隐藏 SSID 跳过
        try:
            signal = int(parts[1])
        except ValueError:
            signal = 0
        security = parts[2] if len(parts) > 2 else ""
        aps.append({
            "ssid": ssid,
            "signal": signal,
            "security": security,
            "enterprise": _is_enterprise(security),
            "in_use": (len(parts) > 3 and parts[3].strip() == "*"),
        })
    return aps


def _dedupe(aps: list[dict]) -> list[dict]:
    """同一 SSID 只留信号最强的一条；已连接的排最前"""
    best: dict[str, dict] = {}
    for ap in aps:
        cur = best.get(ap["ssid"])
        if cur is None or ap["signal"] > cur["signal"]:
            ap["in_use"] = ap["in_use"] or (cur["in_use"] if cur else False)
            best[ap["ssid"]] = ap
        elif ap["in_use"]:
            cur["in_use"] = True
    return sorted(best.values(), key=lambda x: (not x["in_use"], -x["signal"]))


def scan_wifi(refresh: bool = True) -> list[dict]:
    """
    扫描 WiFi，返回去重后的列表（已连接的排第一，其余按信号强度）：
    [{"ssid": "...", "signal": 85, "security": "WPA2", "in_use": True}, ...]

    注意：polkit >= 121 不再支持 .pkla，普通用户 rescan 会被静默拒绝，
    这时 nmcli 只返回缓存（通常只有当前连接的那个 AP），必须走 sudo。
    """
    if not has_nmcli():
        return []

    if refresh:
        _run(["nmcli", "device", "wifi", "rescan"], timeout=12)
        time.sleep(1.5)

    rc, out, _ = _run([
        "nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE",
        "device", "wifi", "list"
    ], timeout=15)
    aps = _parse_scan(out) if rc == 0 else []

    # 结果太少（多半是权限被拒只拿到缓存）→ 用 sudo 重扫一次
    if refresh and len(_dedupe(aps)) < 2:
        _run(["sudo", "-n", "nmcli", "device", "wifi", "rescan"], timeout=12)
        time.sleep(1.5)
        rc2, out2, _ = _run([
            "sudo", "-n", "nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE",
            "device", "wifi", "list"
        ], timeout=15)
        if rc2 == 0:
            aps2 = _parse_scan(out2)
            if len(_dedupe(aps2)) > len(_dedupe(aps)):
                aps = aps2

    return _dedupe(aps)


# ============ 上次成功 WiFi 持久化 ============

def _save_last_wifi(ssid: str, password: str) -> None:
    """保存最近一次成功连接的 WiFi（明文，仅本机可读）"""
    try:
        data = {"ssid": ssid, "password": password}
        fd = os.open(_LAST_WIFI_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[NM] 保存 last_wifi 失败: {e}")


def _load_last_wifi() -> Optional[dict]:
    """读取上次成功连接的 WiFi；文件损坏或不存在返回 None"""
    try:
        with open(_LAST_WIFI_FILE, "r") as f:
            d = json.load(f)
        if isinstance(d, dict) and d.get("ssid"):
            return d
    except Exception:
        pass
    return None


def clear_last_wifi() -> None:
    """清除上次成功 WiFi 记录（用户重置为默认配置时调用）"""
    try:
        if os.path.exists(_LAST_WIFI_FILE):
            os.remove(_LAST_WIFI_FILE)
    except Exception as e:
        print(f"[NM] 清除 last_wifi 失败: {e}")


# ============ 连接/断开 ============

def _delete_profile(ssid: str) -> bool:
    """删除该 SSID 的旧连接配置（旧密码残留会导致换密码后连不上）"""
    rc, out, _ = _run(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"], timeout=10)
    if rc != 0:
        return False
    deleted = False
    for line in out.split("\n"):
        name, _, typ = line.rpartition(":")
        if not name or typ not in ("802-11-wireless", "wifi"):
            continue
        if name == ssid:
            rc2, _, _ = _run(["nmcli", "connection", "delete", name], timeout=15)
            deleted = deleted or rc2 == 0
    return deleted


def connect_wifi(ssid: str, password: str, prefer_5g: bool = True) -> tuple[bool, str]:
    """
    连接指定 WiFi。返回 (成功, 消息)

    - 无密码 WiFi: password="" → 不带 password 参数
    - prefer_5g=True 时先尝试 5GHz band a，失败回退到任意 band
    - 已连着别的 AP 时先断开，否则无线网卡被占用会导致扫描/激活失败
    - 密码类错误 → 删掉旧配置再用新密码重试一次
    - 成功时自动保存到 last_wifi 持久化（供下次开机自动连接）
    """
    if not has_nmcli():
        return False, "nmcli not found"

    # 企业级认证（802.1X）先用密码连只会失败，还会把当前 WiFi 断掉 → 提前拦下
    for ap in scan_wifi(refresh=False):
        if ap["ssid"] == ssid and ap.get("enterprise"):
            return False, "need 802.1X"

    # 0) 先无条件删掉该 SSID 的旧连接配置。
    #    原因：在 NetworkManager 1.52+ (Debian trixie) 上，
    #    "nmcli connection add type wifi con-name X ssid X" 创建的模板会缺少
    #    key-mgmt 字段，而 "nmcli device wifi connect X" 发现已有同名配置时
    #    会先走内部 connection-update 路径，遇到残缺模板就报：
    #      "802-11-wireless-security.key-mgmt: property is missing"
    #    干净环境下 device wifi connect 只会走 connection-add-activate，
    #    自动补齐 key-mgmt / psk 等所有字段，完全不会报错。
    _delete_profile(ssid)

    # 1) 换 AP：先断开当前连接，释放无线网卡
    cur = (get_status().get("wifi_ssid") or "").strip()
    if cur and cur != ssid:
        _run(["nmcli", "device", "disconnect", "wlan0"], timeout=12)
        time.sleep(0.8)

    # 2) 重扫，避免"找不到这个 SSID"的缓存问题
    _run(["nmcli", "device", "wifi", "rescan"], timeout=12)
    time.sleep(1.5)

    # 3) 组装命令。prefer_5g 时先尝试 band a（5GHz），没有 5GHz 的 SSID 会失败，
    #    这时外层循环自动回退到无 band 参数让 NM 自选。
    base = ["nmcli", "device", "wifi", "connect", ssid]
    if password:
        base += ["password", password]

    def _build_cmds() -> list[list]:
        """返回命令尝试序列：先 5G，再任意 band"""
        cmds = []
        if prefer_5g:
            cmds.append(base + ["band", "a"])      # 5GHz 优先
        cmds.append(list(base))                     # 兜底：让 NM 自选
        return cmds

    last_err = ""
    hard_fail = False  # 密码错误等不可恢复错误 → 不要再试后续 band
    for cmd in _build_cmds():
        for attempt in range(3):
            rc, out, err = _run(cmd, timeout=30)
            blob = f"{out} {err}".strip()
            low = blob.lower()

            # nmcli 有时 rc=0 但输出里有 Error:
            if rc == 0 and "error:" not in low:
                # 等 DHCP 拿到 IP（最多 8 秒）
                for _ in range(10):
                    if _get_ip("wlan0"):
                        break
                    time.sleep(0.8)
                # ✅ 标记为 autoconnect：NM 原生机制，下次开机自动连这份配置
                _run(["nmcli", "connection", "modify", ssid,
                      "connection.autoconnect", "yes"], timeout=10)
                # ✅ 持久化：保存到本地文件，供下次开机 auto_connect_on_boot() 优先尝试
                _save_last_wifi(ssid, password)
                return True, f"connected {ssid}"

            last_err = re.sub(r"(?i)^\s*error:\s*", "", blob) or "connect failed"

            if "no network with ssid" in low:
                _run(["sudo", "-n", "nmcli", "device", "wifi", "rescan"], timeout=12)
                time.sleep(2)
                continue

            # 企业级认证（802.1X / EAP）无法用单个密码连接，直接给出明确提示
            if "8021x" in low.replace(".", "").replace("-", ""):
                return False, "need 802.1X"

            if ("secrets" in low or "no-secrets" in low
                    or "psk" in low or "invalid password" in low):
                # 旧配置里可能是错密码 → 删掉重建再试一次
                if attempt == 0:
                    _delete_profile(ssid)
                    time.sleep(0.6)
                    continue
                hard_fail = True
                return False, "bad password"

            if "timed out" in low or "no active connection" in low:
                hard_fail = True
                return False, "timeout"

            hard_fail = True
            return False, last_err[:22]

        # 内层重试耗尽 → 若是硬错误，跳出外层 band 循环直接失败；否则换下一个 band
        if hard_fail:
            break

    return False, (last_err or "failed")[:22]


def disconnect_wifi() -> tuple[bool, str]:
    """断开当前 WiFi"""
    rc, out, err = _run(["nmcli", "device", "disconnect", "wlan0"], timeout=10)
    return rc == 0, (out or err).strip()


def disconnect_eth() -> tuple[bool, str]:
    """断开有线（很少用）"""
    rc, out, err = _run(["nmcli", "device", "disconnect", "eth0"], timeout=10)
    return rc == 0, (out or err).strip()


# ============ 开机自动连接策略 ============

def connect_default_wifi() -> tuple[bool, str]:
    """快捷：连接出厂默认 WiFi (eserc / loongson@eserc)，5G 优先"""
    return connect_wifi(DEFAULT_SSID, DEFAULT_PASS, prefer_5g=True)


def auto_connect_on_boot() -> None:
    """
    开机自动连接入口（建议在后台线程调用，不阻塞 UI）。

    策略：
    1. 如果 NetworkManager 已连上 WiFi → 直接跳过
    2. 先尝试"上次成功连接"的 SSID（若存在且密码有效）
    3. 再尝试出厂默认 (eserc / loongson@eserc)
    4. 都失败 → 放弃，让 NM 自己处理（用户可以进菜单手动连）
    """
    if not has_nmcli():
        print("[NM] auto_connect: nmcli 不存在，跳过")
        return
    if not has_nm():
        print("[NM] auto_connect: NetworkManager 未运行，跳过")
        return

    # 等 NM 就绪 + 无线接口起来
    for _ in range(15):
        s = get_status()
        if s.get("wifi") == "connected":
            print(f"[NM] auto_connect: 已连着 {s.get('wifi_ssid')}，跳过")
            return
        # wlan0 至少要在 managed 状态（disconnected/unconnected 都可以接受）
        if s.get("wifi") is not None and s.get("wifi") != "unavailable":
            break
        time.sleep(1)

    targets = []
    last = _load_last_wifi()
    if last and last.get("ssid"):
        targets.append((last["ssid"], last.get("password", ""), "last_success"))
    # 默认保底放最后
    targets.append((DEFAULT_SSID, DEFAULT_PASS, "factory_default"))

    for ssid, pwd, label in targets:
        print(f"[NM] auto_connect: 尝试 {label} → {ssid}")
        ok, msg = connect_wifi(ssid, pwd, prefer_5g=True)
        if ok:
            print(f"[NM] auto_connect: ✅ {ssid} ({msg})")
            return
        print(f"[NM] auto_connect: ❌ {ssid} 失败 ({msg})")

    print("[NM] auto_connect: 所有候选均失败，放弃。请进菜单手动连接。")
