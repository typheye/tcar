# -*- coding:utf-8 -*-
# 相机核心模块 - 完全独立版本

import threading
import time
import numpy as np
import cv2
from PIL import Image, ImageDraw
from system.rpc import rpc_client
from display.fonts import fonts
from utils import log
from config import *


class Camera:
    """完全独立的相机核心类"""
    
    def __init__(self, camera_url="http://192.168.166.100:8080/?action=stream"):
        self.camera_url = camera_url
        
        # 摄像头状态
        self.available = False
        self.initialized = False
        
        # 摄像头线程相关变量
        self.camera_thread = None
        self.running = False
        self.current_frame = None
        self.frame_lock = threading.Lock()
        self.frame_ready = False
        
        # 性能统计
        self.capture_fps_target = 60  # 采集帧率
        self.capture_interval = 1.0 / self.capture_fps_target
        self.capture_fps = 0
        self.capture_frame_count = 0
        self.capture_fps_start_time = time.time()
        self.fps_lock = threading.Lock()
        
        # 显示控制
        self.display_fps = 0
        self.display_frame_count = 0
        self.display_fps_start_time = time.time()
        self.display_fps_lock = threading.Lock()
        
        # 预计算UI元素
        self.ui_overlay_np = None
        self._init_ui_overlay()
        
        # 动态调整参数
        self.display_skip_ratio = 1          # 初始：每1帧显示1帧
        self.skip_counter = 0               # 跳过计数器
        self.frames_displayed = 0           # 已显示帧数计数器
        self.frame_times = []
        self.last_displayed_frame = None
        self.last_change_check_time = 0
        self.last_ratio_adjust_time = 0
        self.ratio_adjust_cooldown = 2.0    # 2秒内不重复调整
        self.change_check_interval = 1.0    # 每1秒检查一次变化
    
    def can_use(self):
        """检查相机是否可用"""
        return self.available
    
    def _init_ui_overlay(self):
        """预计算UI覆盖层为numpy数组"""
        # 创建240x240的RGB图像
        overlay = Image.new("RGB", (240, 240), COLOR_DARK_BLUE)
        draw = ImageDraw.Draw(overlay)
        
        # 顶部FPS显示区域背景
        draw.rectangle((0, 0, 239, 25), fill=COLOR_DARK_BLUE)
        
        # 摄像头画面区域背景（预填充）
        draw.rectangle((0, 30, 239, 209), fill=COLOR_BLACK)
        
        # 底部提示区域背景
        draw.rectangle((0, 210, 239, 239), fill=COLOR_DARK_BLUE)
        
        # 转换为numpy数组存储
        self.ui_overlay_np = np.array(overlay)
    
    def initialize(self):
        """初始化相机"""
        if self.initialized:
            return True
        
        rpc_client.load_function(8)
            
        try:
            # 测试连接
            cap = cv2.VideoCapture(self.camera_url)
            if not cap.isOpened():
                log(3, "无法打开摄像头:", self.camera_url)
                self.available = False
                return False
            
            self.available = True
            self.initialized = True
            cap.release()
            log(1, "相机初始化成功")
            return True
            
        except Exception as e:
            log(3, "相机初始化错误:", str(e))
            self.available = False
            return False
    
    def start(self):
        """启动相机采集线程"""
        if not self.initialized:
            if not self.initialize():
                return False
        
        if self.running:
            return True

        self.running = True
        self.camera_thread = threading.Thread(target=self._camera_loop)
        self.camera_thread.daemon = True
        self.camera_thread.start()
        log(1, f"相机采集线程已启动")
        
        # 等待第一帧
        start_wait = time.time()
        while time.time() - start_wait < 2.0:
            if self.frame_ready and self.current_frame is not None:
                log(1, "相机第一帧就绪")
                return True
            time.sleep(0.05)
        
        log(2, "相机启动超时")
        return False
    
    def stop(self):
        """停止相机采集线程"""
        self.running = False
        if self.camera_thread:
            self.camera_thread.join(timeout=1)
        log(1, "相机采集线程已停止")
        return True
    
    def _camera_loop(self):
        """摄像头线程主循环"""
        cap = None
        
        try:
            cap = cv2.VideoCapture(self.camera_url)
            if not cap.isOpened():
                log(3, "无法打开摄像头:", self.camera_url)
                self.available = False
                return
            
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.available = True
            
            log(1, f"相机已连接，开始{self.capture_fps_target}fps采集")
            
            last_frame_time = time.time()
            frame_count = 0
            fps_start_time = time.time()
            
            while self.running:
                current_time = time.time()
                elapsed = current_time - last_frame_time
                
                if elapsed >= self.capture_interval:
                    # 清空缓冲区
                    for _ in range(2):
                        cap.grab()
                    
                    ret, frame = cap.retrieve()
                    
                    if ret and frame is not None:
                        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        
                        with self.frame_lock:
                            self.current_frame = frame_rgb
                            self.frame_ready = True
                        
                        last_frame_time = current_time
                        frame_count += 1
                        
                        # 更新FPS
                        if current_time - fps_start_time >= 0.5:
                            with self.fps_lock:
                                self.capture_fps = int(frame_count * 2)
                            frame_count = 0
                            fps_start_time = current_time
                    
                    time.sleep(0.0001)
                else:
                    sleep_time = max(0, self.capture_interval - (time.time() - last_frame_time))
                    if sleep_time > 0:
                        time.sleep(sleep_time * 0.8)
                        
        except Exception as e:
            log(3, "相机线程错误:", str(e))
            self.available = False
        finally:
            if cap:
                cap.release()
            log(1, "相机线程结束")
    
    def get_frame(self):
        """获取当前帧"""
        if self.frame_ready:
            with self.frame_lock:
                if self.current_frame is not None:
                    return self.current_frame.copy()
        return None
    
    def get_stats(self):
        """获取性能统计"""
        with self.fps_lock:
            cam_fps = self.capture_fps
        with self.display_fps_lock:
            disp_fps = self.display_fps
        return cam_fps, disp_fps
    
    def update_display_fps(self):
        """更新显示帧率统计"""
        self.display_frame_count += 1
        current_time = time.time()
        if current_time - self.display_fps_start_time >= 0.5:
            with self.display_fps_lock:
                self.display_fps = self.display_frame_count * 2
            self.display_frame_count = 0
            self.display_fps_start_time = current_time
    
    def create_display_image(self, frame_rgb, show_fps=True, bottom_text=None):
        """创建显示图像"""
        # 缩放摄像头画面
        frame_resized = cv2.resize(frame_rgb, (240, 180))
        
        # 使用预计算的UI覆盖层
        display_np = self.ui_overlay_np.copy()
        display_np[30:210, :] = frame_resized
        
        # 添加FPS显示
        if show_fps:
            cam_fps, disp_fps = self.get_stats()
            
            # 创建文本图像
            text_img = Image.new("RGB", (240, 25), COLOR_DARK_BLUE)
            draw = ImageDraw.Draw(text_img)
            draw.text((5, 5), f"Cam:{cam_fps:2d}", font=fonts.get_font("normal"), fill=COLOR_GREEN)
            draw.text((125, 5), f"Disp:{disp_fps:2d}", font=fonts.get_font("normal"), fill=COLOR_YELLOW)
            
            # 合并文本
            text_np = np.array(text_img)
            display_np[:25, :] = text_np
        
        # 添加底部文字
        if bottom_text:
            bottom_img = Image.new("RGB", (240, 30), COLOR_DARK_BLUE)
            draw = ImageDraw.Draw(bottom_img)
            draw.text((25, 5), bottom_text, font=fonts.get_font("normal"), fill=COLOR_WHITE)
            bottom_np = np.array(bottom_img)
            display_np[210:, :] = bottom_np
        
        return display_np
    
    def should_display_this_frame(self, dynamic_adjust=True):
        """决定是否显示当前帧（动态跳过逻辑）"""
        self.skip_counter += 1
        
        if not dynamic_adjust or self.skip_counter >= self.display_skip_ratio:
            self.skip_counter = 0
            self.frames_displayed += 1
            return True
        return False
    
    def update_dynamic_adjustment(self, frame_rgb):
        """更新动态调整参数"""
        if self.last_displayed_frame is None:
            self.last_displayed_frame = frame_rgb.copy()
            return
        
        current_time = time.time()
        
        # 降低内容变化检测频率
        if (self.frames_displayed % 30 == 0 or 
            current_time - self.last_change_check_time > self.change_check_interval):
            
            # 计算帧间差异
            diff = cv2.absdiff(frame_rgb, self.last_displayed_frame)
            change_amount = np.sum(diff)
            
            # 动态调整逻辑
            if change_amount > 100000:  # 画面变化大
                if (current_time - self.last_ratio_adjust_time > self.ratio_adjust_cooldown and
                    self.display_skip_ratio > 1):
                    self.display_skip_ratio = max(1, self.display_skip_ratio - 1)
                    log(1, f"画面变化大，减少跳过率: 每{self.display_skip_ratio}帧显示1帧")
                    self.last_ratio_adjust_time = current_time
            elif change_amount < 20000 and self.display_skip_ratio < 3:  # 画面静止
                if current_time - self.last_ratio_adjust_time > self.ratio_adjust_cooldown:
                    self.display_skip_ratio = min(3, self.display_skip_ratio + 1)
                    log(1, f"画面静止，增加跳过率: 每{self.display_skip_ratio}帧显示1帧")
                    self.last_ratio_adjust_time = current_time
            
            self.last_change_check_time = current_time
        
        self.last_displayed_frame = frame_rgb.copy()
    
    def update_performance(self, display_time):
        """更新性能统计和动态调整"""
        if display_time is not None:
            self.frame_times.append(display_time)
            
            current_time = time.time()
            if current_time - self.last_ratio_adjust_time >= 2.0 and len(self.frame_times) > 0:
                avg_time = sum(self.frame_times) / len(self.frame_times)
                current_fps = 1.0 / avg_time if avg_time > 0 else 0
                
                log(1, f"性能: {avg_time*1000:.1f}ms, FPS={current_fps:.1f}, 跳过率=1/{self.display_skip_ratio}")
                
                # 动态调整
                if current_fps < 22 and self.display_skip_ratio < 3:
                    self.display_skip_ratio = min(self.display_skip_ratio + 1, 3)
                    log(1, f"帧率偏低({current_fps:.1f}fps)，增加跳过率到: 每{self.display_skip_ratio}帧显示1帧")
                elif current_fps > 30 and self.display_skip_ratio > 1:
                    self.display_skip_ratio = max(self.display_skip_ratio - 1, 1)
                    log(1, f"帧率偏高({current_fps:.1f}fps)，减少跳过率到: 每{self.display_skip_ratio}帧显示1帧")
                
                self.frame_times = []
                self.last_ratio_adjust_time = current_time
    
    def reset_dynamic_params(self):
        """重置动态参数"""
        self.display_skip_ratio = 1
        self.skip_counter = 0
        self.frames_displayed = 0
        self.frame_times = []
        self.last_displayed_frame = None
        self.last_change_check_time = 0
        self.last_ratio_adjust_time = 0