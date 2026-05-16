# -*- coding:utf-8 -*-
# 按钮控制

import time
import RPi.GPIO as GPIO
from server.gui.public.utils import wait_release, wait_press, press_key
from media.config import *

class ButtonManager:
    def __init__(self):
        self.setup_buttons()
        
    def setup_buttons(self):
        """初始化按钮"""
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(KEY_up_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(KEY_down_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(KEY_left_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(KEY_right_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(KEY_press_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(ok_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(main_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(cancel_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    def get_key_function(self):
        """获取按键功能映射"""
        return {
            'up': KEY_up_PIN,
            'down': KEY_down_PIN,
            'left': KEY_left_PIN,
            'right': KEY_right_PIN,
            'center': KEY_press_PIN,
            'ok': ok_PIN,
            'menu': main_PIN,
            'cancel': cancel_PIN
        }
    
    def wait_for_key(self, key_name, timeout=None):
        """等待特定按键"""
        pin = self.get_key_function()[key_name]
        start_time = time.time()
        
        while timeout is None or (time.time() - start_time) < timeout:
            if press_key(pin):
                wait_release(pin)
                return True
            time.sleep(0.01)
        return False
    
    def get_pressed_key(self):
        """获取当前按下的按键"""
        for key_name, pin in self.get_key_function().items():
            if press_key(pin):
                return key_name
        return None
    
    def navigate_menu(self, current_index, max_index, vertical=True):
        """菜单导航"""
        if vertical:
            if press_key(KEY_up_PIN):
                wait_release(KEY_up_PIN, 80)
                return (current_index - 1) % max_index
            if press_key(KEY_down_PIN):
                wait_release(KEY_down_PIN, 80)
                return (current_index + 1) % max_index
        else:
            if press_key(KEY_left_PIN):
                wait_release(KEY_left_PIN, 80)
                return (current_index - 1) % max_index
            if press_key(KEY_right_PIN):
                wait_release(KEY_right_PIN, 80)
                return (current_index + 1) % max_index
        return current_index
    
    def cleanup(self):
        """清理GPIO资源"""
        GPIO.cleanup()