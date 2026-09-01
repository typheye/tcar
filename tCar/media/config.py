# -*- coding:utf-8 -*-
# 配置和常量定义

import os
import cv2
import numpy as np
from PIL import Image

SYS_MODE = 1   # 0: Debug Mode | 1: User Mode

# 屏幕尺寸
SCREEN_WIDTH = 240
SCREEN_HEIGHT = 240

# 颜色定义
COLOR_BLACK = "BLACK"
COLOR_WHITE = "WHITE"
COLOR_WHITE2 = "#CDCDCD"
COLOR_GREY = "#555555"
# COLOR_BLUE = "#0ff0fc"
COLOR_BLUE = "#1f4648"
# COLOR_DARK_BLUE = "#132238"
COLOR_DARK_BLUE = "#000000"
# COLOR_MID_BLUE = "#375e94"
COLOR_MID_BLUE = "#111111"
# COLOR_LIGHT_BLUE = "#55d4dd"
COLOR_LIGHT_BLUE = "#1f4648"
COLOR_GREEN = "#00FF00"
COLOR_RED = "#F00000"
COLOR_YELLOW = "#FFFF00"
COLOR_BLUEFF = "#0000ff"


# 按钮引脚定义
KEY_up_PIN = 6
KEY_down_PIN = 19
KEY_left_PIN = 5
KEY_right_PIN = 26
KEY_press_PIN = 13
ok_PIN = 21
main_PIN = 20
cancel_PIN = 16

# LCD引脚定义
RST = 27
DC = 25
BL = 24
bus = 0
device_pin = 0

# 字体路径
FONT_NORMAL = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf"

# INA219地址
INA219_ADDR = 0x43

# Main battery: two 3500 mAh 18650 cells in series (2S). Series voltage
# increases while capacity remains 3.5 Ah. Runtime is an estimate based on
# the whole-car reference draw and can be tuned from field measurements.
BATTERY_NOMINAL_VOLTAGE = 7.4
BATTERY_CAPACITY_AH = 3.5
CAR_REFERENCE_POWER_W = 12.0

# JSON数据源URL
JSON_DATA_URL = "http://192.168.66.1/test"
