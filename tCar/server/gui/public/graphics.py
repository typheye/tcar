# -*- coding:utf-8 -*-
# 图形元素绘制

from PIL import ImageDraw
from server.gui.public.font_manager import fonts
from media.config import *

class Graphics:
    @staticmethod
    def signal(draw, left=0, top=0, width=10, height=8, signal=100):
        """绘制信号强度图标"""
        color = COLOR_BLUE if signal > 0 else COLOR_MID_BLUE

        tx_w = width / 3 * 2 + 2
        tx_h = height
        draw.polygon(
            [
                (left, top),
                (left + tx_w, top),
                (left + tx_w / 2, top + tx_h / 2),
                (left, top),
                (left + tx_w / 2, top),
                (left + tx_w / 2, top + tx_h),
                (left + tx_w / 2, top),
            ],
            outline=color,
            fill=color,
        )

        draw.text(
            (left + 16, top + 7),
            "" if signal > 0 else "E",
            font=fonts.get_font("small"),
            fill=COLOR_MID_BLUE,
        )

        signal = signal if signal > 0 else 30
        for f in range(5):
            if not f * 25 < signal:
                break
            draw.rectangle(
                (
                    left + width / 2 + 1 + 3 * f,
                    top + height - height * 0.25 * f,
                    left + width / 2 + 2 + 3 * f,
                    top + height,
                ),
                fill=color,
            )

    def eth(draw, left=0, top=0, width=20, height=17, connected=True):
        """使用draw.arc的弧线连接版本"""
        color = COLOR_BLUE if connected else COLOR_MID_BLUE

        rect_w = 9
        rect_h = 7
        half_w = rect_w // 2
        half_h = rect_h // 2

        # 顶部矩形
        top_x = left + width // 2
        top_y = top + 3

        draw.rectangle(
            [top_x - half_w, top_y - half_h, top_x + half_w, top_y + half_h],
            fill=1,
            outline=color,
        )

        # 左下矩形
        left_x = left + 4
        left_y = top + height - 3

        draw.rectangle(
            [left_x - half_w, left_y - half_h, left_x + half_w, left_y + half_h],
            fill=color,
            outline=color,
        )

        # 右下矩形
        right_x = left + width - 5
        right_y = top + height - 3

        draw.rectangle(
            [right_x - half_w, right_y - half_h, right_x + half_w, right_y + half_h],
            fill=color,
            outline=color,
        )

        # 弧线边界框
        arc_left = left_x + half_w + 1
        arc_right = right_x - half_w - 1
        arc_top = top_y + half_h + 2
        arc_bottom = (left_y + right_y) / 2 - 1

        # 绘制向下的弧线（180°到360°）
        # 注意：PIL的arc是从3点钟方向开始，0°在右侧
        # 我们需要从左侧开始（180°）到右侧结束（0°/360°）
        draw.arc(
            [arc_left, arc_top, arc_right, arc_bottom],
            start=180,  # 从左侧开始
            end=0,  # 到右侧结束（0°和360°相同）
            fill=color,
            width=1,
        )

        # 连接线：从顶部矩形到弧线
        draw.line([top_x, top_y + half_h, top_x, arc_top], fill=color, width=1)

        # 连接线：从弧线两端到底部矩形
        draw.line(
            [arc_left, arc_bottom, left_x + half_w, left_y - half_h],
            fill=color,
            width=1,
        )

        draw.line(
            [arc_right, arc_bottom, right_x - half_w, right_y - half_h],
            fill=color,
            width=1,
        )

    @staticmethod
    def battery(
        draw,
        left=170,
        top=78,
        width=50,
        height=25,
        battery=100,
        battery_color=COLOR_BLUE,
    ):
        """绘制电池图标"""

        # 电池轮廓 - 厚度3px
        draw.rectangle(
            (left + 1, top, left + width, top + height),
            outline=COLOR_MID_BLUE,
            width=2,
            fill=1,
        )

        # 电池正极（右侧凸起）- 在轮廓外留2px空隙，向内移动2px
        draw.rectangle(
            (
                left + width + 2,
                top + height / 3,  # 从轮廓右侧开始+2px空隙
                left + width + 2 + 2,
                top + height / 3 * 2,
            ),  # 宽度1px
            fill=COLOR_MID_BLUE,
        )

        # 电池电量填充（内部白色部分）
        battery = battery / 100.0
        aviable = width - 4

        # 调整内部填充区域，考虑轮廓厚度和空隙
        # 左侧和上下各留轮廓厚度(3px) + 空隙(2px) = 5px
        # 右侧也留同样的空间
        if battery > 0:
            draw.rectangle(
                (
                    left + 5,
                    top + 5,
                    left + width - 4 - aviable * (1 - battery),  # 从右侧开始计算
                    top + height - 5,
                ),
                fill=battery_color,
            )

    # @staticmethod
    # def car(draw, left=80, top=43, width=80, height=60):
    #     """绘制车图"""

    #     # 车轮廓图边界 - 厚度1px
    #     draw.rectangle((left, top, left + width, top + height),
    #                 outline=COLOR_WHITE, width = 1, fill=1)

    @staticmethod
    def car(
        draw, left=80, top=43, width=80, height=60, status_core=False, status_pyz=False
    ):
        """绘制车图（3:2比例，居中显示）"""

        # 1. 绘制布局边界
        # draw.rectangle((left, top, left + width, top + height),
        #             outline=COLOR_MID_BLUE, width=1, fill=1)

        # 2. 计算最大的3:2比例车轮廓边界（在布局边界内居中显示）
        aspect_ratio = 4 / 3.8  # 5:3比例

        # 计算两种可能的尺寸方案：
        # 方案A：以布局高度为基准计算宽度
        car_width_by_height = round(height * aspect_ratio)
        # 方案B：以布局宽度为基准计算高度
        car_height_by_width = round(width / aspect_ratio)

        # 选择最大的3:2矩形
        if car_width_by_height <= width:
            # 以高度为基准，宽度可以完全放入
            car_width = car_width_by_height
            car_height = height
            # 居中计算X偏移
            offset_x = (width - car_width) // 2
            offset_y = 0
        else:
            # 以宽度为基准，高度可以完全放入
            car_width = width
            car_height = car_height_by_width
            # 居中计算Y偏移
            offset_x = 0
            offset_y = (height - car_height) // 2

        # 计算车轮廓边界的位置（在布局边界内居中）
        car_outer_left = left + offset_x
        car_outer_top = top + offset_y
        car_outer_width = car_width
        car_outer_height = car_height

        # 3. 绘制车轮廓图边界（绿色轮廓）
        # draw.rectangle((car_outer_left, car_outer_top,
        #                 car_outer_left + car_outer_width,
        #                 car_outer_top + car_outer_height),
        #             outline=COLOR_GREEN, width=1, fill=1)

        # 车体的位置（在车轮廓内部）
        car_left = car_outer_left
        car_top = car_outer_top
        car_inner_width = car_outer_width
        car_inner_height = car_outer_height

        # 5. 绘制车体（白色矩形）

        draw.rectangle(
            (
                car_left,
                car_top + round(car_inner_height * 0.25),
                car_left + car_inner_width,
                car_top
                + round(car_inner_height * 0.25)
                + round(car_inner_height * 0.5),
            ),
            outline=COLOR_WHITE,
            width=round(car_inner_height * 0.01),
            fill=COLOR_GREY,
        )

        # 6. 计算轮子尺寸（基于车体大小的比例）
        wheel_width = car_inner_width // 3  # 轮子宽度为车体宽的1/3
        wheel_height = car_inner_height // 5.5  # 轮子高度为车体高的1/5
        wheel_inset = round(car_inner_height * 0.05)  # 轮子向内偏移量

        # 7. 绘制四个轮子（白色矩形，显示在车体内部）
        # 左上轮
        draw.rectangle(
            (
                car_left + wheel_inset,
                car_top,
                car_left + wheel_inset + wheel_width,
                car_top + wheel_height,
            ),
            fill=COLOR_WHITE2,
        )

        # 右上轮
        draw.rectangle(
            (
                car_left + car_inner_width - wheel_inset - wheel_width,
                car_top,
                car_left + car_inner_width - wheel_inset,
                car_top + wheel_height,
            ),
            fill=COLOR_WHITE2,
        )

        # 左下轮
        draw.rectangle(
            (
                car_left + wheel_inset,
                car_top + car_inner_height - wheel_height,
                car_left + wheel_inset + wheel_width,
                car_top + car_inner_height,
            ),
            fill=COLOR_WHITE2,
        )

        # 右下轮
        draw.rectangle(
            (
                car_left + car_inner_width - wheel_inset - wheel_width,
                car_top + car_inner_height - wheel_height,
                car_left + car_inner_width - wheel_inset,
                car_top + car_inner_height,
            ),
            fill=COLOR_WHITE2,
        )

        # 超声波
        draw.rectangle(
            (
                car_left + car_inner_width,
                car_top + round(car_inner_height * 0.35),
                car_left + car_inner_width + round(car_inner_width * 0.10),
                car_top
                + round(car_inner_height * 0.35)
                + round(car_inner_height * 0.3),
            ),
            outline=COLOR_WHITE,
            width=round(car_inner_height * 0.01),
            fill=COLOR_MID_BLUE,
        )

        # 主机
        draw.rectangle(
            (
                car_left + round(car_inner_height * 0.07),
                car_top + round(car_inner_height * 0.35),
                car_left
                + round(car_inner_height * 0.07)
                + round(car_inner_height * 0.3),
                car_top
                + round(car_inner_height * 0.35)
                + round(car_inner_height * 0.3),
            ),
            outline=COLOR_MID_BLUE,
            width=round(car_inner_height * 0.02),
            fill=COLOR_GREEN if status_core else COLOR_YELLOW,
        )

        # 分割线
        draw.rectangle(
            (
                car_left + round(car_inner_height * (0.08 * 2 + 0.29)),
                car_top + round(car_inner_height * 0.25),
                car_left
                + round(car_inner_height * (0.08 * 2 + 0.29))
                + round(car_inner_height * 0.15),
                car_top
                + round(car_inner_height * 0.25)
                + round(car_inner_height * 0.5),
            ),
            outline=COLOR_WHITE,
            width=round(car_inner_height * 0.01),
            fill=COLOR_WHITE,
        )

        # 云台
        draw.rectangle(
            (
                car_left + round(car_inner_height * (0.08 * 2 + 0.51)),
                car_top + int(car_inner_height * 0.35),
                car_left
                + round(car_inner_height * (0.08 * 2 + 0.51))
                + round(car_inner_height * 0.3),
                car_top + int(car_inner_height * 0.35) + round(car_inner_height * 0.3),
            ),
            outline=COLOR_MID_BLUE,
            width=round(car_inner_height * 0.02),
            fill=COLOR_GREEN if status_pyz else COLOR_YELLOW,
        )

    @staticmethod
    def wifi(draw, left=0, top=0, width=9, height=9, signal=100, num=0):
        """绘制WiFi图标"""
        blue = COLOR_BLUE
        gray = COLOR_MID_BLUE

        if signal > 0:
            draw.pieslice(
                (left, top, left + width * 2, top + height * 2), -135, -45, fill=blue
            )
            draw.pieslice(
                (left + 3, top + 3, left + width * 2 - 3, top + height * 2 - 3),
                -135,
                -45,
                fill=COLOR_DARK_BLUE,
            )
            draw.pieslice(
                (left + 6, top + 6, left + width * 2 - 6, top + height * 2 - 6),
                -135,
                -45,
                fill=blue,
            )
            draw.pieslice(
                (left + 9, top + 9, left + width * 2 - 9, top + height * 2 - 9),
                -135,
                -45,
                fill=COLOR_DARK_BLUE,
            )
            draw.pieslice(
                (left + 12, top + 12, left + width * 2 - 12, top + height * 2 - 12),
                -135,
                -45,
                fill=blue,
            )
        else:
            draw.pieslice(
                (left, top, left + width * 2, top + height * 2),
                -135,
                -45,
                outline=gray,
                fill=gray,
            )

        draw.text(
            (left + 24, top + 7),
            # "%s" % num if signal > 0 else "x",
            "" if signal > 0 else "x",
            font=fonts.get_font("small"),
            fill=COLOR_BLUE if signal > 0 else COLOR_MID_BLUE,
        )

    @staticmethod
    def draw_header(draw, online = False, network=""):
        """绘制页面头部信息"""
        if online:
            Graphics.signal(draw, left=105, top=1, width=20, height=17, signal=100)
        else:
            Graphics.signal(draw, left=105, top=1, width=20, height=17, signal=0)

        if "以太网" in network:
            Graphics.eth(draw, left=132, top=1, width=20, height=17, connected=True)
        else:
            Graphics.eth(draw, left=132, top=1, width=20, height=17, connected=False)

        if "WLAN" in network:
            Graphics.wifi(draw, left=150, top=1, width=17, height=17, signal=100)
        else:
            Graphics.wifi(draw, left=150, top=1, width=17, height=17, signal=0)

    @staticmethod
    def draw_footer(draw, left_text="确定", right_text="返回", center=""):
        """绘制页面底部菜单"""
        footer_y = SCREEN_HEIGHT - 21
        font_width = 17

        if left_text:
            draw.text(
                (2, footer_y),
                left_text,
                font=fonts.get_font("normal"),
                fill=COLOR_WHITE,
            )
        if right_text:
            draw.text(
                (SCREEN_WIDTH - font_width * len(right_text) - 2, footer_y),
                right_text,
                font=fonts.get_font("normal"),
                fill=COLOR_WHITE,
            )
        if center:
            draw.text(
                (SCREEN_WIDTH / 2 - font_width * len(center) / 2, footer_y),
                center,
                font=fonts.get_font("normal"),
                fill=COLOR_WHITE,
            )

    @staticmethod
    def draw_background(draw, title):
        """绘制背景和标题栏"""
        # 背景
        draw.rectangle((0, 0, SCREEN_WIDTH, SCREEN_HEIGHT), fill=COLOR_DARK_BLUE)

        # 外侧边框
        line_width = 2
        draw.polygon(
            [
                (0, 0),
                (90, 0),
                (110, 20),
                (218, 20),
                (238, 40),
                (238, 215),
                (20, 215),
                (0, 195),
                (0, 0),
            ],
            fill=COLOR_BLUE,
        )

        # 内层背景
        draw.polygon(
            [
                (line_width, line_width),
                (90 - line_width, line_width),
                (110 - line_width, 20 + line_width),
                (218 - line_width, 20 + line_width),
                (238 - line_width, 40 + line_width),
                (238 - line_width, 215 - line_width),
                (20 + line_width, 215 - line_width),
                (line_width, 195 - line_width),
                (line_width, line_width),
            ],
            outline=COLOR_BLUE,
            fill=COLOR_DARK_BLUE,
        )

        # 装饰元素
        draw.polygon([(83, 8), (88, 8), (98, 18), (93, 18)], fill=COLOR_BLUE)
        draw.polygon([(73, 8), (78, 8), (88, 18), (83, 18)], fill=COLOR_BLUE)
        draw.polygon([(223, 20), (238, 20), (238, 35)], fill=COLOR_BLUE)

        # 标题栏图标
        draw.rectangle((6, 8, 18, 22), fill=COLOR_BLUE)
        draw.polygon(
            [
                (8, 10),
                (16, 10),
                (16, 20),
                (8, 20),
                (8, 18),
                (14, 16),
                (14, 14),
                (8, 12),
                (14, 12),
                (14, 10),
            ],
            fill=COLOR_DARK_BLUE,
        )

        # 标题文字
        draw.text((20, 4), title, font=fonts.get_font("normal"), fill=COLOR_BLUE)

        # 时间显示
        import time

        draw.text(
            (193, 1),
            time.strftime("%H:%M", time.localtime()),
            font=fonts.get_font("header"),
            fill=COLOR_WHITE,
        )

    @staticmethod
    def draw_rounded_rect(
        draw, left=5, top=20, width=0, height=0, radius=10, color=COLOR_MID_BLUE
    ):
        """绘制圆角矩形区域"""
        draw.polygon(
            [
                (left, top),
                (left + width - radius, top),
                (left + width, top + radius),
                (left + width, top + height),
                (left + radius, top + height),
                (left, top + height - radius),
                (left, top),
            ],
            fill=color,
        )
