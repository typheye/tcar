#!/usr/bin/python3
# coding=utf8
"""
小车基础控制 - SSH终端版（无GUI）
适合在树莓派通过SSH远程控制小车

操作说明：
程序启动后，根据提示输入字母并按回车：
  w → 向前走 5秒
  s → 向后走 5秒
  a → 向左平移 5秒
  d → 向右平移 5秒
  q → 左转 5秒
  e → 右转 5秒
  x → 停止小车
  quit → 退出程序
"""

import sys
import time

# 添加TurboPi库路径
sys.path.append('/home/pi/TurboPi/')
import HiwonderSDK.mecanum as mecanum

# 初始化小车
car = mecanum.MecanumChassis()

def stop_car():
    """停止小车"""
    car.set_velocity(0, 0, 0)
    print("→ 小车已停止")

def move_forward(duration=5):
    print("→ 执行：向前走...")
    car.translation(0, 100)  # Y轴正方向 = 前进
    time.sleep(duration)
    stop_car()

def move_backward(duration=5):
    print("→ 执行：向后走...")
    car.translation(0, -100)  # Y轴负方向 = 后退
    time.sleep(duration)
    stop_car()

def move_left(duration=5):
    print("→ 执行：向左平移...")
    car.translation(-100, 0)  # X轴负方向 = 左移
    time.sleep(duration)
    stop_car()

def move_right(duration=5):
    print("→ 执行：向右平移...")
    car.translation(100, 0)   # X轴正方向 = 右移
    time.sleep(duration)
    stop_car()

def turn_left(duration=5):
    print("→ 执行：原地左转...")
    car.set_velocity(50, 0, 1)  # 旋转参数为正 = 左转
    time.sleep(duration)
    stop_car()

def turn_right(duration=5):
    print("→ 执行：原地右转...")
    car.set_velocity(50, 0, -1)  # 旋转参数为负 = 右转
    time.sleep(duration)
    stop_car()

def show_menu():
    print("\n" + "="*40)
    print("       小车控制面板（SSH终端版）")
    print("="*40)
    print("  w : 向前走 5秒")
    print("  s : 向后走 5秒")
    print("  a : 向左平移 5秒")
    print("  d : 向右平移 5秒")
    print("  q : 原地左转 5秒")
    print("  e : 原地右转 5秒")
    print("  x : 立即停止小车")
    print("  quit : 退出程序")
    print("="*40)

def main():
    print("🚀 小车控制系统启动中...")

    stop_car()  # 确保初始状态停止

    try:
        while True:
            show_menu()
            cmd = input("\n请输入指令: ").strip().lower()

            if cmd == 'quit':
                print("👋 正在退出程序...")
                break
            elif cmd == 'w':
                move_forward(5)
            elif cmd == 's':
                move_backward(5)
            elif cmd == 'a':
                move_left(5)
            elif cmd == 'd':
                move_right(5)
            elif cmd == 'q':
                turn_left(5)
            elif cmd == 'e':
                turn_right(5)
            elif cmd == 'x':
                stop_car()
            else:
                print("⚠️ 无效指令，请重新输入！")

    except KeyboardInterrupt:
        print("\n\n🛑 用户中断（Ctrl+C）")
    finally:
        print("\n🔒 安全关闭小车...")
        stop_car()
        print("✅ 程序已安全退出")

if __name__ == '__main__':
    main()