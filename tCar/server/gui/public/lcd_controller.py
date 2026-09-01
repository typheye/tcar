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
        self._low_battery_provider = None
        self._low_battery_image = None

    def set_low_battery_provider(self, provider):
        self._low_battery_provider = provider

    def _low_battery_active(self):
        try:
            return bool(self._low_battery_provider and self._low_battery_provider())
        except Exception:
            return False

    def _get_low_battery_image(self):
        if self._low_battery_image is None:
            # Use the approved artwork itself so its proportions, cold-white
            # halo and warm low-charge glow survive exactly as designed.
            artwork_path = "./media/low_battery.png"
            try:
                image = Image.open(artwork_path).convert("RGB")
                if image.size == (SCREEN_WIDTH, SCREEN_HEIGHT):
                    self._low_battery_image = image
                else:
                    resampling = getattr(Image, "Resampling", Image).LANCZOS
                    self._low_battery_image = image.resize(
                        (SCREEN_WIDTH, SCREEN_HEIGHT), resampling
                    )
            except (OSError, ValueError):
                # Fail safely to a black screen if the artwork is damaged.
                self._low_battery_image = Image.new(
                    "RGB", (SCREEN_WIDTH, SCREEN_HEIGHT), COLOR_BLACK
                )
        return self._low_battery_image

    def _output_image(self, image):
        return self._get_low_battery_image() if self._low_battery_active() else image
        
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
                output = self.lcd._output_image(self.image)
                self.lcd.device.ShowImage(output, 0, 0)
                self.lcd.current_image = output
                pass

        return Canvas(self)
    
    def clear(self):
        """清屏"""
        if self._low_battery_active():
            output = self._get_low_battery_image()
            self.device.ShowImage(output, 0, 0)
            self.current_image = output
        else:
            self.device.clear()
        
    def show_image(self, image, x=0, y=0):
        """显示图像"""
        output = self._output_image(image)
        if output is not image:
            x, y = 0, 0
        self.device.ShowImage(output, x, y)
        self.current_image = output

    def show_image_fast(self, image, cam_fps=0, disp_fps=0):
        """显示图像"""
        output = self._output_image(image)
        if output is not image:
            # Do not let the fast camera path add diagnostics over the lock screen.
            cam_fps, disp_fps = 0, 0
        self.device.ShowImageFast(output, cam_fps=cam_fps, disp_fps=disp_fps)
        self.current_image = output
        
    def show_logo(self):
        """显示启动Logo"""
        with self.create_canvas() as canvas:
            canvas.draw.rectangle((0, 0, SCREEN_WIDTH, SCREEN_HEIGHT), fill=COLOR_BLACK)
            try:
                img = Image.open("./media/splash.png").convert("RGBA")
                if img.size != (SCREEN_WIDTH, SCREEN_HEIGHT):
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
