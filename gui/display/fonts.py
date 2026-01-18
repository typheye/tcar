# -*- coding:utf-8 -*-
# 字体管理

from PIL import ImageFont
from config import *

class FontManager:
    def __init__(self):
        self.fonts = {}
        self.load_fonts()
    
    def load_fonts(self):
        """加载所有字体"""
        try:
            # 常用字体
            self.fonts['normal'] = ImageFont.truetype(FONT_NORMAL, 17)
            # 页面使用字体
            self.fonts['medium'] = ImageFont.truetype(FONT_NORMAL, 17)
            # 小字体，WiFi右下角序号使用
            self.fonts['small'] = ImageFont.truetype(FONT_MONO, 11)
            # 页面右上角时间使用字体
            self.fonts['header'] = ImageFont.truetype(FONT_MONO, 16)
            # 大字体，首页时间使用
            self.fonts['large'] = ImageFont.truetype(FONT_BOLD, 36)
            # 大字体，首页标语使用
            self.fonts['title'] = ImageFont.truetype(FONT_NORMAL, 30)
        except Exception as e:
            print(f"字体加载失败: {e}")
            # 使用默认字体作为后备
            self.fonts['normal'] = ImageFont.load_default()
            self.fonts['medium'] = ImageFont.load_default()
            self.fonts['small'] = ImageFont.load_default()
            self.fonts['header'] = ImageFont.load_default()
            self.fonts['large'] = ImageFont.load_default()
            self.fonts['title'] = ImageFont.load_default()
    
    def get_font(self, name):
        """获取指定字体"""
        return self.fonts.get(name, self.fonts['normal'])

# 全局字体管理器实例
fonts = FontManager()