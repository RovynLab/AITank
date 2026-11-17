"""
oled_renderer.py — SH1106 / SSD1306 128x64 单色 OLED 渲染器（纯 ASCII 界面）
==========================================================================

设计要点
--------
1. 只用等宽 ASCII 字体（DejaVu Sans Mono Bold）：字符宽度固定，可精确排版，
   不存在 CJK 字形高度溢出导致的裁切。
2. 实测墨迹高度：12px 字体的墨迹高 12px（不能塞进 11px 行距），
   因此主区用 11px（墨迹 10px）+ 11px 行距，状态栏/提示栏用 8px。
3. 硬件 rotate=0 + PIL 图像 180° 旋转，SH1106 与 SSD1306 行为一致。
4. 像素布局（64 行全部用满）：
        0..8    状态栏：WiFi 位图 + SSID + 网口位图 + 时间
        9       分隔线
        11..53  主区域 4 行（11px 行距，选中行反白）
        55..62  提示栏
5. 图标为 8x7 位图，用 draw.point 绘制，SH1106 完全兼容；
   WiFi 断开用棋盘格"灰显"，网口断开则完全不绘制（拔网线后不留残影）。
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

OLED_W, OLED_H = 128, 64
OLED_ADDR = 0x3C
ROTATE_DEG = 180

try:
    from luma.core.interface.serial import i2c
    from luma.oled.device import ssd1306, sh1106
    from PIL import Image, ImageDraw, ImageFont
    _HAS_LUMA = True
except ImportError:
    _HAS_LUMA = False
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        Image = ImageDraw = ImageFont = None

_MONO_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
]

# 8x7 位图图标（'#' = 亮）
_WIFI_ICON = [
    "        ",
    "  ####  ",
    " ##  ## ",
    "##    ##",
    "  ####  ",
    "   ##   ",
    "   ##   ",
]
_ETH_ICON = [
    "        ",
    " ###### ",
    " #    # ",
    " # ## # ",
    " ###### ",
    "  #  #  ",
    "  #  #  ",
]


def _find_mono_font() -> Optional[str]:
    for p in _MONO_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def _probe_device(serial):
    """自动探测控制器。SH1106 必须优先：SSD1306 初始化 SH1106 不会报错"""
    for name, cls, kw in [
        ("sh1106_128x64",   sh1106,  {"width": 128, "height": 64}),
        ("ssd1306_128x64", ssd1306, {"width": 128, "height": 64}),
        ("sh1106_128x32",   sh1106,  {"width": 128, "height": 32}),
        ("ssd1306_128x32", ssd1306, {"width": 128, "height": 32}),
    ]:
        try:
            dev = cls(serial, rotate=0, **kw)
            return dev, name
        except Exception:
            continue
    return None, None


class OLEDRenderer:
    """菜单专用 OLED 渲染器"""

    SEP_Y = 9        # 状态栏分隔线
    MAIN_Y0 = 10     # 主区域起点
    LINE_H = 11      # 主区域行距
    MAIN_LINES = 4   # 主区域可见行数
    HINT_INK = 55    # 提示栏墨迹顶部

    def __init__(self, address: int = OLED_ADDR):
        self._address = address
        self._device = None
        self._controller = ""
        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self._page: dict = {}
        self._net: dict = {"wifi": None, "eth": None, "wifi_ssid": "",
                           "wifi_ip": "", "eth_ip": ""}

        self.width = OLED_W
        self.height = OLED_H

        self._init_device()
        self._init_fonts()

    # ---------------------------------------------------------------- 初始化
    def _init_device(self):
        if not _HAS_LUMA:
            print("[OLED] luma.oled 不可用，Mock 模式")
            return
        try:
            serial = i2c(port=1, address=self._address)
            dev, name = _probe_device(serial)
            if dev is None:
                print("[OLED] 探测失败，Mock 模式")
                return
            self._device = dev
            self._controller = name or "unknown"
            self.width = getattr(dev, "width", OLED_W)
            self.height = getattr(dev, "height", OLED_H)
            print(f"[OLED] 已初始化 @ 0x{self._address:02X} "
                  f"{self.width}x{self.height} {self._controller}")
        except Exception as e:
            print(f"[OLED] 初始化失败 ({e})，Mock 模式")
            self._device = None

    def _init_fonts(self):
        path = _find_mono_font()
        if not path or not ImageFont:
            self._f_main = ImageFont.load_default() if ImageFont else None
            self._f_small = self._f_main
            self._cw_main = 6.0
            self._cw_small = 6.0
            self._main_oy, self._main_ih = 0, 7
            self._small_oy, self._small_ih = 0, 7
            print("[OLED] 未找到等宽字体，使用默认字体")
            return

        self._f_main = ImageFont.truetype(path, 11)
        self._f_small = ImageFont.truetype(path, 8)
        self._cw_main = float(self._f_main.getlength("M"))
        self._cw_small = float(self._f_small.getlength("M"))
        b = self._f_main.getbbox("Ag")
        self._main_oy, self._main_ih = b[1], b[3] - b[1]
        b2 = self._f_small.getbbox("Ag")
        self._small_oy, self._small_ih = b2[1], b2[3] - b2[1]
        print(f"[OLED] 字体 {os.path.basename(path)} 11px/8px "
              f"主区 {self._main_cols()} 列")

    # ---------------------------------------------------------------- 文本工具
    def _main_cols(self) -> int:
        return max(6, int((OLED_W - 4) / self._cw_main))

    def _small_cols(self) -> int:
        return max(6, int((OLED_W - 2) / self._cw_small))

    def _fit(self, text: str, cols: int) -> str:
        if len(text) <= cols:
            return text
        return text[:max(1, cols - 2)] + ".."

    def _fit_px(self, text: str, max_px: int, font) -> str:
        """按像素宽度截断"""
        if font is None:
            return text
        if font.getlength(text) <= max_px:
            return text
        while text and font.getlength(text + "..") > max_px:
            text = text[:-1]
        return text + ".."

    @staticmethod
    def _text(draw, x, ink_top, text, font, oy, fill=1):
        draw.text((int(x), int(ink_top - oy)), text, fill=fill, font=font)

    # ---------------------------------------------------------------- 生命周期
    def close(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._device:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

    def reinit(self):
        self.close()
        self._init_device()

    def start(self):
        self._running = True
        self._paused = False
        self._thread = threading.Thread(target=self._render_loop, daemon=True, name="oled")
        self._thread.start()

    def stop_rendering(self):
        self._paused = True

    def resume_rendering(self):
        self.reinit()
        self._paused = False

    def set_page(self, page: dict):
        with self._lock:
            self._page = page

    def set_net(self, net: dict):
        with self._lock:
            self._net = net

    def _render_loop(self):
        while self._running:
            if not self._paused:
                self._draw_frame()
            time.sleep(0.1)

    # ---------------------------------------------------------------- 每帧
    def _draw_frame(self):
        if Image is None:
            return
        img = Image.new("1", (OLED_W, OLED_H), 0)
        draw = ImageDraw.Draw(img)

        self._draw_status_bar(draw)
        with self._lock:
            page = dict(self._page)
        self._draw_body(draw, page)
        self._draw_hint(draw, page)

        if ROTATE_DEG:
            img = img.rotate(ROTATE_DEG)

        if self._device:
            try:
                self._device.display(img)
            except Exception as e:
                print(f"[OLED] display 失败: {e}")

    # ---------------------------------------------------------------- 图标
    @staticmethod
    def _bitmap(draw, x, y, rows, on=True):
        for ry, row in enumerate(rows):
            for rx, ch in enumerate(row):
                if ch != "#":
                    continue
                if not on and ((rx + ry) & 1):
                    continue        # 断开状态：棋盘格灰显
                draw.point((x + rx, y + ry), fill=1)

    # ---------------------------------------------------------------- 状态栏
    def _draw_status_bar(self, draw):
        with self._lock:
            net = dict(self._net)

        wifi_ok = net.get("wifi") == "connected"
        eth_ok = net.get("eth") == "connected"

        # WiFi 图标 @ (0,1)
        self._bitmap(draw, 0, 1, _WIFI_ICON, on=wifi_ok)

        # 时间右对齐
        now = datetime.now().strftime("%H:%M")
        tw = self._f_small.getlength(now)
        time_x = OLED_W - 1 - tw
        # 网口图标在时间左侧，仅网线真实连通时才显示（拔线后不再残留灰图标）
        eth_x = time_x - 3 - 8
        if eth_ok:
            self._bitmap(draw, int(eth_x), 1, _ETH_ICON, on=True)

        # SSID
        ssid = (net.get("wifi_ssid") or "").strip()
        if not ssid:
            ssid = "--" if wifi_ok else "no wifi"
        avail = int(eth_x) - 3 - 10
        self._text(draw, 10, 1, self._fit_px(ssid, avail, self._f_small),
                   self._f_small, self._small_oy)
        self._text(draw, time_x, 1, now, self._f_small, self._small_oy)

        draw.line([(0, self.SEP_Y), (OLED_W - 1, self.SEP_Y)], fill=1)

    # ---------------------------------------------------------------- 提示栏
    def _draw_hint(self, draw, page):
        hint = page.get("hint", "")
        if not hint:
            return
        self._text(draw, 2, self.HINT_INK,
                   self._fit_px(hint, OLED_W - 4, self._f_small),
                   self._f_small, self._small_oy)

    # ---------------------------------------------------------------- 主区域
    def _draw_body(self, draw, page):
        ptype = page.get("type", "main_menu")
        if ptype in ("main_menu", "apps_menu"):
            self._draw_list(draw, page)
        elif ptype == "wifi_list":
            self._draw_wifi_list(draw, page)
        elif ptype == "wifi_password":
            self._draw_wifi_password(draw, page)
        elif ptype == "network_status":
            self._draw_network_status(draw, page)
        elif ptype == "app_running":
            self._draw_app_running(draw, page)
        elif ptype == "banner":
            self._draw_banner(draw, page)
        elif ptype == "confirm":
            self._draw_confirm(draw, page)
        elif ptype == "shell":
            self._draw_shell(draw, page)

    def _ink_top(self, row: int) -> int:
        return self.MAIN_Y0 + 1 + row * self.LINE_H

    def _draw_row(self, draw, row: int, text: str, selected: bool, prefix: str = " "):
        ink = self._ink_top(row)
        if selected:
            draw.rectangle([0, ink - 1, OLED_W - 1, ink + self._main_ih - 1], fill=1)
            fg = 0
        else:
            fg = 1
        self._text(draw, 2, ink, self._fit(prefix + text, self._main_cols()),
                   self._f_main, self._main_oy, fill=fg)

    def _scroll_marks(self, draw, view, total):
        if view > 0:
            self._text(draw, OLED_W - 6, self._ink_top(0), "^", self._f_small, self._small_oy)
        if view + self.MAIN_LINES < total:
            self._text(draw, OLED_W - 6, self._ink_top(self.MAIN_LINES - 1),
                       "v", self._f_small, self._small_oy)

    def _draw_list(self, draw, page):
        items = page.get("items", [])
        sel = page.get("selected", 0)
        view = page.get("view_start", 0)
        view = max(0, min(view, max(0, len(items) - self.MAIN_LINES)))
        for i in range(self.MAIN_LINES):
            idx = view + i
            if idx >= len(items):
                break
            item = items[idx]
            label = item.get("name", "") if isinstance(item, dict) else str(item)
            self._draw_row(draw, i, label, idx == sel,
                           prefix=">" if idx == sel else " ")
        self._scroll_marks(draw, view, len(items))

    # ---------------------------------------------------------------- WiFi 列表
    def _draw_wifi_list(self, draw, page):
        items = page.get("items", [])
        sel = page.get("selected", 0)
        view = page.get("view_start", 0)
        view = max(0, min(view, max(0, len(items) - self.MAIN_LINES)))

        mark_up = view > 0
        mark_dn = view + self.MAIN_LINES < len(items)

        for i in range(self.MAIN_LINES):
            idx = view + i
            if idx >= len(items):
                break
            ap = items[idx]
            ink = self._ink_top(i)
            selected = idx == sel
            # 该行右侧要画滚动箭头时，安全标签左移，避免箭头压住标签
            has_mark = (i == 0 and mark_up) or (i == self.MAIN_LINES - 1 and mark_dn)
            tag_x_right = OLED_W - 3 - (7 if has_mark else 0)

            is_default = bool(ap.get("is_default"))
            locked = bool((ap.get("security") or "").strip())

            if is_default:
                tag = "RESET"           # 恢复出厂默认配置
            elif ap.get("enterprise"):
                tag = "1X"              # 802.1X 企业级认证，纯密码连不上
            else:
                tag = "WPA" if locked else "OPEN"
            tx = tag_x_right - self._f_small.getlength(tag)
            ssid_px = tx - 2 - 14

            if selected:
                draw.rectangle([0, ink - 1, OLED_W - 1, ink + self._main_ih - 1], fill=1)
                fg = 0
            else:
                fg = 1

            # 信号柱 4 根（x=4..10，底边对齐）；默认项不画
            if not is_default:
                sig = ap.get("signal", 0) or 0
                level = max(1, min(4, int(sig // 25) + 1))
                bottom = ink + self._main_ih - 1
                for b in range(4):
                    h = 2 + b
                    bx = 4 + b * 2
                    for dy in range(h):
                        draw.point((bx, bottom - dy), fill=fg)

            # SSID
            ssid = self._fit_px(ap.get("ssid") or "", ssid_px, self._f_main)
            self._text(draw, 14, ink, ssid, self._f_main, self._main_oy, fill=fg)

            # 右侧安全标签
            self._text(draw, tx, ink + 2, tag, self._f_small, self._small_oy, fill=fg)

        self._scroll_marks(draw, view, len(items))

    # ---------------------------------------------------------------- 密码输入
    def _draw_wifi_password(self, draw, page):
        ssid = page.get("ssid", "")
        pwd = page.get("pwd_mask", "")
        ink = self._ink_top(0)
        self._text(draw, 2, ink, self._fit_px("SSID " + ssid, OLED_W - 4, self._f_main),
                   self._f_main, self._main_oy)
        self._text(draw, 2, ink + self.LINE_H + 3,
                   self._fit_px(pwd, OLED_W - 4, self._f_main),
                   self._f_main, self._main_oy)

    # ---------------------------------------------------------------- 网络状态
    def _draw_network_status(self, draw, page):
        net = page.get("net", {}) or {}
        view = page.get("view_start", 0)
        wifi_ok = net.get("wifi") == "connected"
        eth_ok = net.get("eth") == "connected"

        lines = ["WIFI " + ("UP   " + (net.get("wifi_ssid") or "-") if wifi_ok else "DOWN")]
        if wifi_ok:
            lines.append("  " + (net.get("wifi_ip") or "-"))
        lines.append("LAN  " + ("UP" if eth_ok else "DOWN"))
        if eth_ok:
            lines.append("  " + (net.get("eth_ip") or "-"))
        if net.get("wifi_mac"):
            lines.append("WMAC " + str(net["wifi_mac"])[-11:])
        if net.get("eth_mac"):
            lines.append("EMAC " + str(net["eth_mac"])[-11:])
        if net.get("gateway"):
            lines.append("GW   " + str(net["gateway"]))
        if net.get("dns"):
            lines.append("DNS  " + str(net["dns"]))
        if net.get("uptime_sec"):
            h, r = divmod(net["uptime_sec"], 3600)
            m, _ = divmod(r, 60)
            lines.append(f"UP   {h}h{m:02d}m")

        view = max(0, min(view, max(0, len(lines) - self.MAIN_LINES)))
        mark = view > 0 or view + self.MAIN_LINES < len(lines)
        max_px = OLED_W - (12 if mark else 4)
        for i in range(self.MAIN_LINES):
            idx = view + i
            if idx >= len(lines):
                break
            self._text(draw, 2, self._ink_top(i),
                       self._fit_px(lines[idx], max_px, self._f_main),
                       self._f_main, self._main_oy)
        self._scroll_marks(draw, view, len(lines))

    # ---------------------------------------------------------------- 应用运行
    def _draw_app_running(self, draw, page):
        name = page.get("name", "")
        ink = self._ink_top(1)
        self._text(draw, 2, ink, "RUNNING", self._f_main, self._main_oy)
        self._text(draw, 2, ink + self.LINE_H,
                   self._fit_px(name, OLED_W - 4, self._f_main),
                   self._f_main, self._main_oy)
        self._text(draw, 2, ink + self.LINE_H * 2 + 2, "CTRL+SHIFT+X TO KILL",
                   self._f_small, self._small_oy)

    # ---------------------------------------------------------------- 横幅
    def _draw_banner(self, draw, page):
        msg = page.get("msg", "")
        sub = page.get("sub", "")
        ink = self._ink_top(1)
        self._text(draw, 2, ink, self._fit_px(msg, OLED_W - 4, self._f_main),
                   self._f_main, self._main_oy)
        if sub:
            self._text(draw, 2, ink + self.LINE_H + 2,
                       self._fit_px(sub, OLED_W - 4, self._f_small),
                       self._f_small, self._small_oy)

    # ---------------------------------------------------------------- 确认框
    def _draw_confirm(self, draw, page):
        msg = page.get("msg", "")
        sel = page.get("sel", 0)
        self._text(draw, 2, self._ink_top(0),
                   self._fit_px(msg, OLED_W - 4, self._f_main),
                   self._f_main, self._main_oy)
        for row, label, on in ((1, "YES", sel == 0), (2, "NO", sel == 1)):
            ink = self._ink_top(row)
            if on:
                draw.rectangle([0, ink - 1, OLED_W - 1, ink + self._main_ih - 1], fill=1)
                self._text(draw, 4, ink, label, self._f_main, self._main_oy, fill=0)
            else:
                self._text(draw, 4, ink, label, self._f_main, self._main_oy)

    # ---------------------------------------------------------------- 命令行
    def _draw_shell(self, draw, page):
        outputs = page.get("outputs", []) or []
        prompt = page.get("prompt", "")
        rows = self.MAIN_LINES - 1
        shown = list(outputs[-rows:])
        while len(shown) < rows:
            shown.insert(0, "")
        for i, line in enumerate(shown):
            self._text(draw, 2, self._ink_top(i),
                       self._fit_px(line, OLED_W - 4, self._f_small),
                       self._f_small, self._small_oy)
        self._text(draw, 2, self._ink_top(rows),
                   self._fit_px(prompt, OLED_W - 4, self._f_main),
                   self._f_main, self._main_oy)
