# -*- coding:utf-8 -*-
# 电源管理

import os
import time
from display.fonts import fonts
from utils import log
from config import *

class PowerManager:
    @staticmethod
    def show_power_off_screen(display, buttons, wifi_manager, system_info=None, power_monitor=None):
        from ui.menu import MenuManager
        menu = MenuManager(display, buttons, wifi_manager, system_info, power_monitor)
        
        options = ["是", "否"]
        choice = menu.show_selection_menu("重启", options)
        
        if choice == 0:  # 选择"是"
            # 显示黑屏
            with display.lcd.create_canvas() as canvas:
                canvas.draw.rectangle((0, 0, 240, 240), fill="BLACK")
            log(3, "系统重启中...")
            time.sleep(2)
            PowerManager.reboot()
            return True
        return False

    @staticmethod
    def reboot():
        """重启系统"""
        log(3, "系统重启")
        os.system("sudo reboot")
        time.sleep(20)  # 等待重启
        
    @staticmethod
    def shutdown():
        """关机"""
        log(3, "系统关机")
        os.system("sudo poweroff")