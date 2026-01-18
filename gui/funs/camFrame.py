# -*- coding:utf-8 -*-
# 相机UI模块 - 使用独立的Camera类

import time
from system.rpc import rpc_client
from display.graphics import Graphics
from display.fonts import fonts
from utils import press_key, wait_release, wait_press, log
from config import *
from view.camera import Camera  # 导入独立的相机模块


class CamFrame:
    def __init__(
        self, display, buttons, wifi_manager, system_info=None, power_monitor=None
    ):
        self.display = display
        self.buttons = buttons
        self.wifi_manager = wifi_manager
        self.system_info = system_info
        self.power_monitor = power_monitor

        # 创建相机实例
        self.camera = Camera(camera_url="http://192.168.166.100:8080/?action=stream")
        
        # UI状态
        self.show_ui = 0
        self.show_ui_msg = ""
        self.show_ui_disable = False
        self.have_init = False
        self.have_error = False

    def init_camFrame(self):
        """初始化相机功能"""
        if not self.have_init:
            self.have_init = True
            rpc_client.load_function(8)
            
            # 使用Camera类的接口
            if self.camera.start():
                self.show_ui, self.show_ui_msg, self.show_ui_disable = 0, "", False
                return True
            else:
                self.show_ui, self.show_ui_msg, self.show_ui_disable = 1, "相机连接失败", False
                self.have_init = False
                return False
    
    def show_main_ui(self):
        """显示主页 - 简化版本"""
        use_fast_method = True
        dynamic_adjust = True
        
        log(1, "启动相机UI")
        
        while True:
            if self.show_ui == 0:
                if self.have_init and self.camera.can_use():
                    # 获取当前帧
                    frame_rgb = self.camera.get_frame()
                    
                    if frame_rgb is not None:
                        # 动态跳过逻辑
                        if not self.camera.should_display_this_frame(dynamic_adjust):
                            # 即使跳过，也更新显示FPS统计
                            self.camera.update_display_fps()
                            self.have_error = False
                        else:
                            try:
                                # 更新动态调整
                                self.camera.update_dynamic_adjustment(frame_rgb)
                                
                                # 获取性能统计
                                cam_fps, disp_fps = self.camera.get_stats()
                                
                                # 显示图像
                                display_start = time.time()
                                
                                if use_fast_method:
                                    display_np = self.camera.create_display_image(
                                        frame_rgb, 
                                        show_fps=True,
                                        bottom_text="适当短按KEY3键离开相机"
                                    )
                                    display_time = self.display.lcd.show_image_fast(
                                        display_np, 
                                        cam_fps=cam_fps,
                                        disp_fps=disp_fps
                                    )
                                else:
                                    # 备用方法
                                    display_np = self.camera.create_display_image(
                                        frame_rgb, 
                                        show_fps=True,
                                        bottom_text="适当短按KEY3键离开相机"
                                    )
                                    display_img = Image.fromarray(display_np)
                                    self.display.lcd.show_image(display_img, 0, 0)
                                    display_time = time.time() - display_start
                                
                                # 更新显示FPS和性能统计
                                self.camera.update_display_fps()
                                self.camera.update_performance(display_time)
                                
                                self.have_error = False
                                
                            except Exception as e:
                                log(2, "显示错误:", str(e))
                                self.show_ui, self.show_ui_msg, self.show_ui_disable = (
                                    1,
                                    "绘制错误",
                                    False,
                                )
                                self.have_init = False
                                self.have_error = True
                                self.camera.stop()
                    else:
                        self.show_ui, self.show_ui_msg, self.show_ui_disable = (
                            1,
                            "无信号",
                            False,
                        )
                        self.have_init = False
                        self.have_error = True
                        self.camera.stop()
                else:
                    # 初始UI界面
                    self.have_error = False
                    with self.display.lcd.create_canvas() as canvas:
                        Graphics.draw_background(canvas.draw, "程序")
                        if self.system_info:
                            ip = self.system_info.get_info()[0]
                        else:
                            ip = ""
                        Graphics.draw_header(
                            canvas.draw, ip, self.wifi_manager.get_interfaces()
                        )
                        
                        if not self.have_init:
                            canvas.draw.text(
                                (10, 35),
                                '相机画面\n\n\n\n点击 "启动" 按钮监察相机\n\n点击 "返回" 按钮离开本页',
                                font=fonts.get_font("normal"),
                                fill=COLOR_WHITE,
                            )
                            Graphics.draw_footer(canvas.draw, left_text="启动")
                    
                    time.sleep(0.016)
                
                # 按键检测
                if press_key(ok_PIN):
                    wait_release(ok_PIN)
                    if not self.have_init:
                        self.show_ui, self.show_ui_msg, self.show_ui_disable = (
                            2,
                            "正在连接...",
                            True,
                        )
                
                if press_key(cancel_PIN):
                    wait_release(cancel_PIN)
                    if not self.have_init:
                        break
                    else:
                        self.camera.stop()
                        self.have_error = False
                        self.have_init = False
                        self.show_ui, self.show_ui_msg, self.show_ui_disable = (
                            0,
                            "",
                            False,
                        )
                        # 重置动态参数
                        self.camera.reset_dynamic_params()
            
            elif self.show_ui == 1:
                self.show_msg_screen(self.show_ui_msg, disable=self.show_ui_disable)
                
                if self.have_error:
                    self.camera.stop()
                    self.have_error = False
                    self.have_init = False
                time.sleep(0.016)
            
            elif self.show_ui == 2:
                self.show_msg_screen(self.show_ui_msg, disable=self.show_ui_disable)
                
                if not self.have_init:
                    self.init_camFrame()
                
                time.sleep(0.016)
        
        self.camera.stop()

    def show_msg_screen(self, message="提示内容", disable=False):
        """显示消息屏幕"""
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
            canvas.draw.text(
                (30, 42), message, font=fonts.get_font("medium"), fill=COLOR_WHITE
            )
            
            if not disable and press_key(ok_PIN):
                wait_release(ok_PIN)
                self.show_ui, self.show_ui_msg, self.show_ui_disable = 0, "", False