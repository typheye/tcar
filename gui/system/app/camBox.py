# -*- coding:utf-8 -*-
import time
import os
import cv2
import numpy as np
from PIL import Image
from system.framework.display.graphics import Graphics
from system.framework.display.fonts import fonts
from system.framework.public.utils import press_key, wait_release, wait_press, get_core_status, log
from system.config import *
from system.framework.view.camera import Camera


class CamBox:
    def __init__(
        self, display, buttons, system_info=None, power_monitor=None
    ):
        self.display = display
        self.buttons = buttons
        self.system_info = system_info
        self.power_monitor = power_monitor

        # 创建相机实例
        self.camera = Camera(camera_url=0)

        # UI状态
        self.show_ui = 0
        self.show_ui_msg = ""
        self.show_ui_disable = False

        # 相机状态
        self.camera_enabled = False
        self.camera_initialized = False

        # 相机显示控制
        self.display_skip_ratio = 1
        self.skip_counter = 0
        self.frames_displayed = 0
        self.frame_times = []
        self.last_displayed_frame = None
        self.last_change_check_time = 0
        self.last_ratio_adjust_time = 0

    def init_camera(self):
        """初始化相机"""
        if not self.camera_initialized:
            self.camera_initialized = True
            
            self.camera.start()

            self.show_ui, self.show_ui_msg, self.show_ui_disable = 0, "", False
            self.camera_enabled = True
            return True

        return True

    def close_camera(self):
        """关闭相机"""
        self.camera.stop()
        self.camera_enabled = False
        self.camera_initialized = False
        self.display_skip_ratio = 1
        self.skip_counter = 0
        self.frames_displayed = 0
        self.frame_times = []
        self.last_displayed_frame = None

    def update_dynamic_adjustment(self, frame_rgb):
        """更新动态调整参数"""
        if self.last_displayed_frame is None:
            self.last_displayed_frame = frame_rgb.copy()
            return

        current_time = time.time()

        if (
            self.frames_displayed % 30 == 0
            or current_time - self.last_change_check_time > 2.0
        ):

            diff = cv2.absdiff(frame_rgb, self.last_displayed_frame)
            change_amount = diff.sum()

            if change_amount > 100000 and self.display_skip_ratio > 1:
                self.display_skip_ratio = max(1, self.display_skip_ratio - 1)
                self.last_ratio_adjust_time = current_time
            elif change_amount < 20000 and self.display_skip_ratio < 3:
                self.display_skip_ratio = min(3, self.display_skip_ratio + 1)
                self.last_ratio_adjust_time = current_time

            self.last_change_check_time = current_time

        self.last_displayed_frame = frame_rgb.copy()

    def should_display_frame(self):
        """决定是否显示当前帧"""
        self.skip_counter += 1
        if self.skip_counter >= self.display_skip_ratio:
            self.skip_counter = 0
            self.frames_displayed += 1
            return True
        return False
    
    def update_performance_stats(self, display_time):
        """更新性能统计"""
        if display_time is not None:
            self.frame_times.append(display_time)

            current_time = time.time()
            if (
                current_time - self.last_ratio_adjust_time >= 2.0
                and len(self.frame_times) > 0
            ):
                avg_time = sum(self.frame_times) / len(self.frame_times)
                current_fps = 1.0 / avg_time if avg_time > 0 else 0

                if current_fps < 22 and self.display_skip_ratio < 3:
                    self.display_skip_ratio = min(self.display_skip_ratio + 1, 3)
                elif current_fps > 30 and self.display_skip_ratio > 1:
                    self.display_skip_ratio = max(self.display_skip_ratio - 1, 1)

                self.frame_times = []
                self.last_ratio_adjust_time = current_time

    def show_camera_view(self):
        """显示相机视图"""
        dynamic_adjust = True

        while self.camera_enabled:
            frame_rgb = self.camera.get_frame()

            if not self.should_display_frame():
                self.camera.update_display_fps()
            else:
                try:
                    if dynamic_adjust:
                        self.update_dynamic_adjustment(frame_rgb)

                    cam_fps, disp_fps = self.camera.get_stats()

                    display_start = time.time()

                    display_np = self.camera.create_display_image(
                        frame_rgb,
                        show_fps=True,
                        bottom_text="适当短按KEY2键离开相机",
                    )
                    display_time = self.display.lcd.show_image_fast(
                        display_np, cam_fps=cam_fps, disp_fps=disp_fps
                    )

                    self.camera.update_display_fps()
                    self.update_performance_stats(display_time)

                except Exception as e:
                    log(2, "相机显示错误:", str(e))
                    self.show_ui, self.show_ui_msg, self.show_ui_disable = (
                        1,
                        "相机显示错误",
                        False,
                    )
                    self.close_camera()
                    break

            if press_key(main_PIN):
                wait_release(main_PIN)
                self.close_camera()
                break

            time.sleep(0.001)

        return False

    def show_main_ui(self):
        """显示主界面"""

        while True:
            if self.show_ui == 0:
                if self.camera_enabled:
                    should_exit = self.show_camera_view()
                    if should_exit:
                        break
                    continue

                with self.display.lcd.create_canvas() as canvas:
                    Graphics.draw_background(canvas.draw, "程序")
                    if self.system_info:
                        online, network = (
                            self.system_info.get_online(),
                            self.system_info.get_info()[-2],
                        )
                    else:
                        online, network = False, ""
                    Graphics.draw_header(canvas.draw, online, network)
                    Graphics.draw_footer(canvas.draw, left_text="相机")

                    if self.camera_enabled:
                        pass
                    else:
                        canvas.draw.text(
                            (10, 35),
                            "Typheye Car 外接相机\n\n\n\n点击'相机'按钮打开相机\n\n点击'返回'按钮离开本页",
                            font=fonts.get_font("normal"),
                            fill=COLOR_WHITE,
                        )

                    if wait_press(ok_PIN):
                        wait_release(ok_PIN)
                        if not self.camera_enabled:
                            self.show_ui, self.show_ui_msg, self.show_ui_disable = (
                                2,
                                "正在连接相机...",
                                True,
                            )
                        else:
                            self.close_camera()

                    if press_key(cancel_PIN):
                        wait_release(cancel_PIN)
                        break

            elif self.show_ui == 1:
                self.show_msg_screen(self.show_ui_msg, disable=self.show_ui_disable)

            elif self.show_ui == 2:
                self.show_msg_screen(self.show_ui_msg, disable=self.show_ui_disable)

                if not self.camera_enabled:
                    if self.init_camera():
                        self.show_ui = 0
                    else:
                        self.show_ui = 1

            time.sleep(0.01)

        self.close_camera()

    def show_msg_screen(self, message="提示内容", disable=False):
        """显示加载屏幕"""
        with self.display.lcd.create_canvas() as canvas:
            Graphics.draw_background(canvas.draw, "提示")
            if self.system_info:
                online, network = (
                    self.system_info.get_online(),
                    self.system_info.get_info()[-2],
                )
            else:
                online, network = False, ""
            Graphics.draw_header(canvas.draw, online, network)
            if not disable:
                Graphics.draw_footer(canvas.draw, left_text="确定", right_text="")

            Graphics.draw_rounded_rect(canvas.draw, 6, 27, 225, 50, 16, COLOR_MID_BLUE)
            canvas.draw.text(
                (30, 42), message, font=fonts.get_font("medium"), fill=COLOR_WHITE
            )

            if not disable and press_key(ok_PIN):
                wait_release(ok_PIN)
                self.show_ui, self.show_ui_msg, self.show_ui_disable = 0, "", False
