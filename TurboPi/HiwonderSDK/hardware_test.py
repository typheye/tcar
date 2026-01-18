#!/usr/bin/python3
# coding=utf8
import sys
import time

sys.path.append("/home/pi/TurboPi/")
import yaml_handle
import HiwonderSDK.Board as Board

if sys.version_info.major == 2:
    print("Please run this program with python3!")
    sys.exit(0)

print(
    """
**********************************************************
********************PWM舵机和电机测试************************
**********************************************************
----------------------------------------------------------
Official website:https://www.hiwonder.com
Online mall:https://hiwonder.tmall.com
----------------------------------------------------------
Tips:
 * 按下Ctrl+C可关闭此次程序运行，若失败请多次尝试！
----------------------------------------------------------
"""
)

servo_data = yaml_handle.get_yaml_data(yaml_handle.servo_file_path)
servo1 = servo_data["servo1"]
servo2 = servo_data["servo2"]

Board.setPWMServoPulse(1, servo1 + 300, 300)
time.sleep(0.3)
Board.setPWMServoPulse(1, servo1, 300)
time.sleep(0.3)
Board.setPWMServoPulse(1, servo1 - 300, 300)
time.sleep(0.3)
Board.setPWMServoPulse(1, servo1, 300)
time.sleep(1.5)

Board.setPWMServoPulse(2, servo2 + 300, 300)
time.sleep(0.3)
Board.setPWMServoPulse(2, servo2, 300)
time.sleep(0.3)
Board.setPWMServoPulse(2, servo2 - 300, 300)
time.sleep(0.3)
Board.setPWMServoPulse(2, servo2, 300)
time.sleep(1.5)

Board.setMotor(1, 45)
time.sleep(0.5)
Board.setMotor(1, 0)
time.sleep(1)

Board.setMotor(2, 45)
time.sleep(0.5)
Board.setMotor(2, 0)
time.sleep(1)

Board.setMotor(3, 45)
time.sleep(0.5)
Board.setMotor(3, 0)
time.sleep(1)

Board.setMotor(4, 45)
time.sleep(0.5)
Board.setMotor(4, 0)
time.sleep(1)
