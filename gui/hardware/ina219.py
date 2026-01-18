# -*- coding:utf-8 -*-
# INA219电量监测

import smbus
import time

# 寄存器地址
_REG_CONFIG = 0x00
_REG_SHUNTVOLTAGE = 0x01
_REG_BUSVOLTAGE = 0x02
_REG_POWER = 0x03
_REG_CURRENT = 0x04
_REG_CALIBRATION = 0x05

class INA219:
    def __init__(self, i2c_bus=1, addr=0x40):
        self.bus = smbus.SMBus(i2c_bus)
        self.addr = addr
        self._cal_value = 0
        self._current_lsb = 0
        self._power_lsb = 0
        self.set_calibration_16V_5A()

    def read(self, address):
        data = self.bus.read_i2c_block_data(self.addr, address, 2)
        return (data[0] << 8) + data[1]

    def write(self, address, data):
        temp = [(data & 0xFF00) >> 8, data & 0xFF]
        self.bus.write_i2c_block_data(self.addr, address, temp)

    def set_calibration_16V_5A(self):
        """校准配置，支持16V和5A测量"""
        self._current_lsb = 0.1524  # 100uA每比特
        self._cal_value = 26868
        self._power_lsb = 0.003048  # 2mW每比特
        
        # 写入校准值
        self.write(_REG_CALIBRATION, self._cal_value)
        
        # 配置寄存器
        config = (0x00 << 13) | (0x01 << 11) | (0x0D << 7) | (0x0D << 3) | 0x07
        self.write(_REG_CONFIG, config)

    def get_shunt_voltage_mV(self):
        """获取分流电压(mV)"""
        value = self.read(_REG_SHUNTVOLTAGE)
        if value > 32767:
            value -= 65535
        return value * 0.01

    def get_bus_voltage_V(self):
        """获取总线电压(V)"""
        self.read(_REG_BUSVOLTAGE)  # 第一次读取清除标志
        return (self.read(_REG_BUSVOLTAGE) >> 3) * 0.004

    def get_current_mA(self):
        """获取电流(mA)"""
        value = self.read(_REG_CURRENT)
        if value > 32767:
            value -= 65535
        return value * self._current_lsb

    def get_power_W(self):
        """获取功率(W)"""
        value = self.read(_REG_POWER)
        if value > 32767:
            value -= 65535
        return value * self._power_lsb

    def get_battery_percentage(self):
        """计算电池百分比"""
        try:
            bus_voltage = self.get_bus_voltage_V()
            # 假设电池电压范围3.0V-4.2V
            percentage = (bus_voltage - 3.0) / (4.2 - 3.0) * 100
            return max(0, min(100, int(percentage)))
        except:
            return 0