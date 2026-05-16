# -*- coding:utf-8 -*-
# 各界面屏幕

import time
import re
from server.gui.public.graphics import Graphics
from server.gui.public.font_manager import fonts
from server.gui.public.utils import press_key, wait_release, wait_press
from media.config import *


class ScreenManager:
    def __init__(
        self, display, buttons, system_info, network_status, power_monitor
    ):
        self.display = display
        self.buttons = buttons
        self.system_info = system_info
        self.network_status = network_status
        self.power_monitor = power_monitor

    def show_main_screen(self):
        """显示主屏幕"""
        while True:
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
                Graphics.draw_footer(canvas.draw, right_text="设置", left_text="程序")

                # 车图卡片
                self._draw_car_card(canvas.draw, online)

                # 系统状态卡片
                self._draw_status_cards(canvas.draw)

                if wait_press(cancel_PIN):
                    from server.gui.page.menu_manager import MenuManager

                    menu = MenuManager(
                        self.display,
                        self.buttons,
                        self.system_info,
                        self.power_monitor,
                    )
                    menu.show_main_menu()

                if wait_press(ok_PIN):
                    from server.gui.page.app_home import AppHome

                    menu = AppHome(
                        self.display,
                        self.buttons,
                        self.system_info,
                        self.power_monitor,
                    )
                    menu.show_main_launcher()
                    pass

                # return

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

    def _draw_car_card(self, draw, network = False):
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
        draw.rectangle(
            (
                info1_card_x + 8,
                info1_card_y + 35,
                info1_card_x + 8 + 34,
                info1_card_y + 35 + 15,
            ),
            outline=COLOR_DARK_BLUE,
            width=1,
            fill=COLOR_GREEN if network else COLOR_YELLOW,
        )
        draw.text(
            (info1_card_x + 11, info1_card_y + 7),
            "NET",
            font=fonts.get_font("normal"),
            fill=COLOR_WHITE,
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
