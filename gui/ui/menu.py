# -*- coding:utf-8 -*-
# 菜单系统

import time
from display.graphics import Graphics
from display.fonts import fonts
from utils import press_key, wait_release, wait_press
from config import *


class MenuManager:
    def __init__(
        self, display, buttons, wifi_manager, system_info=None, power_monitor=None
    ):
        self.display = display
        self.buttons = buttons
        self.wifi_manager = wifi_manager
        self.system_info = system_info
        self.power_monitor = power_monitor

    def show_main_menu(self):
        """显示主菜单"""
        menu_items = ["本机信息", "中枢信息", "重启系统"]
        current_index = 0

        while True:
            with self.display.lcd.create_canvas() as canvas:
                Graphics.draw_background(canvas.draw, "设置")
                if self.system_info:
                    ip, wifi = (
                        self.system_info.get_info()[0],
                        self.system_info.get_info()[-2],
                    )
                else:
                    ip, wifi = "", ""
                Graphics.draw_header(canvas.draw, ip, wifi)
                self._draw_menu(canvas.draw, menu_items, current_index)
                Graphics.draw_footer(canvas.draw, left_text="确定")

                # 处理按键
                if wait_press(KEY_press_PIN) or wait_press(ok_PIN):
                    if current_index == 0:
                        self.show_system_info()
                    elif current_index == 1:
                        self.show_core_info()
                    elif current_index == 2:
                        #     self.show_wifi_menu()
                        # elif current_index == 2:
                        #     self.show_display_settings()
                        # elif current_index == 3:
                        from system.power import PowerManager

                        if PowerManager.show_power_off_screen(
                            self.display,
                            self.buttons,
                            self.wifi_manager,
                            self.system_info,
                            self.power_monitor,
                        ):
                            return

                current_index = self.buttons.navigate_menu(
                    current_index, len(menu_items)
                )

                if press_key(cancel_PIN):
                    wait_release(cancel_PIN)
                    return

            time.sleep(0.01)

    def show_selection_menu(self, title, items, vertical=True):
        """显示选择菜单"""
        current_index = 0

        while True:
            with self.display.lcd.create_canvas() as canvas:
                Graphics.draw_background(canvas.draw, title)
                if self.system_info:
                    ip, wifi = (
                        self.system_info.get_info()[0],
                        self.system_info.get_info()[-2],
                    )
                else:
                    ip, wifi = "", ""
                Graphics.draw_header(canvas.draw, ip, wifi)
                self._draw_menu(canvas.draw, items, current_index)
                Graphics.draw_footer(canvas.draw, left_text="选择", right_text="取消")

                # 处理按键
                if wait_press(KEY_press_PIN) or wait_press(ok_PIN):
                    return current_index

                if vertical:
                    current_index = self.buttons.navigate_menu(
                        current_index, len(items), vertical=True
                    )
                else:
                    current_index = self.buttons.navigate_menu(
                        current_index, len(items), vertical=False
                    )

                if press_key(cancel_PIN):
                    wait_release(cancel_PIN)
                    return -1

            time.sleep(0.01)

    def _draw_menu(self, draw, items, current_index):
        """绘制菜单项"""
        visible_items = 8  # 可见菜单项数量

        if current_index < visible_items:
            # 当前选择在可见范围内
            for i, item in enumerate(items[:visible_items]):
                y_pos = 27 + i * 23
                if i == current_index:
                    Graphics.draw_rounded_rect(
                        draw, 8, y_pos, 223, 19, 18, COLOR_LIGHT_BLUE
                    )
                else:
                    Graphics.draw_rounded_rect(
                        draw, 8, y_pos, 223, 20, 18, COLOR_MID_BLUE
                    )
                draw.text(
                    (27, y_pos), item, font=fonts.get_font("normal"), fill=COLOR_WHITE
                )
        else:
            # 需要滚动显示
            start_index = current_index - (visible_items - 1)
            for i in range(visible_items):
                item_index = start_index + i
                y_pos = 27 + i * 23

                if i == (visible_items - 1):
                    Graphics.draw_rounded_rect(
                        draw, 8, y_pos, 223, 19, 18, COLOR_LIGHT_BLUE
                    )
                else:
                    Graphics.draw_rounded_rect(
                        draw, 8, y_pos, 223, 20, 18, COLOR_MID_BLUE
                    )

                draw.text(
                    (27, y_pos),
                    items[item_index],
                    font=fonts.get_font("normal"),
                    fill=COLOR_WHITE,
                )

    def show_system_info(self):
        """显示系统信息屏幕"""
        from system.info import SystemInfo
        from hardware.ina219 import INA219

        # system_info = SystemInfo()
        power_monitor = INA219(addr=0x43)  # 使用正确的地址

        while True:
            with self.display.lcd.create_canvas() as canvas:
                Graphics.draw_background(canvas.draw, "本机")
                if self.system_info:
                    ip, wifi = (
                        self.system_info.get_info()[0],
                        self.system_info.get_info()[-2],
                    )
                else:
                    ip, wifi = "", ""
                Graphics.draw_header(canvas.draw, ip, wifi)
                Graphics.draw_footer(canvas.draw, left_text="")

                # 信息显示区域 - 修复高度和位置
                # Graphics.draw_rounded_rect(canvas.draw, 8, 27, 223, 180, 16, COLOR_MID_BLUE)

                # 获取系统信息
                if self.system_info:
                    ip, cpu, mem, disk, wifi, temp = self.system_info.get_info()
                else:
                    ip, cpu, mem, disk, wifi, temp = ("", "", "", "", "", "")

                # 调整文本显示位置和行高
                info_lines = [
                    f"地址: {ip}",
                    wifi,
                    f"温度: {temp} °C",
                    cpu,
                    mem,
                    disk,
                    # f"电量: {self.power_monitor.get_battery_percentage()}%"  # 使用传入的power_monitor
                ]

                # 调整Y坐标起始位置和行间距
                for i, line in enumerate(info_lines):
                    canvas.draw.text(
                        (10, 35 + i * 22),
                        line,  # 从35开始，行间距22
                        font=fonts.get_font("normal"),
                        fill=COLOR_WHITE,
                    )

                if press_key(cancel_PIN) or press_key(KEY_press_PIN):
                    wait_release(cancel_PIN)
                    wait_release(KEY_press_PIN)
                    return

            time.sleep(0.01)


    def show_core_info(self):
        """显示中枢信息屏幕"""

        while True:
            with self.display.lcd.create_canvas() as canvas:
                Graphics.draw_background(canvas.draw, "中枢")
                if self.system_info:
                    ip, wifi = (
                        self.system_info.get_info()[0],
                        self.system_info.get_info()[-2],
                    )
                else:
                    ip, wifi = "", ""
                Graphics.draw_header(canvas.draw, ip, wifi)
                Graphics.draw_footer(canvas.draw, left_text="")

                # 信息显示区域 - 修复高度和位置
                # Graphics.draw_rounded_rect(canvas.draw, 8, 27, 223, 180, 16, COLOR_MID_BLUE)

                # 获取系统信息
                if self.system_info:
                    ip, temp = self.system_info.get_core_info()
                else:
                    ip, temp = ("", "")

                # 调整文本显示位置和行高
                info_lines = [
                    f"地址: {ip}",
                    f"温度: {temp} °C",
                ]

                # 调整Y坐标起始位置和行间距
                for i, line in enumerate(info_lines):
                    canvas.draw.text(
                        (10, 35 + i * 22),
                        line,  # 从35开始，行间距22
                        font=fonts.get_font("normal"),
                        fill=COLOR_WHITE,
                    )

                if press_key(cancel_PIN) or press_key(KEY_press_PIN):
                    wait_release(cancel_PIN)
                    wait_release(KEY_press_PIN)
                    return

            time.sleep(0.01)

    def show_wifi_menu(self):
        """显示WiFi菜单"""
        menu_items = ["WLAN连接"]
        current_index = 0

        while True:
            with self.display.lcd.create_canvas() as canvas:
                Graphics.draw_background(canvas.draw, "网络")
                if self.system_info:
                    ip, wifi = (
                        self.system_info.get_info()[0],
                        self.system_info.get_info()[-2],
                    )
                else:
                    ip, wifi = "", ""
                Graphics.draw_header(canvas.draw, ip, wifi)
                self._draw_menu(canvas.draw, menu_items, current_index)
                Graphics.draw_footer(canvas.draw, left_text="确定")

                if wait_press(ok_PIN) or wait_press(KEY_press_PIN):
                    if current_index == 0:
                        self.show_wifi_connection()

                current_index = self.buttons.navigate_menu(
                    current_index, len(menu_items)
                )

                if press_key(cancel_PIN):
                    wait_release(cancel_PIN)
                    return

            time.sleep(0.01)

    def show_wifi_connection(self):
        """显示WiFi连接界面"""
        from ui.keyboard import VirtualKeyboard

        keyboard = VirtualKeyboard(self.display, self.buttons)
        ssid = ""
        password = ""
        current_field = 0  # 0: SSID, 1: Password

        while True:
            with self.display.lcd.create_canvas() as canvas:
                Graphics.draw_background(canvas.draw, "WLAN")
                if self.system_info:
                    ip, wifi = (
                        self.system_info.get_info()[0],
                        self.system_info.get_info()[-2],
                    )
                else:
                    ip, wifi = "", ""
                Graphics.draw_header(canvas.draw, ip, wifi)
                Graphics.draw_footer(canvas.draw, left_text="确定", center="扫描")

                # 显示输入字段
                canvas.draw.text(
                    (8, 30),
                    "WiFi名称:",
                    font=fonts.get_font("normal"),
                    fill=COLOR_WHITE,
                )
                canvas.draw.text(
                    (8, 80),
                    "WiFi密码:",
                    font=fonts.get_font("normal"),
                    fill=COLOR_WHITE,
                )
                canvas.draw.line((8, 70, 220, 70), fill=COLOR_BLUE)
                canvas.draw.line((8, 120, 220, 120), fill=COLOR_BLUE)

                # 显示当前内容
                ssid_display = f"{ssid}<-" if current_field == 0 else ssid
                password_display = f"{password}<-" if current_field == 1 else password

                canvas.draw.text(
                    (8, 50),
                    ssid_display,
                    font=fonts.get_font("normal"),
                    fill=COLOR_WHITE,
                )
                canvas.draw.text(
                    (8, 100),
                    password_display,
                    font=fonts.get_font("normal"),
                    fill=COLOR_WHITE,
                )

                # 处理按键
                if press_key(KEY_press_PIN):
                    wait_release(KEY_press_PIN)
                    if current_field == 0:
                        ssid = keyboard.show(ssid)
                    else:
                        password = keyboard.show(password)

                if press_key(main_PIN):
                    wait_release(main_PIN)
                    # 扫描WiFi网络
                    networks = self.wifi_manager.get_visible_networks()
                    if networks:
                        selected = self.show_selection_menu("选择网络", networks)
                        if selected >= 0:
                            ssid = networks[selected]

                if press_key(KEY_up_PIN) or press_key(KEY_down_PIN):
                    current_field = 1 - current_field  # 切换字段
                    wait_release(KEY_up_PIN)
                    wait_release(KEY_down_PIN)

                if press_key(ok_PIN):
                    wait_release(ok_PIN)
                    if ssid and password:
                        self.wifi_manager.connect_to_network(ssid, password)
                        return

                if press_key(cancel_PIN):
                    wait_release(cancel_PIN)
                    return

            time.sleep(0.01)

    def show_display_settings(self):
        """显示显示设置"""
        menu_items = ["背光亮度"]
        current_index = 0

        while True:
            with self.display.lcd.create_canvas() as canvas:
                Graphics.draw_background(canvas.draw, "显示")
                if self.system_info:
                    ip, wifi = (
                        self.system_info.get_info()[0],
                        self.system_info.get_info()[-2],
                    )
                else:
                    ip, wifi = "", ""
                Graphics.draw_header(canvas.draw, ip, wifi)
                self._draw_menu(canvas.draw, menu_items, current_index)
                Graphics.draw_footer(canvas.draw, left_text="确定")

                if wait_press(ok_PIN) or wait_press(KEY_press_PIN):
                    if current_index == 0:
                        self.adjust_backlight()

                current_index = self.buttons.navigate_menu(
                    current_index, len(menu_items)
                )

                if press_key(cancel_PIN):
                    wait_release(cancel_PIN)
                    return

            time.sleep(0.01)

    def adjust_backlight(self):
        """调整背光亮度"""
        temp_level = self.display.get_backlight()

        while True:
            with self.display.lcd.create_canvas() as canvas:
                Graphics.draw_background(canvas.draw, "背光")
                if self.system_info:
                    ip, wifi = (
                        self.system_info.get_info()[0],
                        self.system_info.get_info()[-2],
                    )
                else:
                    ip, wifi = "", ""
                Graphics.draw_header(canvas.draw, ip, wifi)
                Graphics.draw_rounded_rect(
                    canvas.draw, 8, 27, 223, 19, 18, COLOR_MID_BLUE
                )
                canvas.draw.text(
                    (27, 27), "亮度", font=fonts.get_font("normal"), fill=COLOR_WHITE
                )

                # 显示亮度百分比
                percent = temp_level * 10
                canvas.draw.text(
                    (127, 27),
                    f"{percent}%",
                    font=fonts.get_font("normal"),
                    fill=COLOR_WHITE,
                )

                Graphics.draw_footer(canvas.draw, left_text="确定")

                # 调整亮度
                if press_key(KEY_left_PIN):
                    temp_level = max(1, temp_level - 1)
                    wait_release(KEY_left_PIN, 100)

                if press_key(KEY_right_PIN):
                    temp_level = min(10, temp_level + 1)
                    wait_release(KEY_right_PIN, 100)

                # 确认设置
                if press_key(ok_PIN) or press_key(KEY_press_PIN):
                    self.display.set_backlight(temp_level)
                    wait_release(ok_PIN)
                    wait_release(KEY_press_PIN)
                    return

                # 取消设置
                if press_key(cancel_PIN):
                    wait_release(cancel_PIN)
                    return

            time.sleep(0.01)
