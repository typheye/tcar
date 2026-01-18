# -*- coding:utf-8 -*-
# 车体自检系统 - 多线程版本

import threading
import time
from display.graphics import Graphics
from display.fonts import fonts
from utils import press_key, wait_release, wait_press, get_core_status, log
from config import *

class CamFrame:
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
        
        # 功能标志
        self.have_init = False
        self.have_error = False
        
        # 摄像头线程相关变量
        self.camera_thread = None
        self.running = False
        self.current_frame = None  # 缓存的当前帧（numpy数组）
        self.frame_lock = threading.Lock()
        self.frame_ready = False
        self.last_frame_time = 0
        self.camera_url = "http://192.168.166.100:8080/?action=stream"
        self.frame_rate = 10  # 目标帧率
        self.frame_interval = 1.0 / self.frame_rate

        # 帧计算
        self.frame_count = 0
        self.fps = 0
        self.fps_last_time = 0
        self.fps_lock = threading.Lock()  # 用于线程安全的FPS访问

        # 新增：显示FPS统计（排除绘制时间）
        self.display_fps = 0  # 实际显示帧率
        self.last_display_time = 0  # 上次显示时间
        self.display_frame_count = 0  # 显示帧计数器
        self.display_fps_start_time = 0  # 显示FPS计算开始时间
        self.display_fps_lock = threading.Lock()
        
    def start_camera_thread(self):
        """启动摄像头线程"""
        if self.running:
            return
            
        self.running = True
        self.camera_thread = threading.Thread(target=self._camera_loop)
        self.camera_thread.daemon = True
        self.camera_thread.start()
        log(1, "摄像头线程已启动")
        
    def stop_camera_thread(self):
        """停止摄像头线程"""
        self.running = False
        if self.camera_thread:
            self.camera_thread.join(timeout=2)
        log(1, "摄像头线程已停止")
        
    def _camera_loop(self):
        """摄像头线程主循环"""
        cap = None
        
        try:
            cap = cv2.VideoCapture(self.camera_url)
            if not cap.isOpened():
                log(3, "无法打开摄像头:", self.camera_url)
                return
                
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            log(1, "摄像头已连接，开始采集")
            
            last_frame_time = 0
            frame_count = 0  # 本地帧计数器
            fps_start_time = time.time()  # FPS计算开始时间
            
            while self.running:
                current_time = time.time()
                
                # 控制帧率
                if current_time - last_frame_time >= self.frame_interval:
                    ret, frame = cap.read()
                    
                    if ret and frame is not None:
                        # 转换颜色空间
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        
                        # 更新缓存帧
                        with self.frame_lock:
                            self.current_frame = frame_rgb
                            self.frame_ready = True
                            self.last_frame_time = current_time
                        
                        last_frame_time = current_time
                        frame_count += 1  # 成功获取帧时计数
                        
                        # 每秒计算一次FPS（仅摄像头采集帧率）
                        if current_time - fps_start_time >= 1.0:
                            with self.fps_lock:
                                self.fps = frame_count
                            frame_count = 0
                            fps_start_time = current_time
                        
                    else:
                        log(2, "读取摄像头帧失败")
                        # 失败时清空缓存
                        with self.frame_lock:
                            self.current_frame = None
                            self.frame_ready = False
                    
                    # 短暂休眠，避免占用太多CPU
                    time.sleep(0.001)
                else:
                    # 等待下一帧时间
                    sleep_time = max(0, self.frame_interval - (time.time() - last_frame_time))
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                        
        except Exception as e:
            log(3, "摄像头线程错误:", str(e))
        finally:
            if cap:
                cap.release()
            log(1, "摄像头线程结束")
            
    def get_fps(self):
        """获取当前帧率"""
        with self.fps_lock:
            return self.fps
    
    def get_current_frame(self):
        """获取当前缓存的帧"""
        with self.frame_lock:
            if self.frame_ready and self.current_frame is not None:
                return self.current_frame.copy()  # 返回副本
            return None

    def init_camFrame(self):
        if not self.have_init:
            self.have_init = True
            # 启动摄像头线程
            self.start_camera_thread()
            # 等待第一帧
            start_wait = time.time()
            while time.time() - start_wait < 3.0:
                if self.get_current_frame() is not None:
                    break
                time.sleep(0.1)
            self.show_ui, self.show_ui_msg, self.show_ui_disable = 0, "", False

    def show_main_ui(self):
        """显示主页 - 多线程版本"""
        
        # 在 show_main_ui 方法开始处添加：
        display_frame_count = 0
        display_fps = 0
        last_display_fps_time = time.time()
        draw_start_time = 0

        # 然后在绘制循环中修改：
        while True:
            if self.show_ui == 0:
                # 记录绘制开始时间
                draw_start_time = time.time()
                
                with self.display.lcd.create_canvas() as canvas:
                    # 绘制背景和UI
                    Graphics.draw_background(canvas.draw, "程序")
                    if self.system_info:
                        ip = self.system_info.get_info()[0]
                    else:
                        ip = ""
                    Graphics.draw_header(canvas.draw, ip, self.wifi_manager.get_interfaces())

                    if self.have_init:
                        Graphics.draw_footer(canvas.draw, left_text="")
                    else:
                        canvas.draw.text((10, 35), "相机画面\n\n\n\n点击 \"启动\" 按钮监察相机\n\n点击 \"返回\" 按钮离开本页",
                        font=fonts.get_font('normal'), fill=COLOR_WHITE)
                        Graphics.draw_footer(canvas.draw, left_text="启动")
                    
                    if self.have_init:
                        # 获取缓存的帧
                        frame_rgb = self.get_current_frame()

                        if frame_rgb is not None:
                            try:                                
                                canvas.draw.rectangle((0, 0, 240, 220), fill=COLOR_DARK_BLUE)
                                frame_resized = cv2.resize(frame_rgb, (240, 180))

                                # 优化绘制：使用更高效的方法
                                # 当前的方法（240x180x步长1）要绘制43200个矩形，太慢了！
                                # 我们可以优化：
                                
                                # 方案1：降低分辨率（推荐）
                                step = 2  # 改为每2个像素绘制一个
                                for y in range(0, 180, step):
                                    for x in range(0, 240, step):
                                        # 获取像素颜色
                                        r, g, b = frame_resized[y, x]
                                        
                                        # 绘制矩形块
                                        canvas.draw.rectangle(
                                            (0 + x, 30 + y, 
                                            0 + x + step - 1, 30 + y + step - 1),
                                            fill=(int(r), int(g), int(b))
                                        )

                                # 方案2：或者使用PIL的Image.fromarray直接绘制（更高效）
                                # 但需要修改graphics.py的支持
                                
                                # 计算显示FPS（排除绘制时间）
                                display_frame_count += 1
                                current_time = time.time()
                                if current_time - last_display_fps_time >= 1.0:
                                    display_fps = display_frame_count
                                    display_frame_count = 0
                                    last_display_fps_time = current_time
                                
                                # 显示两个FPS：采集FPS和显示FPS
                                current_cam_fps = self.get_fps()
                                canvas.draw.text((5, 5), f"Cam: {current_cam_fps}", 
                                            font=fonts.get_font('normal'), fill=COLOR_GREEN)
                                canvas.draw.text((125, 5), f"Disp: {display_fps}", 
                                            font=fonts.get_font('normal'), fill=COLOR_YELLOW)
                                self.have_error = False
                                    
                            except Exception as e:
                                log(2, "绘制错误:", str(e))
                                self.show_ui, self.show_ui_msg, self.show_ui_disable = 1, "绘制错误", False
                                self.have_error = True
                        else:
                            self.show_ui, self.show_ui_msg, self.show_ui_disable = 1, "无信号", True
                            self.have_error = True

                    else:
                        self.have_error = False
                    
                    # 检查
                    if wait_press(ok_PIN):
                        wait_release(ok_PIN)
                        self.show_ui, self.show_ui_msg, self.show_ui_disable = 1, "正在连接...", True

                    # 检查退出键
                    if press_key(cancel_PIN):
                        wait_release(cancel_PIN)
                        break
                    #return

            elif self.show_ui == 1:
                self.show_msg_screen(self.show_ui_msg, disable=self.show_ui_disable)
            
                if not self.have_init or self.have_error:
                    if not self.have_init:
                        self.init_camFrame()
                    if self.have_error:
                        self.stop_camera_thread()
                        self.have_error = False
                        self.have_init = False
                        self.show_ui, self.show_ui_msg, self.show_ui_disable = 0, "", False
                
            time.sleep(0.01)
        
        # 退出时停止摄像头线程
        self.stop_camera_thread()
    
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
    