import spidev
import RPi.GPIO as GPIO
import time
import numpy as np

class ST7789(object):
    """ST7789 240*240 1.3inch LCD驱动"""

    def __init__(self, spi, rst=27, dc=25, bl=24):
        self.width = 240
        self.height = 240
        self._dc = dc
        self._rst = rst
        self._bl = bl
        
        # 初始化GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(self._dc, GPIO.OUT)
        GPIO.setup(self._rst, GPIO.OUT)
        GPIO.setup(self._bl, GPIO.OUT)
        GPIO.output(self._bl, GPIO.HIGH)
        
        # 初始化SPI
        self._spi = spi
        self._spi.max_speed_hz = 40000000

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
        self.data(0x70)  # 设置扫描方向

        self.command(0x3A) 
        self.data(0x05)  # RGB565格式

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

        # Gamma校正
        self.command(0xE0)
        self.data(0xD0); self.data(0x04); self.data(0x0D); self.data(0x11)
        self.data(0x13); self.data(0x2B); self.data(0x3F); self.data(0x54)
        self.data(0x4C); self.data(0x18); self.data(0x0D); self.data(0x0B)
        self.data(0x1F); self.data(0x23)

        self.command(0xE1)
        self.data(0xD0); self.data(0x04); self.data(0x0C); self.data(0x11)
        self.data(0x13); self.data(0x2C); self.data(0x3F); self.data(0x44)
        self.data(0x51); self.data(0x2F); self.data(0x1F); self.data(0x1F)
        self.data(0x20); self.data(0x23)
        
        self.command(0x21)  # 显示反转开启
        self.command(0x11)  # 退出睡眠模式
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
        
    def clear(self):
        """清屏"""
        buffer = [0xff] * (self.width * self.height * 2)
        self.SetWindows(0, 0, self.width, self.height)
        GPIO.output(self._dc, GPIO.HIGH)
        
        for i in range(0, len(buffer), 4096):
            self._spi.writebytes(buffer[i:i+4096])