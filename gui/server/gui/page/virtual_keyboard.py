# -*- coding:utf-8 -*-
# 虚拟键盘
import time

from server.gui.public.graphics import Graphics
from server.gui.public.font_manager import fonts
from server.gui.public.utils import press_key, wait_release
from media.config import *
from hardware.buttons import ButtonManager

class VirtualKeyboard:
    def __init__(self, display, buttons):
        self.display = display
        self.buttons = buttons
        
    def show(self, initial_text=""):
        """显示虚拟键盘"""
        text = initial_text
        cursor_pos = [0, 0]  # 行, 列
        
        # 键盘布局
        keyboard_layout = [
            ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', 'a', 'b'],
            ['c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n'],
            ['o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z'],
            ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L'],
            ['M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X'],
            ['Y', 'Z', '`', '~', '!', '@', '#', '$', '%', '^', '&', '*'],
            ['(', ')', '_', '+', '-', '=', '{', '}', '|', '[', ']', '\\'],
            [':', '"', ';', "'", ',', '.', '/', '<', '>', '?', " ", " "]
        ]
        
        while True:
            with self.display.lcd.create_canvas() as canvas:
                Graphics.draw_background(canvas.draw, "输入")
                Graphics.draw_footer(canvas.draw, center="删除")
                
                # 显示当前文本
                canvas.draw.line((8, 42, 220, 42), fill=COLOR_BLUE)
                canvas.draw.text((8, 20), f"{text}<-", font=fonts.get_font('normal'), fill=COLOR_BLUE)
                
                # 绘制键盘
                self._draw_keyboard(canvas.draw, keyboard_layout, cursor_pos)
                
                # 处理按键输入
                current_char = keyboard_layout[cursor_pos[1]][cursor_pos[0]]
                
                # 方向键导航
                if press_key(KEY_up_PIN):
                    cursor_pos[1] = (cursor_pos[1] - 1) % len(keyboard_layout)
                    wait_release(KEY_up_PIN, 80)
                if press_key(KEY_down_PIN):
                    cursor_pos[1] = (cursor_pos[1] + 1) % len(keyboard_layout)
                    wait_release(KEY_down_PIN, 80)
                if press_key(KEY_left_PIN):
                    cursor_pos[0] = (cursor_pos[0] - 1) % len(keyboard_layout[0])
                    wait_release(KEY_left_PIN, 80)
                if press_key(KEY_right_PIN):
                    cursor_pos[0] = (cursor_pos[0] + 1) % len(keyboard_layout[0])
                    wait_release(KEY_right_PIN, 80)
                
                # 选择字符
                if press_key(KEY_press_PIN):
                    text += current_char
                    wait_release(KEY_press_PIN)
                    log(3, "键盘输入:", current_char)
                
                # 删除字符
                if press_key(main_PIN):
                    text = text[:-1] if text else ""
                    wait_release(main_PIN)
                    log(3, "删除字符")
                
                # 确认输入
                if press_key(ok_PIN):
                    wait_release(ok_PIN)
                    log(3, "确认输入:", text)
                    return text
                
                # 取消输入
                if press_key(cancel_PIN):
                    wait_release(cancel_PIN)
                    log(3, "取消输入，返回:", initial_text)
                    return initial_text
                
            time.sleep(0.01)
    
    def _draw_keyboard(self, draw, layout, cursor_pos):
        """绘制键盘布局"""
        for row_idx, row in enumerate(layout):
            for col_idx, char in enumerate(row):
                x = col_idx * 18 + 11
                y = 45 + row_idx * 20
                
                # 高亮当前选中的字符
                if row_idx == cursor_pos[1] and col_idx == cursor_pos[0]:
                    Graphics.draw_rounded_rect(draw, x, y, 16, 18, 5, COLOR_LIGHT_BLUE)
                else:
                    Graphics.draw_rounded_rect(draw, x, y, 16, 18, 5)
                
                draw.text((x + 4, y), char, font=fonts.get_font('normal'), fill=COLOR_WHITE)