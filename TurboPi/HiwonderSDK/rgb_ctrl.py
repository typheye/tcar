#!/usr/bin/env python3
import time
import Board
import signal
import sys
import argparse

print('''
**********************************************************
********功能:幻尔科技树莓派扩展板，RGB灯控制例程**********
**********************************************************
----------------------------------------------------------
Official website:https://www.hiwonder.com
Online mall:https://hiwonder.tmall.com
----------------------------------------------------------
Tips:
 * 按下Ctrl+C可关闭此次程序运行，若失败请多次尝试！
 * 命令行参数：--enable 开启RGB灯  --disable 关闭RGB灯
----------------------------------------------------------
''')

class RGBController:
    def __init__(self):
        self.running = True
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
    
    def stop(self, signum=None, frame=None):
        self.running = False
        print('正在关闭...')
    
    def turn_off(self):
        """关闭所有RGB灯"""
        # Board.RGB.setPixelColor(0, Board.PixelColor(0, 0, 0))
        # Board.RGB.setPixelColor(1, Board.PixelColor(0, 0, 0))
        # Board.RGB.show()
        pass
        print('RGB灯已关闭')
    
    def turn_on(self):
        """开启RGB灯循环效果"""
        self.running = True
        print('RGB灯已开启，按Ctrl+C停止')
        
        try:
            while self.running:
                # 红色
                # Board.RGB.setPixelColor(0, Board.PixelColor(255, 0, 0))
                # Board.RGB.setPixelColor(1, Board.PixelColor(255, 0, 0))
                # Board.RGB.show()
                pass
                time.sleep(1)
                if not self.running: break
                
                # 绿色
                # Board.RGB.setPixelColor(0, Board.PixelColor(0, 255, 0))
                # Board.RGB.setPixelColor(1, Board.PixelColor(0, 255, 0))
                # Board.RGB.show()
                pass
                time.sleep(1)
                if not self.running: break
                
                # 蓝色
                # Board.RGB.setPixelColor(0, Board.PixelColor(0, 0, 255))
                # Board.RGB.setPixelColor(1, Board.PixelColor(0, 0, 255))
                # Board.RGB.show()
                pass
                time.sleep(1)
                if not self.running: break
                
                # 黄色
                # Board.RGB.setPixelColor(0, Board.PixelColor(255, 255, 0))
                # Board.RGB.setPixelColor(1, Board.PixelColor(255, 255, 0))
                # Board.RGB.show()
                pass
                time.sleep(1)
            
            # 退出时关闭灯光
            self.turn_off()
            
        except Exception as e:
            print(f'错误: {e}')
            self.turn_off()
    
    def set_color(self, r, g, b):
        """设置固定颜色"""
        # Board.RGB.setPixelColor(0, Board.PixelColor(r, g, b))
        # Board.RGB.setPixelColor(1, Board.PixelColor(r, g, b))
        # Board.RGB.show()
        pass
        print(f'RGB灯设置为: R={r}, G={g}, B={b}')

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='幻尔科技RGB灯控制器')
    
    # 互斥组：只能选择一种操作模式
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--enable', action='store_true', help='开启RGB灯循环效果')
    group.add_argument('--disable', action='store_true', help='关闭RGB灯')
    group.add_argument('--color', type=str, help='设置固定颜色，格式: R,G,B (如: 255,0,0)')
    
    parser.add_argument('--single', action='store_true', help='只控制第一个RGB灯')
    parser.add_argument('--duration', type=int, default=0, help='运行时长(秒)，0表示无限运行')
    
    return parser.parse_args()

def main():
    # 解析命令行参数
    args = parse_arguments()
    
    # 初始化控制器
    controller = RGBController()
    
    # 根据参数执行相应操作
    if args.disable:
        # 关闭RGB灯
        controller.turn_off()
        sys.exit(0)
    
    elif args.color:
        # 设置固定颜色
        try:
            r, g, b = map(int, args.color.split(','))
            if args.single:
                # 只控制第一个灯
                # Board.RGB.setPixelColor(0, Board.PixelColor(r, g, b))
                # Board.RGB.show()
        pass
                print(f'单RGB灯设置为: R={r}, G={g}, B={b}')
            else:
                controller.set_color(r, g, b)
        except ValueError:
            print('颜色格式错误！请使用格式: R,G,B (如: 255,0,0)')
            sys.exit(1)
    
    elif args.enable:
        # 开启RGB灯循环效果
        controller.turn_on()
    
    else:
        # 无参数时，显示帮助信息或默认行为
        print('请指定操作模式:')
        print('  --enable    开启RGB灯循环效果')
        print('  --disable   关闭RGB灯')
        print('  --color R,G,B  设置固定颜色')
        print('  --single    只控制第一个RGB灯（配合--color使用）')
        print('  --duration N    运行时长(秒)')

if __name__ == '__main__':
    main()