#!/usr/bin/env python3
import sys
import time
import yaml
import os
import socket
import threading
import json

sys.path.append('/home/pi/TurboPi/')
import yaml_handle
try:
    import HiwonderSDK.Board as Board
except ImportError:
    sys.exit(1)

# 配置文件路径
CALIBRATION_FILE = "/home/pi/TurboPi/HiwonderSDK/servo_config.yaml"
CURRENT_FILE = "/home/pi/TurboPi/HiwonderSDK/servo_config_now.yaml"
SOCKET_PATH = "/tmp/servo_control.sock"

class ServoDaemon:
    def __init__(self):
        self.running = True
        self.control_active = {1: False, 2: False}
        self.control_direction = {1: 0, 2: 0}  # -1, 0, 1
        self.control_speed = {1: 0, 2: 0}      # 0-100
        
        # 加载位置
        self.calibration = self.load_calibration()
        self.positions = self.load_current_positions()
        
        # 创建socket服务器
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)
        self.server.bind(SOCKET_PATH)
        self.server.listen(1)
        
        print("舵机守护进程已启动")
    
    def load_calibration(self):
        """加载校准位置"""
        try:
            servo_data = yaml_handle.get_yaml_data(yaml_handle.servo_file_path)
            return {
                1: servo_data["servo1"],
                2: servo_data["servo2"]
            }
        except:
            return {1: 1500, 2: 1500}
    
    def load_current_positions(self):
        """加载当前位置"""
        if not os.path.exists(CURRENT_FILE):
            return self.load_calibration()
        try:
            servo_data = yaml_handle.get_yaml_data(yaml_handle.servo_now_file_path)
            return {
                1: servo_data["servo1"],
                2: servo_data["servo2"]
            }
        except:
            return self.calibration.copy()
    
    def save_current_positions(self):
        """保存当前位置"""
        try:
            data = {
                'servo1': self.positions.get(1, self.calibration[1]),
                'servo2': self.positions.get(2, self.calibration[2])
            }
            yaml_handle.save_yaml_data(data, yaml_handle.servo_now_file_path)

        except:
            pass
    
    def move_servo(self, servo_id, step):
        """移动舵机一步"""
        current = self.positions.get(servo_id, self.calibration[servo_id])
        new_pos = current + step
        
        s1_max =  self.calibration[1] + 300
        s1_min = self.calibration[1] - 700
        s2_max =  self.calibration[2] + 700
        s2_min = self.calibration[2] - 700

        if servo_id == 1:
            if new_pos < s1_min:
                new_pos = s1_min
            elif new_pos > s1_max:
                new_pos = s1_max
        elif servo_id == 2:
            if new_pos < s2_min:
                new_pos = s2_min
            elif new_pos > s2_max:
                new_pos = s2_max
        
        if new_pos != current:
            try:
                Board.setPWMServoPulse(servo_id, new_pos, 100)  # 快速移动
                self.positions[servo_id] = new_pos
                self.save_current_positions()
                return True
            except:
                pass
        return False
    
    def continuous_control_loop(self):
        """连续控制循环"""
        while self.running:
            moved = False
            
            for servo_id in [1, 2]:
                if self.control_active[servo_id] and self.control_speed[servo_id] > 0:
                    # 计算移动步长，根据速度调整
                    step = self.control_direction[servo_id] * self.control_speed[servo_id] * 2
                    if self.move_servo(servo_id, step):
                        moved = True
            
            # 如果有移动，稍作延迟；如果没有移动，延迟更长
            if moved:
                time.sleep(0.08)  # 50Hz，平滑移动
            else:
                time.sleep(0.03)
        
        # 退出前保存位置
        self.save_current_positions()
    
    def handle_command(self, conn):
        """处理客户端命令"""
        try:
            data = conn.recv(1024).decode('utf-8')
            if not data:
                return
            
            try:
                cmd = json.loads(data)
                cmd_type = cmd.get('type')
                
                if cmd_type == 'move':
                    servo_id = cmd.get('servo')
                    step = cmd.get('step')
                    if servo_id in [1, 2] and -100 <= step <= 100:
                        self.move_servo(servo_id, step * 10)
                        conn.send(b'OK')
                
                elif cmd_type == 'control':
                    servo_id = cmd.get('servo')
                    active = cmd.get('active', False)
                    direction = cmd.get('direction', 0)  # -1, 0, 1
                    speed = cmd.get('speed', 50)         # 0-100
                    
                    if servo_id in [1, 2]:
                        self.control_active[servo_id] = active
                        self.control_direction[servo_id] = direction
                        self.control_speed[servo_id] = speed
                        conn.send(b'OK')
                
                elif cmd_type == 'reset':
                    for servo_id in [1, 2]:
                        self.positions[servo_id] = self.calibration[servo_id]
                        Board.setPWMServoPulse(servo_id, self.calibration[servo_id], 500)
                    self.save_current_positions()
                    conn.send(b'OK')
                
                elif cmd_type == 'status':
                    status = {
                        'positions': self.positions,
                        'calibration': self.calibration
                    }
                    conn.send(json.dumps(status).encode('utf-8'))
                
                else:
                    conn.send(b'ERROR: Unknown command')
                    
            except json.JSONDecodeError:
                conn.send(b'ERROR: Invalid JSON')
                
        except Exception as e:
            conn.send(f'ERROR: {str(e)}'.encode('utf-8'))
        finally:
            conn.close()
    
    def run(self):
        """运行守护进程"""
        # 启动连续控制线程
        control_thread = threading.Thread(target=self.continuous_control_loop)
        control_thread.daemon = True
        control_thread.start()
        
        print(f"Socket服务器监听: {SOCKET_PATH}")
        
        while self.running:
            try:
                conn, _ = self.server.accept()
                self.handle_command(conn)
            except KeyboardInterrupt:
                self.running = False
                break
            except Exception as e:
                print(f"服务器错误: {e}")
        
        self.server.close()
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)
        print("舵机守护进程已停止")

if __name__ == '__main__':
    daemon = ServoDaemon()
    daemon.run()