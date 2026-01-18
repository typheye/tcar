# -*- coding:utf-8 -*-
import time
import os
import threading
from display.graphics import Graphics
from display.fonts import fonts
from utils import press_key, wait_release, wait_press, get_core_status
from config import *

class PTZOpera:
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
        
        # 控制状态
        self.control_states = {
            1: {'active': False, 'direction': 0, 'last_cmd': ''},
            2: {'active': False, 'direction': 0, 'last_cmd': ''}
        }
    
    def send_control_command(self, servo_id, active, direction=0):
        """发送连续控制命令"""
        # 构建SSH命令
        direction_str = str(direction)
        active_str = "1" if active else "0"
        
        cmd = f'''ssh pi@192.168.166.100 "sudo python3 /home/pi/TurboPi/HiwonderSDK/pyz_opera.py \
--servo {servo_id} \
--control \
--direction {direction_str} \
--speed 20"'''
        
        # 只发送变化的命令
        current_cmd = f"{servo_id}:{active}:{direction}"
        if self.control_states[servo_id]['last_cmd'] != current_cmd:
            os.system(cmd)
            self.control_states[servo_id]['last_cmd'] = current_cmd
            self.control_states[servo_id]['active'] = active
            self.control_states[servo_id]['direction'] = direction
    
    def show_main_ui(self):
        """显示云台控制界面 - 连续控制版本"""

        if get_core_status():
            # 初始化
            os.system('ssh pi@192.168.166.100 "sudo python3 /home/pi/TurboPi/HiwonderSDK/servo_daemon.py" &')
        else:
            self.show_ui, self.show_ui_msg, self.show_ui_disable = 1, "中枢主机未连接", False
        
        while True:
            if self.show_ui == 0:
                with self.display.lcd.create_canvas() as canvas:
                    Graphics.draw_background(canvas.draw, "程序")
                    if self.system_info:
                        ip = self.system_info.get_info()[0]
                    else:
                        ip = ""
                    Graphics.draw_header(canvas.draw, ip, self.wifi_manager.get_interfaces())
                    Graphics.draw_footer(canvas.draw, left_text="重置")
                    
                    # 显示控制说明
                    canvas.draw.text((10, 35), "Typheye Car 云台控制\n移动摇杆以操作云台\n\n\n点击 “重置” 按钮复原位置\n\n点击 “返回” 按钮离开本页",
                        font=fonts.get_font('normal'), fill=COLOR_WHITE)
                    
                    # 确定按钮 - 重置位置
                    if wait_press(ok_PIN):
                        wait_release(ok_PIN)
                        if get_core_status():
                            os.system('ssh pi@192.168.166.100 "sudo python3 /home/pi/TurboPi/HiwonderSDK/pyz_opera.py --reset"')
                            # 重置控制状态
                            for servo_id in [1, 2]:
                                self.control_states[servo_id]['active'] = False
                                self.control_states[servo_id]['last_cmd'] = ''
                        else:
                            self.show_ui, self.show_ui_msg, self.show_ui_disable = 1, "中枢主机未连接", False
                    
                    # 返回按钮
                    if press_key(cancel_PIN):
                        wait_release(cancel_PIN)
                        # 停止所有控制
                        for servo_id in [1, 2]:
                            if self.control_states[servo_id]['active']:
                                self.send_control_command(servo_id, False, 0)
                        return
                    
                    # 检查摇杆状态并发送控制命令
                    control_updated = False
                    
                    # 舵机1控制（上下）
                    if press_key(KEY_up_PIN):
                        if not self.control_states[1]['active'] or self.control_states[1]['direction'] != -1:
                            self.send_control_command(1, True, -1)  # 向上
                            control_updated = True
                    elif press_key(KEY_down_PIN):
                        if not self.control_states[1]['active'] or self.control_states[1]['direction'] != 1:
                            self.send_control_command(1, True, 1)   # 向下
                            control_updated = True
                    elif self.control_states[1]['active']:  # 没有按下但之前是活动状态
                        self.send_control_command(1, False, 0)  # 停止
                        control_updated = True
                    
                    # 舵机2控制（左右）
                    if press_key(KEY_left_PIN):
                        if not self.control_states[2]['active'] or self.control_states[2]['direction'] != 1:
                            self.send_control_command(2, True, 1)   # 向左
                            control_updated = True
                    elif press_key(KEY_right_PIN):
                        if not self.control_states[2]['active'] or self.control_states[2]['direction'] != -1:
                            self.send_control_command(2, True, -1)  # 向右
                            control_updated = True
                    elif self.control_states[2]['active']:  # 没有按下但之前是活动状态
                        self.send_control_command(2, False, 0)  # 停止
                        control_updated = True
                    
                    # 如果有控制更新，稍微延迟以避免过于频繁的SSH调用
                    if control_updated:
                        time.sleep(0.05)
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