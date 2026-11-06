#!/usr/bin/env python3
"""SSD1306 128x64 OLED I2C 点亮测试程序"""
import smbus
import time

I2C_ADDR = 0x3C
WIDTH = 128
HEIGHT = 64

# SSD1306 初始化命令序列
INIT_CMDS = [
    0xAE,         # display off
    0xD5, 0x80,   # set display clock div
    0xA8, 0x3F,   # set multiplex ratio (64)
    0xD3, 0x00,   # set display offset
    0x40,         # set start line
    0x8D, 0x14,   # set charge pump (enable)
    0x20, 0x00,   # set memory addr mode (horizontal)
    0xA1,         # seg remap
    0xC8,         # com output scan dir
    0xDA, 0x12,   # set com pins
    0x81, 0xCF,   # set contrast
    0xD9, 0xF1,   # set pre-charge period
    0xDB, 0x40,   # set vcomh deselect
    0xA4,         # display follows RAM
    0xA6,         # normal display
    0xAF,         # display on
]

def write_cmd(bus, cmd):
    """发送命令字节"""
    bus.write_byte_data(I2C_ADDR, 0x00, cmd)

def write_data(bus, data):
    """发送数据字节"""
    bus.write_byte_data(I2C_ADDR, 0x40, data)

def init_display(bus):
    for cmd in INIT_CMDS:
        write_cmd(bus, cmd)

def fill(bus, value):
    """全屏填充"""
    for page in range(HEIGHT // 8):
        write_cmd(bus, 0xB0 | page)   # set page
        write_cmd(bus, 0x00)           # low col
        write_cmd(bus, 0x10)           # high col
        for col in range(WIDTH):
            write_data(bus, value)

def fill_pattern(bus):
    """显示棋盘格图案"""
    for page in range(HEIGHT // 8):
        write_cmd(bus, 0xB0 | page)
        write_cmd(bus, 0x00)
        write_cmd(bus, 0x10)
        for col in range(WIDTH):
            # 交替 0xAA (10101010) 和 0x55 (01010101)
            write_data(bus, 0xAA if (col + page) % 2 == 0 else 0x55)

def draw_border(bus):
    """画边框"""
    # 清空
    fill(bus, 0x00)
    # 顶边和底边
    for col in range(WIDTH):
        write_cmd(bus, 0xB0 | 0)
        write_cmd(bus, 0x00 | (col & 0x0F))
        write_cmd(bus, 0x10 | ((col >> 4) & 0x0F))
        write_data(bus, 0xFF)

        write_cmd(bus, 0xB0 | (HEIGHT // 8 - 1))
        write_cmd(bus, 0x00 | (col & 0x0F))
        write_cmd(bus, 0x10 | ((col >> 4) & 0x0F))
        write_data(bus, 0xFF)

    # 左边和右边
    for page in range(HEIGHT // 8):
        write_cmd(bus, 0xB0 | page)
        write_cmd(bus, 0x00)
        write_cmd(bus, 0x10)
        write_data(bus, 0xFF)

        write_cmd(bus, 0xB0 | page)
        write_cmd(bus, 0x00 | ((WIDTH - 1) & 0x0F))
        write_cmd(bus, 0x10 | (((WIDTH - 1) >> 4) & 0x0F))
        write_data(bus, 0xFF)

def main():
    print("Opening I2C bus 1...")
    bus = smbus.SMBus(1)

    print("Initializing SSD1306 display at 0x%02X..." % I2C_ADDR)
    init_display(bus)
    time.sleep(0.1)

    print("Step 1: Full WHITE screen")
    fill(bus, 0xFF)
    time.sleep(2)

    print("Step 2: Full BLACK screen")
    fill(bus, 0x00)
    time.sleep(1)

    print("Step 3: Checkerboard pattern")
    fill_pattern(bus)
    time.sleep(2)

    print("Step 4: Border + text area")
    draw_border(bus)
    time.sleep(3)

    print("Step 5: Invert test")
    write_cmd(bus, 0xA7)  # invert on
    time.sleep(2)
    write_cmd(bus, 0xA6)  # invert off

    print("Step 6: All pixels ON (solid white again)")
    fill(bus, 0xFF)
    print("Done! Screen should be fully lit.")

    bus.close()

if __name__ == "__main__":
    main()
