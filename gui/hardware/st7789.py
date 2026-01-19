import spidev
import RPi.GPIO as GPIO
import time
from config import *
import numpy as np

class ST7789(object):
    """ST7789 240*240 1.3inch LCD驱动"""

    def __init__(self, spi, rst=27, dc=25, bl=24):
        self.width = 240
        self.height = 240
        self._dc = dc
        self._rst = rst
        self._bl = bl
        
        # 缓存FPS文本区域图像，减少重复转换
        self.fps_buffer = None
        self.fps_dirty = True
        self.last_cam_fps = -1
        self.last_disp_fps = -1
        
        # 初始化GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self._dc, GPIO.OUT)
        GPIO.setup(self._rst, GPIO.OUT)
        GPIO.setup(self._bl, GPIO.OUT)
        GPIO.output(self._bl, GPIO.HIGH)
        
        # 初始化SPI - 尝试最高速度
        self._spi = spi
        self._spi.max_speed_hz = 62000000  # 尝试62MHz
        self._spi.mode = 0b00
        
        # 预分配内存
        self.rgb565_buffer = np.zeros((self.height, self.width), dtype=np.uint16)
        self.spi_buffer = bytearray(self.width * self.height * 2)
        
        # 预计算部分区域更新
        self.region_buffers = {
            'fps': bytearray(80 * 25 * 2),  # FPS区域
            'video': bytearray(240 * 180 * 2),  # 视频区域
            'bottom': bytearray(240 * 30 * 2),  # 底部区域
        }

    def command(self, cmd):
        """发送命令"""
        GPIO.output(self._dc, GPIO.LOW)
        self._spi.writebytes([cmd])

    def data(self, val):
        """发送数据"""
        GPIO.output(self._dc, GPIO.HIGH)
        self._spi.writebytes([val])

    def Init(self):
        """初始化显示"""
        self.reset()

        self.command(0x36)
        # 尝试以下值之一：
        # self.data(0x00)  # 正常方向
        self.data(0x70)  # 当前设置
        # self.data(0xC0)  # 旋转180度
        # self.data(0xA0)  # RGB顺序

        self.command(0x3A) 
        # self.data(0x05)  # RGB565格式
        self.data(0x65)  # 改为65K RGB格式

        # 其他配置寄存器设置
        self.command(0xB2)
        self.data(0x0C); self.data(0x0C); self.data(0x00)
        self.data(0x33); self.data(0x33)

        self.command(0xB7)
        self.data(0x35) 

        self.command(0xBB)
        self.data(0x19)

        self.command(0xC0)
        self.data(0x2C)

        self.command(0xC2)
        self.data(0x01)

        self.command(0xC3)
        self.data(0x12)   

        self.command(0xC4)
        self.data(0x20)

        self.command(0xC6)
        self.data(0x0F) 

        self.command(0xD0)
        self.data(0xA4); self.data(0xA1)

        # Gamma校正 - 尝试更中性的设置
        self.command(0xE0)
        # 第一组Gamma校正（正极）
        self.data(0xD0); self.data(0x00); self.data(0x02); self.data(0x07)
        self.data(0x0A); self.data(0x28); self.data(0x32); self.data(0x44)
        self.data(0x42); self.data(0x06); self.data(0x0E); self.data(0x12)
        self.data(0x14); self.data(0x17)

        self.command(0xE1)
        # 第二组Gamma校正（负极）
        self.data(0xD0); self.data(0x00); self.data(0x02); self.data(0x07)
        self.data(0x0A); self.data(0x28); self.data(0x31); self.data(0x54)
        self.data(0x47); self.data(0x0E); self.data(0x1C); self.data(0x17)
        self.data(0x1B); self.data(0x1E)

        # 增加对比度到最大值
        self.command(0xC5)  # VCOM控制命令
        self.data(0x3F)     # 最大对比度值（通常是0x00-0x3F）
        self.data(0x3F)     # 最大对比度值
        
        self.command(0x21)  # 显示反转开启
        # self.command(0x20)  # 显示反转关闭
        
        self.command(0x11)  # 退出睡眠模式
        time.sleep(0.120)   # 等待120ms
        self.command(0x29)  # 开启显示

    def reset(self):
        """复位显示"""
        GPIO.output(self._rst, GPIO.HIGH)
        time.sleep(0.01)
        GPIO.output(self._rst, GPIO.LOW)
        time.sleep(0.01)
        GPIO.output(self._rst, GPIO.HIGH)
        time.sleep(0.01)
        
    def SetWindows(self, Xstart, Ystart, Xend, Yend):
        """设置显示窗口"""
        # 设置X坐标
        self.command(0x2A)
        self.data(0x00)
        self.data(Xstart & 0xff)
        self.data(0x00)
        self.data((Xend - 1) & 0xff)
        
        # 设置Y坐标
        self.command(0x2B)
        self.data(0x00)
        self.data((Ystart & 0xff))
        self.data(0x00)
        self.data((Yend - 1) & 0xff)

        self.command(0x2C)  # 开始写入内存
    
    def ShowImage(self, Image, Xstart, Ystart):
        """显示PIL图像"""
        imwidth, imheight = Image.size
        if imwidth != self.width or imheight != self.height:
            raise ValueError(f'图像尺寸必须与显示尺寸相同 ({self.width}x{self.height})')
        
        img = np.asarray(Image)
        pix = np.zeros((self.width, self.height, 2), dtype=np.uint8)
        
        # RGB565转换
        pix[..., [0]] = np.add(np.bitwise_and(img[..., [0]], 0xF8), np.right_shift(img[..., [1]], 5))
        pix[..., [1]] = np.add(np.bitwise_and(np.left_shift(img[..., [1]], 3), 0xE0), np.right_shift(img[..., [2]], 3))
        
        pix = pix.flatten().tolist()
        self.SetWindows(0, 0, self.width, self.height)
        
        GPIO.output(self._dc, GPIO.HIGH)
        # 分块写入，避免缓冲区溢出
        for i in range(0, len(pix), 4096):
            self._spi.writebytes(pix[i:i+4096])		

    @staticmethod
    def _rgb888_to_rgb565_numba(img):
        """使用numba加速RGB888转RGB565"""
        h, w = img.shape[:2]
        result = np.zeros((h, w), dtype=np.uint16)
        
        for i in range(h):
            for j in range(w):
                r = img[i, j, 0] >> 3
                g = img[i, j, 1] >> 2
                b = img[i, j, 2] >> 3
                result[i, j] = (r << 11) | (g << 5) | b
        return result

    @staticmethod
    def _rgb888_to_rgb565_numpy(img):
        """使用numpy向量化转换RGB888到RGB565"""
        # 提取并移位RGB分量
        r = (img[..., 0] >> 3).astype(np.uint16)
        g = (img[..., 1] >> 2).astype(np.uint16)
        b = (img[..., 2] >> 3).astype(np.uint16)
        
        # 组合成RGB565
        return (r << 11) | (g << 5) | b

    def _convert_to_rgb565_fast(self, img_array):
        """快速转换图像到RGB565格式"""
        if img_array.shape[:2] != (self.height, self.width):
            # 如果需要缩放，先缩放
            img_array = cv2.resize(img_array, (self.width, self.height))
        
        # 使用numpy向量化转换
        rgb565 = self._rgb888_to_rgb565_numpy(img_array)
        return rgb565

    def _update_fps_region_fast(self, cam_fps, disp_fps):
        """快速更新FPS区域"""
        # 只有当FPS值变化时才更新
        if cam_fps == self.last_cam_fps and disp_fps == self.last_disp_fps and not self.fps_dirty:
            return self.region_buffers['fps']
        
        # 创建FPS文本图像（只需顶部25像素高度）
        from PIL import Image, ImageDraw
        fps_img = Image.new("RGB", (240, 25), (0, 0, 0))
        draw = ImageDraw.Draw(fps_img)
        
        # 绘制FPS文本
        draw.text((5, 5), f"Cam:{cam_fps:2d}", fill=(0, 255, 0))
        draw.text((125, 5), f"Disp:{disp_fps:2d}", fill=(255, 255, 0))
        
        # 转换为RGB565
        fps_array = np.array(fps_img)
        rgb565 = self._rgb888_to_rgb565_numpy(fps_array)
        
        # 转换为字节并存储
        self.region_buffers['fps'][:] = rgb565.tobytes()
        
        self.last_cam_fps = cam_fps
        self.last_disp_fps = disp_fps
        self.fps_dirty = False
        
        return self.region_buffers['fps']

    def ShowImageFast(self, img_input, cam_fps=0, disp_fps=0):
        """快速显示图像 - 修正版本"""
        import time
        start_time = time.time()
        
        # 确保输入是numpy数组
        if isinstance(img_input, Image.Image):
            img_array = np.array(img_input)
        elif isinstance(img_input, np.ndarray):
            img_array = img_input
        else:
            raise TypeError("输入必须是PIL Image或numpy数组")
        
        # 确保尺寸正确
        if img_array.shape[:2] != (self.height, self.width):
            img_array = cv2.resize(img_array, (self.width, self.height))
        
        # 确保是RGB格式
        if len(img_array.shape) == 2:
            img_array = cv2.cvtColor(img_array, cv2.COLOR_GRAY2RGB)
        elif img_array.shape[2] == 4:
            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)
        
        # 调用类方法时不要加self参数
        rgb565 = self._rgb888_to_rgb565_st7789(img_array)
        
        # 转换为字节
        rgb565_bytes = rgb565.tobytes()
        
        # 写入SPI
        self._write_spi_fast(rgb565_bytes)
        
        end_time = time.time()
        return end_time - start_time

    def _rgb888_to_rgb565_st7789(self, img):
        """使用原始ShowImage的转换公式"""
        h, w = img.shape[:2]
        pix = np.zeros((h, w, 2), dtype=np.uint8)
        
        r = img[..., 0]
        g = img[..., 1] 
        b = img[..., 2]
        
        # 高位字节: RRRRRGGG
        pix[..., 0] = ((r & 0xF8) | (g >> 5))
        # 低位字节: GGGBBBBB
        pix[..., 1] = (((g << 3) & 0xE0) | (b >> 3))
        
        # 转换为16位
        rgb565 = pix.view(dtype=np.uint16).reshape(h, w)
        return rgb565

    def _write_spi_fast(self, data):
        """快速SPI写入"""
        self.SetWindows(0, 0, self.width, self.height)
        GPIO.output(self._dc, GPIO.HIGH)
        
        block_size = 4096
        
        if isinstance(data, (bytes, bytearray)):
            for i in range(0, len(data), block_size):
                self._spi.writebytes(data[i:i+block_size])
        else:
            data_bytes = bytes(data)
            for i in range(0, len(data_bytes), block_size):
                self._spi.writebytes(data_bytes[i:i+block_size])

    def ShowImageFastPartial(self, img_array, region='video'):
        """
        部分区域更新 - 只更新变化的区域
        region: 'fps', 'video', 'bottom', 'all'
        """
        if region == 'all':
            return self.ShowImageFast(img_array)
        
        if region == 'fps':
            # 只更新FPS区域 (0-25行)
            self.SetWindows(0, 0, self.width, 25)
            GPIO.output(self._dc, GPIO.HIGH)
            
            # 从img_array提取FPS区域并转换
            fps_section = img_array[:25, :]
            fps_rgb565 = self._rgb888_to_rgb565_numpy(fps_section)
            self._spi.writebytes2(fps_rgb565.tobytes())
            
        elif region == 'video':
            # 只更新视频区域 (30-210行)
            self.SetWindows(0, 30, self.width, 210)
            GPIO.output(self._dc, GPIO.HIGH)
            
            video_section = img_array[30:210, :]
            video_resized = cv2.resize(video_section, (240, 180))
            video_rgb565 = self._rgb888_to_rgb565_numpy(video_resized)
            self._spi.writebytes2(video_rgb565.tobytes())
        
        elif region == 'bottom':
            # 只更新底部区域 (210-240行)
            self.SetWindows(0, 210, self.width, self.height)
            GPIO.output(self._dc, GPIO.HIGH)
            
            bottom_section = img_array[210:240, :]
            bottom_rgb565 = self._rgb888_to_rgb565_numpy(bottom_section)
            self._spi.writebytes2(bottom_rgb565.tobytes())

        
    def clear(self):
        """清屏"""
        try:
            # 1. 关闭显示
            self.command(0x28)  # DISPOFF
            
            # 2. 等待一小段时间
            time.sleep(0.005)  # 5ms
            
            # 3. 执行清屏
            buffer = [0x00] * (self.width * self.height * 2)
            self.SetWindows(0, 0, self.width, self.height)
            GPIO.output(self._dc, GPIO.HIGH)
            
            for i in range(0, len(buffer), 4096):
                self._spi.writebytes(buffer[i:i+4096])
            
            # 4. 重新打开显示
            time.sleep(0.005)  # 5ms
            self.command(0x29)  # DISPON
        except Exception as e:
            print(f"清屏错误: {e}")
            # 回退方案：直接发送命令
            self.command(0x2C)  # RAMWR命令
            GPIO.output(self._dc, GPIO.HIGH)
            self._spi.writebytes([0x00, 0x00] * 100)  # 发送少量数据