#!/usr/bin/env python3
import sys

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='舵机控制程序')
    parser.add_argument('--servo', '-s', type=int, choices=[1, 2], help='舵机编号')
    parser.add_argument('--step', '-t', type=int, help='步进值 (-100~100)')
    parser.add_argument('--reset', action='store_true', help='重置')
    parser.add_argument('--control', '-c', action='store_true', help='连续控制')
    parser.add_argument('--direction', '-d', type=int, choices=[-1, 0, 1], default=0, help='方向')
    parser.add_argument('--speed', '-v', type=int, default=50, help='速度')
    
    args = parser.parse_args()
    
    # 调用客户端
    if args.reset:
        import subprocess
        subprocess.run(['sudo', 'python3', '/home/pi/TurboPi/HiwonderSDK/servo_client.py', '--reset'])
    
    elif args.servo and args.step is not None and not args.control:
        import subprocess
        subprocess.run(['sudo', 'python3', '/home/pi/TurboPi/HiwonderSDK/servo_client.py', 
                       '--servo', str(args.servo), '--step', str(args.step)])
    
    elif args.servo and args.control:
        import subprocess
        cmd = ['sudo', 'python3', '/home/pi/TurboPi/HiwonderSDK/servo_client.py',
               '--servo', str(args.servo), '--control', 
               '--direction', str(args.direction), '--speed', str(args.speed)]
        subprocess.run(cmd)