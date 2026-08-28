#!/usr/bin/python3
# coding=utf8
# 文件名: mpu6050_server_fixed.py

import smbus
import math
import socket
import time
import struct

# ============ 简化的互补滤波姿态解算 (更稳定) ============
class AttitudeEstimator:
    """使用互补滤波 + 自适应参数，稳定可靠"""
    
    def __init__(self, sample_freq=100):
        self.sample_freq = sample_freq
        self.dt = 1.0 / sample_freq
        
        # 四元数 [w, x, y, z]
        self.q = [1.0, 0.0, 0.0, 0.0]
        
        # 姿态角 (度)
        self.pitch = 0.0
        self.roll = 0.0
        self.yaw = 0.0
        
        # 互补滤波系数 (动态调整)
        self.alpha = 0.96  # 陀螺仪权重 (0.96-0.99)
        
        # 平滑
        self.last_pitch = 0.0
        self.last_roll = 0.0
        self.last_yaw = 0.0

    def update(self, gx, gy, gz, ax, ay, az):
        """
        更新姿态
        gx, gy, gz: 角速度 (度/秒)
        ax, ay, az: 加速度 (g)
        """
        # 1. 通过加速度计算角度 (仅当加速度稳定时)
        norm = math.sqrt(ax*ax + ay*ay + az*az)
        if norm > 0.001:
            # 归一化
            ax_n = ax / norm
            ay_n = ay / norm
            az_n = az / norm
            
            # 计算角度 (度)
            accel_pitch = math.atan2(ax_n, az_n) * 180.0 / math.pi
            accel_roll = math.atan2(ay_n, az_n) * 180.0 / math.pi
        else:
            accel_pitch = self.pitch
            accel_roll = self.roll
        
        # 2. 陀螺仪积分 (度)
        gyro_pitch = self.pitch + gy * self.dt
        gyro_roll = self.roll + gx * self.dt
        gyro_yaw = self.yaw + gz * self.dt
        
        # 3. 动态调整互补滤波系数
        # 当加速度变化大时，降低加速度权重 (减少抖动)
        accel_magnitude = math.sqrt(ax*ax + ay*ay + az*az)
        if abs(accel_magnitude - 1.0) > 0.2:
            # 加速度偏离1g较大，可能是快速运动，降低加速度权重
            alpha = 0.98
        else:
            alpha = self.alpha
        
        # 4. 互补滤波融合
        self.pitch = alpha * gyro_pitch + (1 - alpha) * accel_pitch
        self.roll = alpha * gyro_roll + (1 - alpha) * accel_roll
        self.yaw = gyro_yaw  # 偏航仅靠陀螺仪 (无磁力计)
        
        # 5. 轻微平滑 (消除突变)
        smooth_factor = 0.2
        self.pitch = self.last_pitch * (1 - smooth_factor) + self.pitch * smooth_factor
        self.roll = self.last_roll * (1 - smooth_factor) + self.roll * smooth_factor
        self.yaw = self.last_yaw * (1 - smooth_factor) + self.yaw * smooth_factor
        
        self.last_pitch = self.pitch
        self.last_roll = self.roll
        self.last_yaw = self.yaw


# ============ MPU6050 类 ============
class MPU6050:
    def __init__(self, address=0x68, bus=1):
        self.bus = smbus.SMBus(bus)
        self.address = address
        
        # 校准数据
        self.gyro_offset = [0.0, 0.0, 0.0]
        self.accel_offset = [0.0, 0.0, 0.0]
        
        # 初始化传感器
        self._init_mpu6050()
        
        # 校准
        self.calibrate()
        
        # 姿态估计器
        self.estimator = AttitudeEstimator(sample_freq=100)

    def _write_byte(self, reg, val):
        try:
            self.bus.write_byte_data(self.address, reg, val)
            return True
        except:
            return False

    def _read_word_array(self, reg, length):
        try:
            return self.bus.read_i2c_block_data(self.address, reg, length)
        except:
            return [0] * length

    def _init_mpu6050(self):
        """初始化MPU6050"""
        # 唤醒
        self._write_byte(0x6B, 0x00)
        time.sleep(0.1)
        
        # 配置: DLPF 21Hz, 采样率 100Hz
        self._write_byte(0x1A, 0x06)   # DLPF
        self._write_byte(0x19, 0x09)   # 采样率分频 (100Hz)
        self._write_byte(0x1B, 0x08)   # 陀螺仪 ±500°/s
        self._write_byte(0x1C, 0x00)   # 加速度 ±2g
        
        time.sleep(0.1)

    def calibrate(self, samples=200):
        """校准陀螺仪零点"""
        print("校准中... 请保持MPU6050静止!")
        
        gyro_sum = [0.0, 0.0, 0.0]
        accel_sum = [0.0, 0.0, 0.0]
        
        for i in range(samples):
            # 读取陀螺仪
            data = self._read_word_array(0x43, 6)
            if len(data) >= 6:
                for j in range(3):
                    val = (data[j*2] << 8) + data[j*2+1]
                    if val >= 0x8000:
                        val -= 0x10000
                    gyro_sum[j] += val
            
            # 读取加速度 (用于计算偏移)
            data = self._read_word_array(0x3B, 6)
            if len(data) >= 6:
                for j in range(3):
                    val = (data[j*2] << 8) + data[j*2+1]
                    if val >= 0x8000:
                        val -= 0x10000
                    accel_sum[j] += val
            
            time.sleep(0.005)
        
        # 陀螺仪偏移
        self.gyro_offset = [s / samples for s in gyro_sum]
        
        # 加速度偏移 (理论上 X=0, Y=0, Z=1g)
        self.accel_offset[0] = accel_sum[0] / samples
        self.accel_offset[1] = accel_sum[1] / samples
        self.accel_offset[2] = accel_sum[2] / samples - 16384.0  # 减去1g
        
        print(f"校准完成: 陀螺仪偏移 = ({self.gyro_offset[0]:.2f}, {self.gyro_offset[1]:.2f}, {self.gyro_offset[2]:.2f})")

    def read_all(self):
        """读取所有原始数据"""
        # 读取加速度 (6字节)
        accel = self._read_word_array(0x3B, 6)
        ax = (accel[0] << 8) + accel[1]
        ay = (accel[2] << 8) + accel[3]
        az = (accel[4] << 8) + accel[5]
        if ax >= 0x8000: ax -= 0x10000
        if ay >= 0x8000: ay -= 0x10000
        if az >= 0x8000: az -= 0x10000
        
        # 读取陀螺仪 (6字节)
        gyro = self._read_word_array(0x43, 6)
        gx = (gyro[0] << 8) + gyro[1]
        gy = (gyro[2] << 8) + gyro[3]
        gz = (gyro[4] << 8) + gyro[5]
        if gx >= 0x8000: gx -= 0x10000
        if gy >= 0x8000: gy -= 0x10000
        if gz >= 0x8000: gz -= 0x10000
        
        # 减去陀螺仪偏移
        gx -= self.gyro_offset[0]
        gy -= self.gyro_offset[1]
        gz -= self.gyro_offset[2]
        
        # 读取温度 (可选)
        temp_data = self._read_word_array(0x41, 2)
        temp = (temp_data[0] << 8) + temp_data[1]
        if temp < 0x8000:
            temp = temp / 340.0 + 36.53
        else:
            temp = 0.0
        
        return (ax, ay, az, gx, gy, gz, temp)

    def get_angles(self):
        """获取稳定姿态角 (度)"""
        ax, ay, az, gx, gy, gz, _ = self.read_all()
        
        # 转换为物理单位
        ax_g = ax / 16384.0      # ±2g 量程
        ay_g = ay / 16384.0
        az_g = az / 16384.0
        gx_dps = gx / 65.5       # ±500°/s 量程
        gy_dps = gy / 65.5
        gz_dps = gz / 65.5
        
        # 更新姿态
        self.estimator.update(gx_dps, gy_dps, gz_dps, ax_g, ay_g, az_g)
        
        # 返回角度和原始数据 (用于调试)
        return (self.estimator.pitch, self.estimator.roll, self.estimator.yaw,
                ax, ay, az, gx, gy, gz)


# ============ UDP 服务器 ============
class MPU6050Server:
    def __init__(self, ip='0.0.0.0', port=8888):
        self.ip = ip
        self.port = port
        self.mpu = MPU6050()
        self.running = True
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((ip, port))
        self.sock.settimeout(0.1)
        
        print(f"UDP服务器启动: {ip}:{port}")
        print("等待PC客户端连接...")

    def run(self):
        client_addr = None
        last_time = time.time()
        frame_count = 0
        
        print("\n开始发送数据 (Ctrl+C停止)")
        print("-" * 50)
        
        try:
            while self.running:
                # 接收客户端请求
                try:
                    data, addr = self.sock.recvfrom(1024)
                    if data == b'get_data':
                        client_addr = addr
                except socket.timeout:
                    pass
                
                # 如果有客户端，发送数据
                if client_addr:
                    angles = self.mpu.get_angles()
                    # 打包: 9个float = 36字节
                    data = struct.pack('!9f', *angles)
                    self.sock.sendto(data, client_addr)
                    
                    # 控制台输出 (每10帧显示一次)
                    frame_count += 1
                    if frame_count % 10 == 0:
                        pitch, roll, yaw = angles[0], angles[1], angles[2]
                        print(f"Pitch: {pitch:6.1f}°  Roll: {roll:6.1f}°  Yaw: {yaw:6.1f}°")
                
                # 控制发送频率 ~100Hz
                dt = time.time() - last_time
                sleep_time = 0.01 - dt
                if sleep_time > 0:
                    time.sleep(sleep_time)
                last_time = time.time()
                
        except KeyboardInterrupt:
            print("\n\n服务器已停止")
        except Exception as e:
            print(f"\n错误: {e}")
        finally:
            self.sock.close()


if __name__ == "__main__":
    server = MPU6050Server()
    server.run()
