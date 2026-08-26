#!/usr/bin/python3
# coding=utf8
import smbus
import time

'''
/****************************************************
  Company:   幻尔科技
  作者:深圳市幻尔科技有限公司
  我们的店铺:lobot-zone.taobao.com
*****************************************************
  传感器：Hiwonder系列 一体化语音交互模块
  通信方式：iic
  返回：数字量
*****************************************************/
'''


I2C_ADDR = 0x34  # I2C地址

# 模块寄存器
ASR_RESULT_ADDR = 0x64  #语音识别结果寄存器地址，通过不断读取此地址的值判断是否识别到语音，不同的值对应不同的语音
ASR_SPEAK_ADDR = 0x6E   #播报设置寄存器地址

ASR_CMDMAND = 0x00     #播报语类型：命令词条播报语
ASR_ANNOUNCER = 0xFF   #播报语类型：普通播报语

class ASRModule:
    def __init__(self,address, bus=1):
        # 初始化 I2C 总线和设备地址
        self.bus = smbus.SMBus(bus)  # 使用 I2C 总线 1
        self.address = address  # 设备的 I2C 地址
        self.send = [0, 0]  # 初始化发送数据的数组

    def wire_write_byte(self, val):
        """
        向设备写入单个字节
        :param val: 要写入的字节值
        :return: 如果成功写入返回 True，失败返回 False
        """
        try:
            self.bus.write_byte(self.address, val) # 发送字节到设备
            return True # 写入成功
        except IOError:
            return False # 写入失败，返回 False

    def wire_write_data_array(self, reg, val, length):
        """
        向指定寄存器写入字节数组
        :param reg: 寄存器地址
        :param val: 要写入的字节数组
        :param length: 要写入的字节数
        :return: 如果成功写入返回 True，失败返回 False
        """
        try:            
            self.bus.write_i2c_block_data(self.address, reg, val[:length]) # 发送字节数组到设备的指定寄存器
            return True # 写入成功
        except IOError:
            return False # 写入失败，返回 False

    def wire_read_data_array(self, reg, length):
        """
        从指定寄存器读取字节数组
        :param reg: 寄存器地址
        :param length: 要读取的字节数
        :return: 读取到的字节数组，失败时返回空数组
        """          
        try:
            result = self.bus.read_i2c_block_data(self.address, reg, 1) # 从设备读取字节数组
            return result # 返回读取结果
        except IOError:
            return [] # 读取失败，返回空数组

    def rec_recognition(self):
        """
        识别结果读取
        :return: 识别结果，如果读取失败返回 0
        """
        result = self.wire_read_data_array(ASR_RESULT_ADDR, 1) # 从结果寄存器读取一个字节
        if result:
            return result # 返回读取到的结果
        return 0  # 如果没有结果，返回 0

    def speak(self, cmd, id):
        """
        向设备发送说话命令
        :param cmd: 命令字节
        :param id: 说话的 ID
        """
        if cmd == ASR_ANNOUNCER or cmd == ASR_CMDMAND: # 检查命令是否有效
            self.send[0] = cmd # 设置发送数组的第一个元素为命令
            self.send[1] = id # 设置发送数组的第二个元素为 ID
            self.wire_write_data_array(ASR_SPEAK_ADDR, self.send, 2) # 发送命令和 ID 到指定寄存器


if __name__ == "__main__":
    asr_module = ASRModule(I2C_ADDR)    
    
        # (ASR_CMDMAND, 1),  # 正在前进
        # (ASR_CMDMAND, 3),  # 正在左转
        # (ASR_ANNOUNCER, 1),  # 可回收物
        # (ASR_ANNOUNCER, 3)   # 有害垃圾
    # 定义播报内容及其对应的ID
    announcements = [
        (ASR_ANNOUNCER, 15),  # 欢迎光临

        (ASR_ANNOUNCER, 33),  # 1
        (ASR_ANNOUNCER, 34),  # 2
        (ASR_ANNOUNCER, 35),  # 3
        (ASR_ANNOUNCER, 36),  # 4
        (ASR_ANNOUNCER, 37),  # 5
        (ASR_ANNOUNCER, 38),  # 6
        (ASR_ANNOUNCER, 39),  # 7
        (ASR_ANNOUNCER, 40),  # 8
        
        (ASR_ANNOUNCER, 34),  # 2
        (ASR_ANNOUNCER, 34),  # 2
        (ASR_ANNOUNCER, 35),  # 3
        (ASR_ANNOUNCER, 36),  # 4
        (ASR_ANNOUNCER, 37),  # 5
        (ASR_ANNOUNCER, 38),  # 6
        (ASR_ANNOUNCER, 39),  # 7
        (ASR_ANNOUNCER, 40),  # 8
        
        (ASR_ANNOUNCER, 35),  # 3
        (ASR_ANNOUNCER, 34),  # 2
        (ASR_ANNOUNCER, 35),  # 3
        (ASR_ANNOUNCER, 36),  # 4
        (ASR_ANNOUNCER, 37),  # 5
        (ASR_ANNOUNCER, 38),  # 6
        (ASR_ANNOUNCER, 39),  # 7
        (ASR_ANNOUNCER, 40),  # 8
        
        (ASR_ANNOUNCER, 36),  # 4
        (ASR_ANNOUNCER, 34),  # 2
        (ASR_ANNOUNCER, 35),  # 3
        (ASR_ANNOUNCER, 36),  # 4
        (ASR_ANNOUNCER, 37),  # 5
        (ASR_ANNOUNCER, 38),  # 6
        (ASR_ANNOUNCER, 39),  # 7
        (ASR_ANNOUNCER, 40),  # 8
    ]
    
    while True:
        for cmd, id in announcements:
            asr_module.speak(cmd, id)
            time.sleep(1) 
        