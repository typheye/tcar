# -*- coding:utf-8 -*-
# 车体自检系统

import time
from display.graphics import Graphics
from display.fonts import fonts
from utils import press_key, wait_release, wait_press, get_core_status, log
from config import *
from system.power import PowerManager

class CarReboot:
    def __init__(self, display, buttons, wifi_manager, system_info=None, power_monitor=None):
        self.display = display
        self.buttons = buttons
        self.wifi_manager = wifi_manager
        self.system_info = system_info
        self.power_monitor = power_monitor

        # 消息提示框
        self.show_ui = 0
        self.show_ui_msg = ""
        self.show_ui_disable = False
        
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
                    
                    canvas.draw.text((10, 35), "重启Typheye Car中枢？\n本机也将重启！\n\n\n点击 “确定” 按钮执行重启\n\n点击 “返回” 按钮离开本页",
                        font=fonts.get_font('normal'), fill=COLOR_WHITE)

                    if wait_press(ok_PIN):
                        wait_release(ok_PIN)

                        if get_core_status():
                            with self.display.lcd.create_canvas() as canvas:
                                canvas.draw.rectangle((0, 0, 240, 240), fill="BLACK")
                            os.system('ssh pi@192.168.166.100 "sudo reboot" &')
                            log(3, "系统重启中...")
                            time.sleep(2)
                            PowerManager.reboot()
                        else:
                            self.show_ui, self.show_ui_msg, self.show_ui_disable = 1, "中枢主机未连接", False

                    if press_key(cancel_PIN):
                        wait_release(cancel_PIN)
                        return
                    #return
            elif self.show_ui == 1:
                self.show_msg_screen(self.show_ui_msg, disable=self.show_ui_disable)
                    
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
    