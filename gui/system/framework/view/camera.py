# -*- coding:utf-8 -*-
# 相机核心模块 - 完全独立版本

import threading
import time
import numpy as np
import cv2
from PIL import Image, ImageDraw
from system.framework.public.rpc import rpc_client
from system.framework.display.fonts import fonts
from system.framework.public.utils import log
from system.config import *


class Camera:
    """完全独立的相机核心类"""
    
    def __init__(self, camera_url):
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
                # 仅在没有帧时才生成色块图
                if self.current_frame is None:
                    with self.frame_lock:
                        snow_frame = self._generate_snow_frame()
                        self.current_frame = snow_frame
                        self.frame_ready = True
                return False  # 仍然返回True
            
            self.available = True
            self.initialized = True
            cap.release()
            return True
            
        except Exception as e:
            log(3, "相机初始化错误:", str(e))
            self.available = False
            # 仅在没有帧时才生成色块图
            if self.current_frame is None:
                with self.frame_lock:
                    snow_frame = self._generate_snow_frame()
                    self.current_frame = snow_frame
                    self.frame_ready = True
            return False
    
    def start(self):
        """启动相机采集线程"""
        if not self.initialized:
            self.initialize()  # 调用但不检查返回值
        
        if self.running:
            return True

        self.running = True
        self.camera_thread = threading.Thread(target=self._camera_loop)
        self.camera_thread.daemon = True
        self.camera_thread.start()
        log(1, f"相机采集线程已启动")
        
        # 等待第一帧
        start_wait = time.time()
        while time.time() - start_wait < 1.0:
            if self.frame_ready and self.current_frame is not None:
                log(1, "相机第一帧就绪")
            time.sleep(0.05)
        
        return True
    
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
        error_count = 0
        max_retry_interval = 0.001
        
        # 初始确保有色块图
        if not self.available or self.current_frame is None:
            with self.frame_lock:
                snow_frame = self._generate_snow_frame()
                self.current_frame = snow_frame
                self.frame_ready = True
        
        while self.running:
            try:
                # 尝试连接摄像头
                if cap is None or not cap.isOpened():
                    # 先显示色块图
                    with self.frame_lock:
                        snow_frame = self._generate_snow_frame()
                        self.current_frame = snow_frame
                        self.frame_ready = True
                    
                    cap = cv2.VideoCapture(self.camera_url)
                    if not cap.isOpened():
                        time.sleep(max_retry_interval)
                        continue
                    
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    self.available = True
                    error_count = 0
                    log(1, f"相机已连接，开始{self.capture_fps_target}fps采集")
                
                # 正常的帧采集循环
                last_frame_time = time.time()
                frame_count = 0
                fps_start_time = time.time()
                
                while self.running and cap.isOpened():
                    try:
                        current_time = time.time()
                        elapsed = current_time - last_frame_time
                        
                        if elapsed >= self.capture_interval:
                            # 清空缓冲区
                            for _ in range(2):
                                cap.grab()
                            
                            ret, frame = cap.retrieve()
                            
                            if not ret or frame is None:
                                raise RuntimeError("摄像头无有效帧")
                            
                            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            
                            with self.frame_lock:
                                self.current_frame = frame_rgb
                                self.frame_ready = True
                            
                            last_frame_time = current_time
                            frame_count += 1
                            error_count = 0
                            
                            # 更新FPS
                            if current_time - fps_start_time >= 0.5:
                                with self.fps_lock:
                                    self.capture_fps = int(frame_count * 2)
                                frame_count = 0
                                fps_start_time = current_time
                        
                        time.sleep(0.001)
                            
                    except Exception as e:
                        log(3, "帧采集异常:", str(e))
                        break  # 跳出内层循环
                
                # 如果跳出内层循环，表示摄像头出问题了
                self.available = False
                if cap:
                    cap.release()
                    cap = None
                
                # 显示色块图
                with self.frame_lock:
                    snow_frame = self._generate_snow_frame()
                    self.current_frame = snow_frame
                    self.frame_ready = True
                
                # 等待后重试
                time.sleep(max_retry_interval)
                
            except Exception as e:
                log(2, f"摄像头循环异常: {str(e)}")
                self.available = False
                with self.frame_lock:
                    snow_frame = self._generate_snow_frame()
                    self.current_frame = snow_frame
                    self.frame_ready = True
                time.sleep(max_retry_interval)
        
        # 循环结束后的清理
        if cap:
            cap.release()
        log(1, "相机线程结束")
    
    def _generate_snow_frame(self):
        """生成240x180的随机大块马赛克图"""
        # 随机生成更大的块（减少细节）
        block_size = 10  # 块大小
        num_rows = 180 // block_size + 1
        num_cols = 240 // block_size + 1
        
        # 创建空图像
        frame = np.zeros((180, 240, 3), dtype=np.uint8)
        
        # 生成随机颜色矩阵
        color_matrix = np.random.randint(0, 256, (num_rows, num_cols, 3), dtype=np.uint8)
        
        # 填充马赛克块
        for i in range(num_rows):
            for j in range(num_cols):
                y_start = i * block_size
                y_end = min((i + 1) * block_size, 180)
                x_start = j * block_size
                x_end = min((j + 1) * block_size, 240)
                
                frame[y_start:y_end, x_start:x_end] = color_matrix[i, j]
        
        return frame

    def get_frame(self):
        """获取当前帧"""
        with self.frame_lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
        
        # 如果当前帧为空，生成色块图
        snow_frame = self._generate_snow_frame()
        with self.frame_lock:
            self.current_frame = snow_frame
            self.frame_ready = True
        return snow_frame
    
    def get_stats(self):
        """获取性能统计"""
        if not self.available:
            return 0, 0  # 摄像头不可用时返回0,0
    
        with self.fps_lock:
            cam_fps = self.capture_fps
        with self.display_fps_lock:
            disp_fps = self.display_fps
        return cam_fps, disp_fps
    
    def update_display_fps(self):
        """更新显示帧率统计"""
        if not self.available:
            with self.display_fps_lock:
                self.display_fps = 0
            return
    
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