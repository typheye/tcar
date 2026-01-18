#!/usr/bin/env python3
import socket
import json
import sys

SOCKET_PATH = "/tmp/servo_control.sock"

def send_command(cmd):
    """发送命令到守护进程"""
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(SOCKET_PATH)
        
        client.send(json.dumps(cmd).encode('utf-8'))
        response = client.recv(1024).decode('utf-8')
        
        client.close()
        return response
    except Exception as e:
        print(f"连接失败: {e}")
        return None

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='舵机控制客户端')
    parser.add_argument('--servo', '-s', type=int, choices=[1, 2], help='舵机编号')
    parser.add_argument('--step', '-t', type=int, help='单次移动步进 (-100~100)')
    parser.add_argument('--control', '-c', action='store_true', help='进入连续控制模式')
    parser.add_argument('--direction', '-d', type=int, choices=[-1, 0, 1], help='控制方向 (-1, 0, 1)')
    parser.add_argument('--speed', '-v', type=int, default=50, help='控制速度 (0~100)')
    parser.add_argument('--reset', '-r', action='store_true', help='重置到校准位置')
    parser.add_argument('--status', action='store_true', help='显示状态')
    
    args = parser.parse_args()
    
    if args.status:
        response = send_command({'type': 'status'})
        if response:
            data = json.loads(response)
            print(f"舵机1: {data['positions'][1]} (校准: {data['calibration'][1]})")
            print(f"舵机2: {data['positions'][2]} (校准: {data['calibration'][2]})")
    
    elif args.reset:
        send_command({'type': 'reset'})
    
    elif args.servo and args.step is not None and not args.control:
        # 单次移动模式
        if -100 <= args.step <= 100:
            send_command({'type': 'move', 'servo': args.servo, 'step': args.step})
    
    elif args.servo and args.control:
        # 连续控制模式
        active = args.direction != 0
        cmd = {
            'type': 'control',
            'servo': args.servo,
            'active': active,
            'direction': args.direction or 0,
            'speed': max(1, min(100, args.speed))
        }
        send_command(cmd)