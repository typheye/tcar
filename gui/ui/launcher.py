# -*- coding:utf-8 -*-
# 菜单系统

import os
import time
from display.graphics import Graphics
from display.fonts import fonts
from utils import press_key, wait_release, wait_press
from config import *


class LauncherManager:
    def __init__(
        self, display, buttons, wifi_manager, system_info=None, power_monitor=None
    ):
        self.display = display
        self.buttons = buttons
        self.wifi_manager = wifi_manager
        self.system_info = system_info
        self.power_monitor = power_monitor

    def show_main_launcher(self):
        """显示主菜单"""
        menu_items = ["车辆自检", "云台控制", "外接相机"]
        current_index = 0

        while True:
            with self.display.lcd.create_canvas() as canvas:
                Graphics.draw_background(canvas.draw, "程序")
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
                        from funs.carTest import CarTest

                        car_test = CarTest(
                            self.display,
                            self.buttons,
                            self.wifi_manager,
                            self.system_info,
                            self.power_monitor,
                        )
                        car_test.show_main_ui()
                    elif current_index == 1:
                        from funs.ptzOpera import PTZOpera

                        ptz_opera = PTZOpera(
                            self.display,
                            self.buttons,
                            self.wifi_manager,
                            self.system_info,
                            self.power_monitor,
                        )
                        ptz_opera.show_main_ui()
                    elif current_index == 2:
                        from funs.camBox import CamBox

                        cam_box = CamBox(
                            self.display,
                            self.buttons,
                            self.wifi_manager,
                            self.system_info,
                            self.power_monitor,
                        )
                        cam_box.show_main_ui()

                current_index = self.buttons.navigate_menu(
                    current_index, len(menu_items)
                )

                if press_key(cancel_PIN):
                    wait_release(cancel_PIN)
                    return

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
                        draw, 8, y_pos, 219, 19, 18, COLOR_LIGHT_BLUE
                    )
                else:
                    Graphics.draw_rounded_rect(
                        draw, 8, y_pos, 219, 20, 18, COLOR_MID_BLUE
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
                        draw, 8, y_pos, 219, 19, 18, COLOR_LIGHT_BLUE
                    )
                else:
                    Graphics.draw_rounded_rect(
                        draw, 8, y_pos, 219, 20, 18, COLOR_MID_BLUE
                    )

                draw.text(
                    (27, y_pos),
                    items[item_index],
                    font=fonts.get_font("normal"),
                    fill=COLOR_WHITE,
                )
