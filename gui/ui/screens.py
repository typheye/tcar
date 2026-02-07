# -*- coding:utf-8 -*-
# 各界面屏幕

import time
import re
from display.graphics import Graphics
from display.fonts import fonts
from utils import press_key, wait_release, wait_press
from config import *


class ScreenManager:
    def __init__(
        self, display, buttons, system_info, network_status, wifi_manager, power_monitor
    ):
        self.display = display
        self.buttons = buttons
        self.system_info = system_info
        self.network_status = network_status
        self.wifi_manager = wifi_manager
        self.power_monitor = power_monitor
        self.show_ui = 0
        self.show_ui_msg = ""

    def show_main_screen(self):
        """显示主屏幕"""
        while True:
            if self.show_ui == 0:
                with self.display.lcd.create_canvas() as canvas:
                    Graphics.draw_background(canvas.draw, "桌面")
                    if self.system_info:
                        online, network = (
                            self.system_info.get_online(),
                            self.system_info.get_info()[-2],
                        )
                    else:
                        online, network = False, ""
                    Graphics.draw_header(canvas.draw, online, network)
                    Graphics.draw_footer(
                        canvas.draw, right_text="设置", left_text="程序", center="信息"
                    )

                    # 时间卡片
                    # self._draw_time_card(canvas.draw)

                    # 车图卡片
                    self._draw_car_card(canvas.draw)

                    # 系统状态卡片
                    self._draw_status_cards(canvas.draw)

                    # 处理按键
                    # if press_key(main_PIN):
                    #     press_time = wait_release(main_PIN)
                    #     if press_time > 1000:  # 长按关机
                    #         from system.power import PowerManager
                    #         PowerManager.show_power_off_screen(self.display, self.buttons, self.wifi_manager)

                    if wait_press(main_PIN):
                        wait_release(main_PIN)
                        self.show_ui = 1
                        self.show_ui_msg = "暂无消息"

                    if wait_press(cancel_PIN):
                        from ui.menu import MenuManager

                        menu = MenuManager(
                            self.display,
                            self.buttons,
                            self.wifi_manager,
                            self.system_info,
                            self.power_monitor,
                        )
                        menu.show_main_menu()

                    if wait_press(ok_PIN):
                        from ui.launcher import LauncherManager

                        menu = LauncherManager(
                            self.display,
                            self.buttons,
                            self.wifi_manager,
                            self.system_info,
                            self.power_monitor,
                        )
                        menu.show_main_launcher()
                        pass

                    # return
            elif self.show_ui == 1:
                self.show_msg_screen(self.show_ui_msg)

            time.sleep(0.01)

    def _draw_time_card(self, draw):
        """绘制时间卡片"""
        time_card_x, time_card_y = 20, 43
        time_card_w, time_card_h = 200, 60

        Graphics.draw_rounded_rect(
            draw, time_card_x, time_card_y, time_card_w, time_card_h, 14, COLOR_MID_BLUE
        )

        # 当前时间
        current_time = time.strftime("%H:%M", time.localtime())
        draw.text(
            (time_card_x + 48, time_card_y + 6),
            current_time,
            font=fonts.get_font("large"),
            fill=COLOR_WHITE,
        )

        # 当前日期
        current_date = time.strftime("%Y / %m / %d", time.localtime())
        draw.text(
            (time_card_x + 43, time_card_y + 38),
            current_date,
            font=fonts.get_font("normal"),
            fill=COLOR_WHITE,
        )

    def _draw_car_card(self, draw):
        """绘制车卡片"""
        # time_card_x, time_card_y = 20, 43
        # time_card_w, time_card_h = 200, 60

        # x: 20 - 220 | y: 43 - 123 | w: 200 | h: 60
        central_status, central_color, central_value, central_value_color = (
            self.network_status.get_central_status()
        )
        voltage, battery, battery_color = self.network_status.get_core_battery()

        # 警告卡片
        info1_card_x, info1_card_y = 20, 43
        info1_card_w, info1_card_h = 50, 60
        Graphics.draw_rounded_rect(
            draw,
            info1_card_x,
            info1_card_y,
            info1_card_w,
            info1_card_h,
            5,
            COLOR_MID_BLUE,
        )
        draw.text(
            (info1_card_x + 9, info1_card_y + 5),
            "警告",
            font=fonts.get_font("normal"),
            fill=COLOR_WHITE,
        )
        draw.text(
            (info1_card_x + 15, info1_card_y + info1_card_h / 2 - 5),
            "0",
            font=fonts.get_font("large"),
            fill=COLOR_GREEN,
        )

        # 车图
        car_card_x, car_card_y = 80, 43
        car_card_w, car_card_h = 80, 60
        Graphics.car(
            draw,
            car_card_x,
            car_card_y,
            car_card_w,
            car_card_h,
            status_core=self.network_status.get_ping_status(),
            status_pyz=self.network_status.get_camera_status(),
        )

        # 电压显示
        voltage_card_x, voltage_card_y = 170, 43
        voltage_card_w, voltage_card_h = 50, 30
        Graphics.draw_rounded_rect(
            draw,
            voltage_card_x,
            voltage_card_y,
            voltage_card_w,
            voltage_card_h,
            5,
            COLOR_MID_BLUE,
        )
        draw.text(
            (voltage_card_x + 6, voltage_card_y + 5),
            voltage,
            font=fonts.get_font("normal"),
            fill=COLOR_WHITE,
        )

        # 电池显示
        bettery_card_x, bettery_card_y = 170, 78
        bettery_card_w, bettery_card_h = 50, 25
        Graphics.battery(
            draw,
            bettery_card_x,
            bettery_card_y,
            bettery_card_w,
            bettery_card_h,
            battery,
            battery_color,
        )

    def _draw_status_cards(self, draw):
        """绘制状态卡片"""
        card_w, card_h = 90, 70
        gap = 20
        card1_x, card1_y = 20, 120  # 路由卡片
        card2_x, card2_y = card1_x + card_w + gap, 120  # 中枢卡片

        # 获取路由和中枢状态
        route_status, route_color, route_value, route_value_color = (
            self.network_status.get_route_status()
        )
        central_status, central_color, central_value, central_value_color = (
            self.network_status.get_central_status()
        )

        # 路由卡片
        Graphics.draw_rounded_rect(
            draw, card1_x, card1_y, card_w, card_h, 5, COLOR_MID_BLUE
        )
        draw.text(
            (card1_x + 15, card1_y + 8),
            route_value,
            font=fonts.get_font("large"),
            fill=route_value_color,
        )
        draw.text(
            (card1_x + 15, card1_y + 43),
            "路由",
            font=fonts.get_font("normal"),
            fill=COLOR_WHITE,
        )
        draw.text(
            (card1_x + 52, card1_y + 43),
            route_status,
            font=fonts.get_font("normal"),
            fill=route_color,
        )

        # 中枢卡片
        Graphics.draw_rounded_rect(
            draw, card2_x, card2_y, card_w, card_h, 5, COLOR_MID_BLUE
        )
        draw.text(
            (card2_x + 15, card2_y + 8),
            central_value,
            font=fonts.get_font("large"),
            fill=central_value_color,
        )
        draw.text(
            (card2_x + 15, card2_y + 43),
            "中枢",
            font=fonts.get_font("normal"),
            fill=COLOR_WHITE,
        )
        draw.text(
            (card2_x + 52, card2_y + 43),
            central_status,
            font=fonts.get_font("normal"),
            fill=central_color,
        )

    def show_msg_screen(self, message="提示内容"):
        """显示加载屏幕"""
        with self.display.lcd.create_canvas() as canvas:
            Graphics.draw_background(canvas.draw, "提示")
            if self.system_info:
                online, network = (
                    self.system_info.get_online(),
                    self.system_info.get_info()[-2],
                )
            else:
                online, network = False, ""
            Graphics.draw_header(canvas.draw, online, network)
            Graphics.draw_footer(canvas.draw, left_text="确定", right_text="")

            Graphics.draw_rounded_rect(canvas.draw, 6, 27, 225, 50, 16, COLOR_MID_BLUE)
            canvas.draw.text(
                (30, 42), message, font=fonts.get_font("medium"), fill=COLOR_WHITE
            )

            if press_key(ok_PIN):
                wait_release(ok_PIN)
                self.show_ui = 0
                self.show_ui_msg = ""
