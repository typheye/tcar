# -*- coding:utf-8 -*-
# LCD显示控制

import time
import RPi.GPIO as GPIO
from server.gui.page.power_manager import PowerManager
import spidev as SPI  # 添加SPI导入
from PIL import Image, ImageDraw
from hardware.st7789 import ST7789
from media.config import *
from server.gui.public.graphics import Graphics
from server.gui.public.font_manager import fonts
from server.gui.public.utils import press_key, wait_release, wait_press, log

class LCDController:
    def __init__(self, device):
        self.device = device
        self.canvas = None
        self.current_image = None
        
    def create_canvas(self):
        """创建画布上下文管理器"""
        class Canvas:
            def __init__(self, lcd_controller):
                self.lcd = lcd_controller
                self.image = Image.new("RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), COLOR_BLACK)
                self.draw = ImageDraw.Draw(self.image)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.lcd.device.ShowImage(self.image, 0, 0)
                self.lcd.current_image = self.image
                pass

        return Canvas(self)
    
    def clear(self):
        """清屏"""
        self.device.clear()
        
    def show_image(self, image, x=0, y=0):
        """显示图像"""
        self.device.ShowImage(image, x, y)

    def show_image_fast(self, image, cam_fps=0, disp_fps=0):
        """显示图像"""
        self.device.ShowImageFast(image, cam_fps=cam_fps, disp_fps=disp_fps)
        
    def show_logo(self):
        """显示启动Logo"""
        with self.create_canvas() as canvas:
            canvas.draw.rectangle((0, 0, SCREEN_WIDTH, SCREEN_HEIGHT), fill=COLOR_BLACK)
            try:
                img = Image.open("/home/pi/gui/system/media/splash.png").convert("RGBA")
                img = img.resize((SCREEN_WIDTH, SCREEN_HEIGHT), Image.ANTIALIAS)
                canvas.draw.bitmap((0, 0), img, fill=None)
            except Exception as e:
                pass
        
    def show_startup_animation(self):
        """显示启动动画"""
        with self.create_canvas() as canvas:
            canvas.draw.rectangle((0, 0, SCREEN_WIDTH, SCREEN_HEIGHT), fill=COLOR_BLACK)
            text = "Typheye Car"
            w, h = canvas.draw.textsize(text, font=fonts.get_font('title'))
            canvas.draw.text(((SCREEN_WIDTH - w) // 2, (SCREEN_HEIGHT - h) // 2), 
                           text, font=fonts.get_font('title'), fill=COLOR_WHITE)
        time.sleep(1)

class DisplayManager:
    def __init__(self):
        # 创建SPI设备实例
        spi_dev = SPI.SpiDev(bus, device_pin)
        self.device = ST7789(spi=spi_dev, rst=RST, dc=DC, bl=BL)
        self.device.Init()
        self.device.clear()
        
        self.lcd = LCDController(self.device)
        self.backlight_level = 10  # 默认亮度级别（1-10）
        self.setup_backlight()
        
    def setup_backlight(self):
        """设置背光控制"""
        GPIO.setup(BL, GPIO.OUT)
        self.pwm_bl = GPIO.PWM(BL, 10000)  # 10kHz
        self.pwm_bl.start(self.backlight_level * 10)  # 10-100
        
    def set_backlight(self, level):
        """设置背光亮度"""
        level = max(1, min(10, level))  # 限制在1-10范围内
        self.backlight_level = level
        self.pwm_bl.ChangeDutyCycle(level * 10)
        
    def get_backlight(self):
        """获取当前背光级别"""
        return self.backlight_level
    
    def get_device(self):
        return self.device
        
    def cleanup(self):
        """清理资源"""
        self.pwm_bl.stop()
        GPIO.cleanup()