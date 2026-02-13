#!/usr/bin/env python3
"""
电池电压监测脚本 - 适用于SSH远程调用
调用方式: ssh -q -t pi@192.168.166.100 "sudo python3 /home/pi/TurboPi/Utils/battery.py"
"""

import time
import sys
import json
import statistics
from collections import deque

sys.path.append('/home/pi/TurboPi/')
import HiwonderSDK.Board as Board

# 配置参数 - 简化和优化
class BatteryConfig:
    # 电压参数（根据实际测量）
    FULL_VOLTAGE = 7.8    # 满电电压
    EMPTY_VOLTAGE = 7.0   # 空电电压
    MIN_VOLTAGE = 6.8     # 最低有效电压
    MAX_VOLTAGE = 8.2     # 最高有效电压
    
    # 采样参数（优化为1秒内完成）
    SAMPLING_INTERVAL = 0.02  # 20ms采样间隔，更快响应
    SAMPLE_COUNT = 30         # 采样30次，约0.6秒完成
    
    # 滤波参数
    MEDIAN_WINDOW = 5         # 中值滤波窗口
    EMA_ALPHA = 0.4           # 稍高的平滑系数，更快稳定

class BatteryMonitor:
    def __init__(self):
        self.config = BatteryConfig()
        self.last_voltage = None
        self.last_update = 0
        
    def read_voltage_raw(self):
        """读取原始电压值"""
        try:
            voltage_raw = Board.getBattery()
            return voltage_raw / 1000.0
        except:
            return None
    
    def collect_samples(self):
        """快速采集电压样本"""
        samples = []
        valid_count = 0
        
        for _ in range(self.config.SAMPLE_COUNT):
            voltage = self.read_voltage_raw()
            if voltage and self.config.MIN_VOLTAGE <= voltage <= self.config.MAX_VOLTAGE:
                samples.append(voltage)
                valid_count += 1
            
            # 非阻塞延时，提高效率
            time.sleep(self.config.SAMPLING_INTERVAL)
        
        return samples
    
    def calculate_voltage(self, samples):
        """计算稳定的电压值"""
        if len(samples) < 10:  # 至少需要10个有效样本
            return None
        
        # 1. 中值滤波去噪
        if len(samples) >= self.config.MEDIAN_WINDOW:
            filtered = []
            for i in range(len(samples) - self.config.MEDIAN_WINDOW + 1):
                window = samples[i:i + self.config.MEDIAN_WINDOW]
                filtered.append(statistics.median(window))
            
            # 取最后5个值的平均值
            voltage = statistics.mean(filtered[-5:]) if len(filtered) >= 5 else statistics.mean(filtered)
        else:
            voltage = statistics.mean(samples)
        
        # 2. 指数平滑
        if self.last_voltage is not None:
            voltage = (self.config.EMA_ALPHA * voltage + 
                      (1 - self.config.EMA_ALPHA) * self.last_voltage)
        
        self.last_voltage = voltage
        return voltage
    
    def calculate_battery_percent(self, voltage):
        """计算电量百分比 - 针对7.8V满电优化"""
        if voltage <= self.config.EMPTY_VOLTAGE:
            return 0.0
        elif voltage >= self.config.FULL_VOLTAGE:
            return 100.0
        
        # 简化的线性插值
        voltage_range = self.config.FULL_VOLTAGE - self.config.EMPTY_VOLTAGE
        percent = ((voltage - self.config.EMPTY_VOLTAGE) / voltage_range) * 100.0
        
        # 限制范围
        return max(0.0, min(100.0, percent))
    
    def get_battery_status(self, percent):
        """获取电池状态"""
        if percent < 10:
            return "critical"
        elif percent < 30:
            return "warning"
        elif percent < 80:
            return "normal"
        else:
            return "full"
    
    def measure(self):
        """执行一次完整的电池测量"""
        start_time = time.time()
        
        # 采集样本
        samples = self.collect_samples()
        
        # 计算电压
        voltage = self.calculate_voltage(samples)
        
        if voltage is None:
            return {
                "success": False,
                "error": "测量失败，样本不足",
                "voltage": 0.0,
                "battery": 0.0,
                "status": "unknown",
                "measurement_time": round(time.time() - start_time, 3)
            }
        
        # 计算电量百分比
        battery_percent = self.calculate_battery_percent(voltage)
        
        # 获取状态
        battery_status = self.get_battery_status(battery_percent)
        
        return {
            "success": True,
            "voltage": round(voltage, 2),  # 保留2位小数
            "battery": round(battery_percent, 1),  # 保留1位小数
            "status": battery_status,
            "samples": len(samples),
            "measurement_time": round(time.time() - start_time, 3)
        }

# 主执行函数
def main():
    """主函数 - 适合SSH远程调用"""
    monitor = BatteryMonitor()
    result = monitor.measure()
    
    # 只输出最精简的JSON数据，适合远程解析
    print(json.dumps(result))
    
    # 如果需要更详细的信息，可以添加以下调试输出（默认不启用）
    if len(sys.argv) > 1 and sys.argv[1] == "--debug":
        print(f"\n调试信息:", file=sys.stderr)
        print(f"电压: {result['voltage']}V", file=sys.stderr)
        print(f"电量: {result['battery']}%", file=sys.stderr)
        print(f"状态: {result['status']}", file=sys.stderr)
        print(f"采样数: {result['samples']}", file=sys.stderr)
        print(f"测量时间: {result['measurement_time']}秒", file=sys.stderr)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # SSH调用时可能被中断
        print(json.dumps({"success": False, "error": "测量被中断"}))
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))