#!/usr/bin/python3
# coding=utf8
# 文件名: debug_sensors.py
# 运行在树莓派上，分别测试MPU6050和超声波

import smbus
import math
import time
import sys
sys.path.append('/home/pi/TurboPi/')
from smbus2 import SMBus, i2c_msg

print("=" * 60)
print("传感器调试工具")
print("=" * 60)

# ============ 1. 测试I2C设备 ============
print("\n[1] 扫描I2C设备...")
print("-" * 40)
try:
    bus = smbus.SMBus(1)
    for addr in range(0x03, 0x78):
        try:
            bus.write_byte(addr, 0)
            print(f"  找到设备: 0x{addr:02X}")
        except:
            pass
except Exception as e:
    print(f"  I2C扫描失败: {e}")

# ============ 2. 测试MPU6050 ============
print("\n[2] 测试MPU6050 (地址0x68)...")
print("-" * 40)

MPU6050_ADDR = 0x68

def read_word(reg):
    try:
        high = bus.read_byte_data(MPU6050_ADDR, reg)
        low = bus.read_byte_data(MPU6050_ADDR, reg + 1)
        val = (high << 8) + low
        if val >= 0x8000:
            val -= 0x10000
        return val
    except:
        return 0

try:
    # 读取WHO_AM_I
    whoami = bus.read_byte_data(MPU6050_ADDR, 0x75)
    print(f"  WHO_AM_I: 0x{whoami:02X} (期望: 0x68)")
    
    if whoami == 0x68:
        print("  ✓ MPU6050 检测正常")
        
        # 读取原始数据
        for i in range(5):
            ax = read_word(0x3B)
            ay = read_word(0x3D)
            az = read_word(0x3F)
            gx = read_word(0x43)
            gy = read_word(0x45)
            gz = read_word(0x47)
            
            print(f"  样本{i+1}: 加速度({ax:6d}, {ay:6d}, {az:6d})  角速度({gx:6d}, {gy:6d}, {gz:6d})")
            time.sleep(0.1)
    else:
        print("  ✗ WHO_AM_I 不匹配，可能是连接问题")
        
except Exception as e:
    print(f"  ✗ MPU6050 读取失败: {e}")

# ============ 3. 测试超声波 ============
print("\n[3] 测试超声波 (地址0x77)...")
print("-" * 40)

class SonarTest:
    def __init__(self):
        self.i2c_addr = 0x77
        self.i2c = 1

    def getDistance(self):
        """获取距离"""
        dist = 5000
        try:
            with SMBus(self.i2c) as bus:
                # 方法1: 写入0x00然后读取2字节
                write = i2c_msg.write(self.i2c_addr, [0x00,])
                bus.i2c_rdwr(write)
                time.sleep(0.02)  # 等待测量
                
                read = i2c_msg.read(self.i2c_addr, 2)
                bus.i2c_rdwr(read)
                
                data = list(read)
                if len(data) >= 2:
                    # 尝试两种字节序
                    raw1 = (data[0] << 8) | data[1]
                    raw2 = (data[1] << 8) | data[0]
                    
                    print(f"  原始数据: [0x{data[0]:02X}, 0x{data[1]:02X}] -> raw1={raw1}, raw2={raw2}")
                    
                    # 取合理的值 (30-5000mm)
                    if 30 <= raw1 <= 5000:
                        dist = raw1
                    elif 30 <= raw2 <= 5000:
                        dist = raw2
                    else:
                        # 尝试直接读取
                        dist = raw1
                        
        except Exception as e:
            print(f"  读取错误: {e}")
            dist = 5000
            
        return dist

sonar = SonarTest()

print("  开始连续读取超声波 (按Ctrl+C停止)")
print("  请在传感器前方移动障碍物观察变化")
print("-" * 40)

try:
    count = 0
    while count < 20:
        dist = sonar.getDistance()
        print(f"  距离: {dist:5d} mm  ({dist/10:.1f} cm)")
        time.sleep(0.5)
        count += 1
except KeyboardInterrupt:
    print("\n  测试停止")

# ============ 4. 测试姿态融合 (Yaw) ============
print("\n[4] 测试Yaw角度变化")
print("-" * 40)
print("  请缓慢旋转MPU6050 90度，观察Yaw变化")
print("  按Ctrl+C停止")
print("-" * 40)

class SimpleAttitude:
    def __init__(self):
        self.pitch = 0.0
        self.roll = 0.0
        self.yaw = 0.0
        self.gyro_offset = [0, 0, 0]
        self.alpha = 0.96
        
    def calibrate(self):
        print("  校准中...保持静止")
        for i in range(100):
            gx = read_word(0x43)
            gy = read_word(0x45)
            gz = read_word(0x47)
            self.gyro_offset[0] += gx
            self.gyro_offset[1] += gy
            self.gyro_offset[2] += gz
            time.sleep(0.005)
        self.gyro_offset = [x/100 for x in self.gyro_offset]
        print(f"  偏移: ({self.gyro_offset[0]:.1f}, {self.gyro_offset[1]:.1f}, {self.gyro_offset[2]:.1f})")
    
    def update(self):
        gx = read_word(0x43) - self.gyro_offset[0]
        gy = read_word(0x45) - self.gyro_offset[1]
        gz = read_word(0x47) - self.gyro_offset[2]
        
        # 转换为度/秒 (±500°/s)
        gx_dps = gx / 65.5
        gy_dps = gy / 65.5
        gz_dps = gz / 65.5
        
        dt = 0.01
        self.yaw += gz_dps * dt
        
        return self.yaw

try:
    attitude = SimpleAttitude()
    attitude.calibrate()
    
    print("\n  开始读取Yaw (按Ctrl+C停止)")
    print("  旋转90度观察Yaw变化")
    print("-" * 40)
    
    last_yaw = 0
    while True:
        yaw = attitude.update()
        print(f"  Yaw: {yaw:8.2f}°  (变化: {yaw - last_yaw:6.2f}°)")
        last_yaw = yaw
        time.sleep(0.1)
        
except KeyboardInterrupt:
    print("\n  测试停止")

print("\n" + "=" * 60)
print("调试完成")