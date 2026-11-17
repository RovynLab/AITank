"""
main.py — AITank 开机菜单管理器主入口
========================================

整合：keyboard_listener + oled_renderer + network_manager + app_launcher
实现状态机驱动的页面流转。

菜单结构：
  主菜单 ─┬─ APPS → 子菜单（含"返回上级"）
          ├─ WIFI 设置
          ├─ NETWORK 状态
          ├─ REBOOT
          └─ EXIT（退出 menu 进程）

用法：
    python3 -m aitank_menu.main          # 前台运行（日志可见）
    sudo systemctl start aitank-menu     # systemd 后台常驻
"""

from __future__ import annotations

import os
import sys
import time
import signal
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from aitank_menu.keyboard_listener import KeyboardListener, KeyEvent
from aitank_menu.oled_renderer import OLEDRenderer
from aitank_menu.network_manager import (
    get_status, scan_wifi, connect_wifi, disconnect_wifi,
    has_nmcli,
    auto_connect_on_boot, connect_default_wifi, clear_last_wifi,
    DEFAULT_SSID, DEFAULT_PASS,
)
from aitank_menu.app_launcher import AppLauncher, load_apps


# ============================================================================
# 页面状态机
# ============================================================================
# state 值列表：
#   "main_menu"       主菜单（第一级）
#   "apps_menu"       启动应用子菜单（第二级）
#   "wifi_list"       WiFi 扫描列表
#   "wifi_password"   WiFi 密码输入
#   "wifi_connecting" 连接中 banner
#   "network_status"  网络详情
#   "exit_banner"     操作完成过渡
#   "confirm"         确认对话框
#   "shutting_down"   退出/重启/启动应用中


class MenuController:
    def __init__(self):
        # 模块
        self.renderer = OLEDRenderer()
        self.kbd = KeyboardListener()
        self.launcher = AppLauncher()

        # 状态
        self.state = "main_menu"
        self.apps = load_apps()

        # 主菜单
        self.main_items = self._build_main_menu()
        self.main_selected = 0
        self.main_view = 0

        # 应用子菜单
        self.apps_items = self._build_apps_menu()
        self.apps_selected = 0
        self.apps_view = 0

        # WiFi 列表
        self.wifi_list: list[dict] = []
        self.wifi_selected = 0
        self.wifi_view = 0

        # 网络状态页
        self.net_view = 0

        # 密码输入
        self.wifi_pwd_input = ""
        self.wifi_connecting_ssid = ""

        # 确认对话框
        self.confirm_msg = ""
        self.confirm_action: Optional[str] = None  # "reboot" | "shutdown"

        # exit banner
        self.exit_banner_until = 0.0
        self.exit_return_to = "main_menu"

        # 退出信号
        self._shutdown = False

        # 后台线程
        self._net_thread: Optional[threading.Thread] = None
        self._net_stop = threading.Event()

    # ---------- 菜单构建 ----------
    def _build_main_menu(self) -> list[dict]:
        """第一级主菜单"""
        return [
            {"type": "apps",    "name": "APPS"},
            {"type": "wifi",    "name": "WIFI"},
            {"type": "status",  "name": "NETWORK"},
            {"type": "reboot",  "name": "REBOOT"},
            {"type": "exit",    "name": "EXIT"},
        ]

    def _build_apps_menu(self) -> list[dict]:
        """应用子菜单：第一项 = 返回上级，后面是注册的 apps"""
        items = [{"type": "back", "name": "< BACK"}]
        for app in self.apps:
            items.append({
                "type": "app",
                "app": app,
                "name": app.get("name", app.get("id", "未知")),
            })
        return items

    # ==========================================================================
    # 启动与清理
    # ==========================================================================
    def run(self):
        print("[Menu] === AITank 开机菜单启动 ===")

        self.renderer.start()  # OLED 渲染线程 10 FPS

        if not self.kbd.start():
            print("[Menu] 警告：未检测到 USB 键盘")

        self.kbd.on_key = self._on_key
        self._start_net_poller()
        self._refresh_net_once()

        # ============ 开机自动连 WiFi（后台线程，不阻塞 UI）============
        if has_nmcli():
            threading.Thread(target=auto_connect_on_boot,
                             daemon=True, name="auto-wifi").start()
        else:
            print("[Menu] nmcli 不存在，跳过开机自动连 WiFi")

        signal.signal(signal.SIGINT, self._sig_handler)
        signal.signal(signal.SIGTERM, self._sig_handler)
        # SIGUSR1 = 暂停 OLED（petcar 要独占 OLED），SIGUSR2 = 恢复
        signal.signal(signal.SIGUSR1, self._sig_pause_oled)
        signal.signal(signal.SIGUSR2, self._sig_resume_oled)

        self._render_page()
        print("[Menu] 进入主循环...")

        try:
            while not self._shutdown:
                # exit_banner 到期 → 自动跳转到 return_to
                if self.state == "exit_banner" and time.time() >= self.exit_banner_until:
                    if self.exit_return_to == "apps_menu":
                        self._goto_apps_menu()
                    elif self.exit_return_to == "wifi_list":
                        self._enter_wifi_list()
                    else:
                        self._goto_main_menu()
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("[Menu] Ctrl+C")
        finally:
            self._shutdown_cleanly()

    def _sig_handler(self, signum, frame):
        print(f"[Menu] 收到信号 {signum}")
        self._shutdown = True

    def _sig_pause_oled(self, signum, frame):
        """SIGUSR1 — petcar 要独占 OLED，暂停 menu 的渲染线程"""
        print("[Menu] 收到 SIGUSR1，暂停 OLED 渲染（让路给其他应用）")
        try:
            self.renderer.stop_rendering()
        except Exception as e:
            print(f"[Menu] stop_rendering 异常：{e}")

    def _sig_resume_oled(self, signum, frame):
        """SIGUSR2 — 其他应用用完 OLED，恢复 menu 渲染"""
        print("[Menu] 收到 SIGUSR2，恢复 OLED 渲染")
        try:
            self.renderer.resume_rendering()
            self._render_page()
        except Exception as e:
            print(f"[Menu] resume_rendering 异常：{e}")

    def _shutdown_cleanly(self):
        print("[Menu] 清理中...")
        self._net_stop.set()
        self.kbd.stop()
        if self.launcher.is_running:
            self.launcher.kill_current(force=True)
        self.renderer.close()
        print("[Menu] 已退出")

    # ---------- 后台网络轮询 ----------
    def _start_net_poller(self):
        t = threading.Thread(target=self._net_loop, daemon=True, name="net")
        t.start()

    def _net_loop(self):
        while not self._net_stop.is_set():
            self._refresh_net_once()
            self._net_stop.wait(2.0)   # 2s 轮询：拔插网线后状态栏能快速跟随

    def _refresh_net_once(self):
        s = get_status()
        self.renderer.set_net({
            "wifi": s.get("wifi"),
            "wifi_ssid": s.get("wifi_ssid", ""),
            "wifi_ip": s.get("wifi_ip", ""),
            "eth": s.get("eth"),
            "eth_ip": s.get("eth_ip", ""),
            "wifi_mac": s.get("wifi_mac", ""),
            "eth_mac": s.get("eth_mac", ""),
            "gateway": s.get("gateway", ""),
            "dns": s.get("dns", ""),
            "uptime_sec": s.get("uptime_sec", 0),
        })

    # ==========================================================================
    # 键盘事件分发
    # ==========================================================================
    def _on_key(self, ev: KeyEvent):
        handler = {
            "main_menu":       self._key_main_menu,
            "apps_menu":       self._key_apps_menu,
            "wifi_list":       self._key_wifi_list,
            "wifi_password":   self._key_wifi_password,
            "wifi_connecting": None,  # 连接中忽略按键
            "network_status":  self._key_network_status,
            "exit_banner":     None,  # 自动跳，按键忽略
            "confirm":         self._key_confirm,
            "shutting_down":   None,
        }.get(self.state)

        if handler:
            handler(ev)

    # ---------- main_menu ----------
    def _key_main_menu(self, ev: KeyEvent):
        total = len(self.main_items)
        if ev.char == "UP":
            self.main_selected, self.main_view = self._scroll(
                self.main_selected - 1, total, self.main_view, 4)
        elif ev.char == "DOWN":
            self.main_selected, self.main_view = self._scroll(
                self.main_selected + 1, total, self.main_view, 4)
        elif ev.char in ("ENTER", "RIGHT"):
            self._select_main(self.main_selected)
        elif ev.char in ("LEFT", "ESC"):
            self._do_exit()
        self._render_page()

    def _select_main(self, idx: int):
        self.main_selected = idx
        item = self.main_items[idx]
        itype = item["type"]
        if itype == "apps":
            self._goto_apps_menu()
        elif itype == "wifi":
            self._enter_wifi_list()
        elif itype == "status":
            self._enter_network_status()
        elif itype == "reboot":
            self._enter_confirm("Reboot?", "reboot")
        elif itype == "exit":
            self._do_exit()

    @staticmethod
    def _scroll(sel: int, total: int, view: int, visible: int) -> tuple[int, int]:
        """保证 sel 在 view ~ view+visible-1 范围内"""
        sel = max(0, min(total - 1, sel))
        if sel < view:
            view = sel
        elif sel >= view + visible:
            view = sel - visible + 1
        return sel, view

    # ---------- apps_menu（子菜单） ----------
    def _goto_apps_menu(self):
        self.state = "apps_menu"
        self.apps_selected = 0
        self.apps_view = 0
        self.apps_items = self._build_apps_menu()
        self._render_page()

    def _key_apps_menu(self, ev: KeyEvent):
        total = len(self.apps_items)
        if ev.char == "UP":
            self.apps_selected, self.apps_view = self._scroll(
                self.apps_selected - 1, total, self.apps_view, 4)
        elif ev.char == "DOWN":
            self.apps_selected, self.apps_view = self._scroll(
                self.apps_selected + 1, total, self.apps_view, 4)
        elif ev.char in ("ENTER", "RIGHT"):
            self._select_apps(self.apps_selected)
        elif ev.char in ("LEFT", "ESC"):
            self._goto_main_menu()
        self._render_page()

    def _select_apps(self, idx: int):
        self.apps_selected = idx
        item = self.apps_items[idx]
        itype = item["type"]
        if itype == "back":
            self._goto_main_menu()
        elif itype == "app":
            self._launch_app(item["app"])

    # ---------- wifi_list ----------
    def _enter_wifi_list(self):
        self.state = "wifi_list"
        # 扫描要 2-5 秒，先显示横幅，避免屏幕无反应
        self._render_page_banner("Scanning WiFi...", "")
        time.sleep(0.25)
        aps = scan_wifi()
        # 在列表顶部插入一个"重置为默认"的特殊项
        default_item = {
            "ssid": "DEFAULT (" + DEFAULT_SSID + ")",
            "signal": -1,           # 渲染器识别 signal<0 → 不画信号柱
            "security": "FACTORY",  # 渲染器识别 FACTORY → 显示出厂重置标签
            "enterprise": False,
            "in_use": False,
            "is_default": True,     # 逻辑标记：这是"恢复默认配置"项
        }
        self.wifi_list = [default_item] + aps
        self.wifi_selected = 0
        self.wifi_view = 0
        self._render_page()

    def _key_wifi_list(self, ev: KeyEvent):
        total = len(self.wifi_list)
        if ev.char == "UP":
            self.wifi_selected, self.wifi_view = self._scroll(
                self.wifi_selected - 1, max(total, 1), self.wifi_view, 4)
        elif ev.char == "DOWN":
            self.wifi_selected, self.wifi_view = self._scroll(
                self.wifi_selected + 1, max(total, 1), self.wifi_view, 4)
        elif ev.char in ("ENTER", "RIGHT"):
            if self.wifi_list:
                ap = self.wifi_list[self.wifi_selected]
                # 特殊项：重置为出厂默认（eserc）
                if ap.get("is_default"):
                    self._do_reset_to_default()
                    self._render_page()
                    return
                security = ap.get("security", "") or ""
                # 企业级认证（eduroam / ECNU-1X 等）要账号+证书，菜单不支持
                if ap.get("enterprise"):
                    self._render_page_banner("802.1X NEEDED", "NOT SUPPORTED")
                    time.sleep(1.5)
                # 开放网络（没加密标记）直接连，跳过密码页面
                elif not security.strip():
                    ssid = ap["ssid"]
                    self._do_connect_wifi(ssid, "")
                else:
                    self._enter_wifi_password()
        elif ev.char in ("LEFT", "ESC"):
            self._goto_main_menu()
        self._render_page()

    def _do_reset_to_default(self):
        """清掉 last_wifi 记录 → 连出厂默认 (eserc / loongson@eserc)"""
        clear_last_wifi()
        self.state = "wifi_connecting"
        self.wifi_connecting_ssid = DEFAULT_SSID
        self._render_page_banner("Resetting to default", DEFAULT_SSID)

        def _worker():
            ok, msg = connect_default_wifi()
            time.sleep(0.5)
            self._refresh_net_once()
            self._show_exit_banner(
                ("OK: " + msg[:16]) if ok else ("FAIL: " + msg[:16]),
                duration=2.0,
                return_to="main_menu" if ok else "wifi_list",
            )

        threading.Thread(target=_worker, daemon=True).start()

    # ---------- wifi_password ----------
    def _enter_wifi_password(self):
        self.state = "wifi_password"
        self.wifi_pwd_input = ""
        self._render_page()

    def _key_wifi_password(self, ev: KeyEvent):
        if ev.char in ("LEFT", "ESC"):
            self.state = "wifi_list"
            self._render_page()
            return
        if ev.char == "ENTER":
            ssid = self.wifi_list[self.wifi_selected]["ssid"] if self.wifi_list else ""
            self._do_connect_wifi(ssid, self.wifi_pwd_input)
            return
        if ev.char == "BACKSPACE":
            self.wifi_pwd_input = self.wifi_pwd_input[:-1]
            self._render_page()
            return
        # 方向键忽略（防止误触）
        if ev.char in ("UP", "DOWN", "RIGHT"):
            return
        # 可打印字符
        if not ev.is_functional and len(self.wifi_pwd_input) < 64:
            self.wifi_pwd_input += ev.char
            self._render_page()

    def _do_connect_wifi(self, ssid: str, pwd: str):
        self.state = "wifi_connecting"
        self.wifi_connecting_ssid = ssid
        self._render_page_banner("Connecting...", ssid)

        def _worker():
            ok, msg = connect_wifi(ssid, pwd)
            time.sleep(0.5)
            self._refresh_net_once()
            self._show_exit_banner(
                ("OK: " + msg[:16]) if ok else ("FAIL: " + msg[:16]),
                duration=2.0,
                return_to="main_menu" if ok else "wifi_list",
            )

        threading.Thread(target=_worker, daemon=True).start()

    # ---------- network_status ----------
    def _enter_network_status(self):
        self.state = "network_status"
        self.net_view = 0
        self._refresh_net_once()
        self._render_page()

    def _key_network_status(self, ev: KeyEvent):
        # 行数不确定（动态根据连接状态），用 max 3 保守估算
        # renderer 里用 view_start + visible 控制
        if ev.char == "UP":
            self.net_view = max(0, self.net_view - 1)
            self._render_page()
        elif ev.char == "DOWN":
            # 允许翻到 view_start 较大值，renderer 会 clamp
            self.net_view += 1
            self._render_page()
        elif ev.char in ("LEFT", "ESC"):
            self._goto_main_menu()
        elif ev.char in ("ENTER", "RIGHT"):
            # ENTER = 刷新网络状态
            self._refresh_net_once()
            self.net_view = 0
            self._render_page()

    # ---------- confirm ----------
    def _enter_confirm(self, msg: str, action: str):
        self.state = "confirm"
        self.confirm_msg = msg
        self.confirm_action = action
        self._confirm_sel = 0  # 0=Yes, 1=No
        self._render_page()

    def _key_confirm(self, ev: KeyEvent):
        if ev.char == "UP":
            self._confirm_sel = 0
            self._render_page()
        elif ev.char == "DOWN":
            self._confirm_sel = 1
            self._render_page()
        elif ev.char in ("ENTER", "RIGHT"):
            if self._confirm_sel == 0:
                self._do_reboot_or_shutdown()
            else:
                self._goto_main_menu()
        elif ev.char in ("LEFT", "ESC"):
            self._goto_main_menu()

    def _do_reboot_or_shutdown(self):
        action = self.confirm_action or "shutdown"
        self.state = "shutting_down"
        self._render_page_banner(("reboot..." if action == "reboot" else "shutdown..."), "")
        time.sleep(1.5)
        self._shutdown_cleanly()
        os.system("sudo reboot" if action == "reboot" else "sudo shutdown -h now")

    # ==========================================================================
    # EXIT & 启动 petcar（清资源 → 停 service → exec 替换进程）
    # ==========================================================================
    def _stop_aitank_service(self):
        """停掉 systemd 的 aitank-menu，防止 Restart=always 重启 menu"""
        try:
            os.system("systemctl stop aitank-menu.service 2>/dev/null")
            print("[Menu] 已 stop aitank-menu.service")
        except Exception as e:
            print(f"[Menu] stop service 失败（可忽略）: {e}")

    def _do_exit(self):
        """退出 menu 程序，释放所有资源，停 service，进程结束"""
        print("[Menu] EXIT → 清理资源并停服务")
        self._shutdown_cleanly()
        self._stop_aitank_service()
        os._exit(0)

    # ==========================================================================
    # 应用启动 — petcar full 模式：清资源 → 停 service → exec 替换进程
    # ==========================================================================
    def _launch_app(self, app_config: dict):
        print(f"[Menu] 启动应用: {app_config.get('name')}")

        # === 对于 petcar full 等"独占型"应用：menu 自己退出，exec 替换进程 ===
        app_id = app_config.get("id", "")
        if app_id == "petcar_full":
            self._launch_via_exec(app_config)
            return

        # === 其他普通应用：暂不支持（APPS 里只留 petcar_full 了）===
        print(f"[Menu] 暂不支持此应用: {app_id}")
        self._show_exit_banner("Not supported", duration=1.5)

    def _launch_via_exec(self, app_config: dict):
        """
        释放 OLED / 键盘 / 线程 → 停 systemd service → os.execvp 替换为目标进程。
        这样 petcar 退出后，PID 没变但进程已不是 menu，systemd 不会重启 menu。
        """
        # 1. 显示过渡 banner
        self.state = "shutting_down"
        self._render_page_banner("Launching...", app_config.get("name", ""))
        time.sleep(0.8)

        # 2. 清理自己的所有资源
        print("[Menu] 清理资源...")
        self._net_stop.set()
        self.kbd.stop()
        self.renderer.close()

        # 3. 停 systemd service（防止 exec 前 service 重启 menu）
        self._stop_aitank_service()
        time.sleep(0.3)

        # 4. exec 替换当前进程为 petcar
        cmd = app_config["command"]
        cwd = app_config.get("cwd") or _ROOT
        env = os.environ.copy()
        env.update(app_config.get("env", {}) or {})

        print(f"[Menu] exec: {' '.join(cmd)}")
        print(f"[Menu]   cwd = {cwd}")

        try:
            os.chdir(cwd)
            os.execvpe(cmd[0], cmd, env)
        except FileNotFoundError as e:
            print(f"[Menu] exec 失败（可执行文件不存在）: {e}")
        except Exception as e:
            print(f"[Menu] exec 失败: {e}")

        # exec 失败的保底：退出去
        print("[Menu] exec 失败，执行 _do_exit()")
        os._exit(1)

    # ==========================================================================
    # exit_banner → 自动跳转
    # ==========================================================================
    def _show_exit_banner(self, msg: str, duration: float = 2.0,
                          return_to: str = "main_menu"):
        self.state = "exit_banner"
        self._exit_msg = msg
        self.exit_return_to = return_to
        self.exit_banner_until = time.time() + duration
        self._render_page()

    # ==========================================================================
    # 页面跳转
    # ==========================================================================
    def _goto_main_menu(self):
        self.state = "main_menu"
        self.main_items = self._build_main_menu()
        self._refresh_net_once()
        self._render_page()

    # ==========================================================================
    # 渲染（state → renderer.set_page）
    # ==========================================================================
    def _render_page(self):
        s = self.state
        if s == "main_menu":
            self.renderer.set_page({
                "type": "main_menu",
                "items": [it["name"] for it in self.main_items],
                "selected": self.main_selected,
                "view_start": self.main_view,
                "hint": "UP/DN MOVE  OK SELECT",
            })
        elif s == "apps_menu":
            self.renderer.set_page({
                "type": "apps_menu",
                "items": [it["name"] for it in self.apps_items],
                "selected": self.apps_selected,
                "view_start": self.apps_view,
                "hint": "OK RUN  LEFT BACK",
            })
        elif s == "wifi_list":
            self.renderer.set_page({
                "type": "wifi_list",
                "items": self.wifi_list,
                "selected": self.wifi_selected,
                "view_start": self.wifi_view,
                "hint": "OK CONNECT  LEFT BACK",
            })
        elif s == "wifi_password":
            # 明文显示（小键盘输密码不容易输错，需要看得见）
            pwd = self.wifi_pwd_input + ("_" if len(self.wifi_pwd_input) < 64 else "")
            ssid = self.wifi_list[self.wifi_selected]["ssid"] if self.wifi_list else ""
            self.renderer.set_page({
                "type": "wifi_password",
                "ssid": ssid,
                "pwd_mask": pwd,
                "hint": "TYPE  OK DONE  LEFT BACK",
            })
        elif s == "wifi_connecting":
            self._render_page_banner("Connecting...", self.wifi_connecting_ssid)
        elif s == "network_status":
            self.renderer.set_page({
                "type": "network_status",
                "net": self.renderer._net,
                "view_start": self.net_view,
                "hint": "UP/DN SCROLL  OK REFRESH",
            })
        elif s == "exit_banner":
            self.renderer.set_page({
                "type": "banner",
                "msg": getattr(self, "_exit_msg", ""),
                "sub": "",
                "hint": "",
            })
        elif s == "confirm":
            self.renderer.set_page({
                "type": "confirm",
                "msg": self.confirm_msg,
                "sel": getattr(self, "_confirm_sel", 0),
                "hint": "UP/DN CHOOSE  OK APPLY",
            })
        elif s == "shutting_down":
            self.renderer.set_page({
                "type": "banner",
                "msg": "shutdown...",
                "hint": "",
            })

    def _render_page_banner(self, msg: str, sub: str = ""):
        self.renderer.set_page({
            "type": "banner",
            "msg": msg,
            "sub": sub,
            "hint": "",
        })


# ============================================================================
# 入口
# ============================================================================

def main():
    MenuController().run()


if __name__ == "__main__":
    main()
