# -*- coding:utf-8 -*-
# 车体自检系统

import time
from display.graphics import Graphics
from display.fonts import fonts
from utils import press_key, wait_release, wait_press, get_core_status
from config import *

class CarTest:
    def __init__(self, display, buttons, wifi_manager, system_info=None, power_monitor=None):
        self.display = display
        self.buttons = buttons
        self.wifi_manager = wifi_manager
        self.system_info = system_info
        self.power_monitor = power_monitor
        self.show_ui = 0
        self.show_ui_msg = ""
        self.show_ui_disable = False
        self.have_test = False
        
    def test_car(self):
        if not self.have_test:
            self.have_test = True
            if get_core_status():
                os.system('ssh pi@192.168.166.100 "sudo python3 /home/pi/TurboPi/HiwonderSDK/hardware_test.py"')
                self.show_ui, self.show_ui_msg, self.show_ui_disable = 0, "", False
            else:
                self.show_ui, self.show_ui_msg, self.show_ui_disable = 1, "中枢主机未连接", False
            self.have_test = False

    def show_main_ui(self):
        """显示主页"""
        
        while True:
            if self.show_ui == 0:
                with self.display.lcd.create_canvas() as canvas:
                    Graphics.draw_background(canvas.draw, "程序")
                    if self.system_info:
                        ip = self.system_info.get_info()[0]
                    else:
                        ip = ""
                    Graphics.draw_header(canvas.draw, ip, self.wifi_manager.get_interfaces())
                    Graphics.draw_footer(canvas.draw, left_text="确定")
                    
                    canvas.draw.text((10, 35), "Typheye Car 自检\n\n\n\n点击 “确定” 按钮启动检测\n\n点击 “返回” 按钮离开本页",
                        font=fonts.get_font('normal'), fill=COLOR_WHITE)

                    if wait_press(ok_PIN):
                        wait_release(ok_PIN)
                        self.show_ui, self.show_ui_msg, self.show_ui_disable = 1, "正在测试...", True

                    if press_key(cancel_PIN):
                        wait_release(cancel_PIN)
                        return
                    #return
            elif self.show_ui == 1:
                self.show_msg_screen(self.show_ui_msg, disable=self.show_ui_disable)
                
                if not self.have_test:
                    self.test_car()

            time.sleep(0.01)
    
    def show_msg_screen(self, message="提示内容", disable=False):
        """显示加载屏幕"""
        with self.display.lcd.create_canvas() as canvas:
            Graphics.draw_background(canvas.draw, "提示")
            if self.system_info:
                ip = self.system_info.get_info()[0]
            else:
                ip = ""
            Graphics.draw_header(canvas.draw, ip, self.wifi_manager.get_interfaces())
            if not disable:
                Graphics.draw_footer(canvas.draw, left_text="确定", right_text="")
            
            Graphics.draw_rounded_rect(canvas.draw, 8, 27, 219, 50, 16, COLOR_MID_BLUE)
            canvas.draw.text((30, 42), message, font=fonts.get_font('medium'), fill=COLOR_WHITE)

            if not disable and press_key(ok_PIN):
                wait_release(ok_PIN)
                self.show_ui, self.show_ui_msg, self.show_ui_disable = 0, "", False
    