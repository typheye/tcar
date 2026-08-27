#!/usr/bin/env python3
# coding=utf8
import math
import os
import time

import pygame
import sys
import json
import socket
import signal
import threading

sys.path.append('/home/pi/TurboPi/')
import Utils.buzzer as BZ
import HiwonderSDK.Board as Board
import HiwonderSDK.mecanum as mecanum

# 映射PS2手柄按键值（修正版）
key_map = {"PSB_Y": 0, "PSB_B": 1, "PSB_A": 2, "PSB_X": 3,
           "PSB_L1": 4, "PSB_R1": 5, "PSB_L2": 6, "PSB_R2": 7,
           "PSB_SELECT": 8, "PSB_START": 9, "PSB_L3": 10, "PSB_R3": 11}

# Socket通信配置
SOCKET_PATH = "/tmp/servo_control.sock"
SENSOR_SERVER_ADDRESS = ("192.168.66.3", 8888)

# 全局运行标志
RUNNING = True

def signal_handler(signum, frame):
    """信号处理函数"""
    global RUNNING
    print(f"PS2控制器收到退出信号 {signum}")
    RUNNING = False

class ChassisController:
    """小车底盘控制器"""
    def __init__(self):
        if mecanum is not None:
            self.chassis = mecanum.MecanumChassis()
            print("小车底盘初始化成功")
        else:
            self.chassis = None
            print("警告: 小车底盘使用模拟模式")
        
        # 小车控制参数
        self.max_speed = 60      # 最大线速度 0~60
        self.max_yaw_rate = 2.0   # 最大偏航角速度 -2~2
        self.min_yaw_rate = 0.22  # keeps all rotation wheels above PWM 26
        self.move_active = False  # 移动激活状态
        
        # 左摇杆控制
        self.last_Lxy = [0, 0]    # 左摇杆值
        self.deadzone = 0.02      # only suppress electrical center noise
        self.min_speed = 26.0     # overcome mecanum static friction
        
    def map_joystick_to_velocity(self, value):
        """映射摇杆值到速度（带死区和曲线）"""
        abs_value = abs(value)
        if abs_value < self.deadzone:
            return 0
        
        # 归一化到 0-1 范围
        normalized = (abs_value - self.deadzone) / (1.0 - self.deadzone)
        
        # 应用平方曲线（更精细的控制）
        normalized = normalized ** 1.5
        
        # 映射到速度 0-60
        speed = self.min_speed + normalized * (self.max_speed - self.min_speed)
        return speed
    
    def map_joystick_to_yaw(self, value):
        """映射摇杆值到偏航角速度"""
        abs_value = abs(value)
        if abs_value < self.deadzone:
            return 0
        
        # 归一化到 0-1 范围
        normalized = (abs_value - self.deadzone) / (1.0 - self.deadzone)
        
        # 应用平方曲线
        normalized = normalized ** 1.5
        
        # 映射到偏航角速度 -2~2
        yaw = normalized * self.max_yaw_rate
        return yaw
    
    def control_chassis(self, left_x, left_y):
        """控制小车底盘"""
        if self.chassis is None:
            # 模拟模式
            speed = self.map_joystick_to_velocity(abs(left_y))
            if abs(left_y) > self.deadzone:
                direction = 90 if left_y > 0 else 270  # 前进或后退
                print(f"模拟小车: 速度={speed:.1f}, 方向={direction}")
            return
        
        yaw_rate = 0
        magnitude = min(1.0, math.hypot(left_x, left_y))
        if magnitude <= self.deadzone:
            linear_speed = 0
            direction = 0
        else:
            linear_speed = self.map_joystick_to_velocity(magnitude)
            # Preserve the full two-axis vector.  The old dominant-axis branch
            # snapped diagonal input to four directions and produced drifting.
            direction = math.degrees(math.atan2(-left_y, left_x)) % 360.0
        
        # 设置小车速度
        try:
            self.chassis.set_velocity(linear_speed, direction, yaw_rate)
        except Exception as e:
            print(f"小车控制错误: {e}")
    
    def turn(self, direction, yaw_rate=0.3):
        """转向
        direction: 1=左转, -1=右转
        """
        if self.chassis is None:
            print(f"模拟: {'左' if direction == 1 else '右'}转")
            return
        
        # 转向
        yaw_rate = max(self.min_yaw_rate, abs(yaw_rate))
        yaw_rate = -yaw_rate if direction == 1 else yaw_rate
        try:
            self.chassis.set_velocity(0, 0, yaw_rate)
        except Exception as e:
            print(f"平移控制错误: {e}")
    
    def stop(self):
        """停止小车"""
        if self.chassis is not None:
            try:
                self.chassis.set_velocity(0, 0, 0)
            except:
                pass

class ServoController:
    def __init__(self, use_direct=True):
        """初始化舵机控制器"""
        self.use_direct = use_direct  # 强制使用直接控制
        self.calibration = self.load_calibration()
        self.current_pos = {
            1: self.calibration.get(1, 1500),
            2: self.calibration.get(2, 1500)
        }
        
        # 舵机限位（根据您的示例）
        self.servo_limits = {
            1: {"min": self.calibration.get(1, 1500) - 700,  # 舵机1下限
                "max": self.calibration.get(1, 1500) + 300},  # 舵机1上限
            2: {"min": self.calibration.get(2, 1500) - 700,  # 舵机2下限
                "max": self.calibration.get(2, 1500) + 700}   # 舵机2上限
        }
        
        print(f"舵机限位 - 舵机1: {self.servo_limits[1]['min']}~{self.servo_limits[1]['max']}")
        print(f"舵机限位 - 舵机2: {self.servo_limits[2]['min']}~{self.servo_limits[2]['max']}")
        
        self.socket = None
        if not use_direct:
            self.connect_to_daemon()
        else:
            print("使用直接控制模式")
    
    def load_calibration(self):
        """加载校准位置"""
        try:
            from yaml_handle import get_yaml_data, servo_file_path
            servo_data = get_yaml_data(servo_file_path)
            return {
                1: servo_data.get("servo1", 1500),
                2: servo_data.get("servo2", 1500)
            }
        except:
            print("警告: 使用默认校准位置")
            return {1: 1500, 2: 1500}
    
    def connect_to_daemon(self):
        """连接到舵机守护进程"""
        try:
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.connect(SOCKET_PATH)
            print("已连接到舵机守护进程")
            return True
        except:
            print("警告: 无法连接到舵机守护进程，使用直接控制")
            self.socket = None
            return False
    
    def move_servo_direct(self, servo_id, step, smooth_time=50):
        """直接移动舵机（无守护进程时使用）"""
        if Board is None:
            print(f"模拟: 舵机{servo_id} 移动 {step}")
            return True
            
        new_pos = self.current_pos[servo_id] + step
        
        # 应用限位
        if new_pos < self.servo_limits[servo_id]["min"]:
            new_pos = self.servo_limits[servo_id]["min"]
        elif new_pos > self.servo_limits[servo_id]["max"]:
            new_pos = self.servo_limits[servo_id]["max"]
        
        if new_pos != self.current_pos[servo_id]:
            try:
                # 使用平滑移动时间
                Board.setPWMServoPulse(servo_id, new_pos, smooth_time)
                self.current_pos[servo_id] = new_pos
                return True
            except Exception as e:
                print(f"舵机移动错误: {e}")
                return False
        return False
    
    def control_servo(self, servo_id, step):
        """控制舵机移动（简化版本）"""
        # 限制步长范围，确保平滑
        step = max(-50, min(50, step))
        return self.move_servo_direct(servo_id, step, smooth_time=30)
    
    def reset_servos(self):
        """重置舵机到校准位置"""
        print("重置舵机到校准位置")
        for servo_id in [1, 2]:
            self.current_pos[servo_id] = self.calibration[servo_id]
            if Board:
                print(f"重置舵机{servo_id} 到 {self.calibration[servo_id]}")
                Board.setPWMServoPulse(servo_id, self.calibration[servo_id], 500)
            time.sleep(0.02)
        print("舵机已重置")
        return True

class PS2Controller:
    def __init__(self):
        """初始化PS2控制器"""
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        pygame.init()  # 初始化所有pygame模块
        pygame.joystick.init()
        
        self.shield = True  # 模拟模式/数字模式
        self.connected = False
        self.js = None
        
        # 初始化舵机控制器
        self.servo_ctrl = ServoController(use_direct=True)
        
        # 初始化小车控制器
        self.chassis_ctrl = ChassisController()
        
        # 右摇杆相关（舵机控制）
        self.last_Rxy = [0, 0]
        self.deadzone = 0.02  # only suppress electrical center noise
        self.min_servo_speed = 4.0
        
        # 左摇杆相关（小车控制）
        self.last_Lxy = [0, 0]
        
        # 舵机平滑控制变量
        self.target_speed = {1: 0, 2: 0}  # 目标速度
        self.current_speed = {1: 0, 2: 0}  # 当前速度
        self.smoothing_factor = 0.3  # 平滑因子
        
        # 控制模式
        self.control_mode = "joystick"
        
        # 摇杆轴映射
        self.axis_mapping = {
            "left_x": 0,   # 左摇杆左右（小车转向）
            "left_y": 1,   # 左摇杆上下（小车前后）
            "right_x": 2,  # 右摇杆左右（舵机2）
            "right_y": 3   # 右摇杆上下（舵机1）
        }
        
        # 按钮状态
        self.l1_pressed = False
        self.r1_pressed = False
        self.calibration_combo_active = False
        self.calibration_combo_since = None
        self.calibration_combo_cooldown_until = 0.0
        self.calibration_monitor = None
        
        # 导入math模块用于角度计算
        import math
        self.math = math
    
    def joystick_init(self):
        """初始化手柄"""
        count = pygame.joystick.get_count()
        print(f"检测到手柄数量: {count}")
        
        if count > 0:
            self.js = pygame.joystick.Joystick(0)
            self.js.init()
            
            print(f"手柄名称: {self.js.get_name()}")
            print(f"轴数量: {self.js.get_numaxes()}")
            print(f"按钮数量: {self.js.get_numbuttons()}")
            print(f"帽子数量: {self.js.get_numhats()}")
            
            print(f"模式: {'模拟' if self.shield else '数字'}")

            return True
        return False
    
    def map_joystick_to_speed(self, value):
        """映射摇杆值到舵机速度（带死区和曲线）"""
        abs_value = abs(value)
        if abs_value < self.deadzone:
            return 0
        
        # 归一化到 0-1 范围
        normalized = (abs_value - self.deadzone) / (1.0 - self.deadzone)
        
        # 应用平方曲线（更精细的控制）
        normalized = normalized ** 1.5
        
        # 映射到速度 0-50
        speed = self.min_servo_speed + normalized * (50 - self.min_servo_speed)
        return speed
    
    def get_safe_button(self, button_id):
        """安全获取按钮状态"""
        try:
            if self.js and button_id < self.js.get_numbuttons():
                return self.js.get_button(button_id)
        except:
            pass
        return False

    def request_full_sensor_calibration(self):
        """Request full gyro/DMP/magnetometer calibration from tCar service."""
        if self.calibration_monitor and self.calibration_monitor.is_alive():
            print("传感器校准已在进行")
            return
        self.chassis_ctrl.stop()
        self.target_speed = {1: 0, 2: 0}
        self.current_speed = {1: 0, 2: 0}
        self.calibration_monitor = threading.Thread(
            target=self._monitor_sensor_calibration,
            name="sensor-calibration-monitor",
            daemon=True,
        )
        self.calibration_monitor.start()

    def _sensor_command(self, command, timeout=1.0):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            sock.sendto(command, SENSOR_SERVER_ADDRESS)
            reply, _ = sock.recvfrom(256)
            return reply.decode("utf-8", errors="replace")
        finally:
            sock.close()

    def _monitor_sensor_calibration(self):
        auto_turning = False
        turn_rate = None
        try:
            reply = self._sensor_command(b"calibrate_all")
            print(f"传感器校准请求: {reply}")
            if not reply.startswith(("started:", "busy:")):
                raise RuntimeError(reply)
            if reply.startswith("started:"):
                BZ.calibration_started()
            last_phase = None
            while RUNNING:
                status = self._sensor_command(b"calibration_status")
                phase = status.split(":", 1)[0]
                progress = None
                if phase == "magnetometer" and ":" in status:
                    try:
                        progress = float(status.split(":", 1)[1])
                    except ValueError:
                        pass
                if phase != last_phase:
                    print(f"传感器校准阶段: {status}")
                    if phase == "magnetometer":
                        # tCar integrates the calibrated Z gyro and ends this
                        # phase after one real 360-degree rotation.
                        turn_rate = 0.30
                        self.chassis_ctrl.turn(1, turn_rate)
                        auto_turning = True
                    elif auto_turning:
                        self.chassis_ctrl.stop()
                        auto_turning = False
                    last_phase = phase
                if auto_turning and progress is not None:
                    if progress >= 352.0:
                        desired_rate = 0.22
                    elif progress >= 330.0:
                        desired_rate = 0.22
                    elif progress >= 285.0:
                        desired_rate = 0.24
                    else:
                        desired_rate = 0.30
                    if desired_rate != turn_rate:
                        turn_rate = desired_rate
                        self.chassis_ctrl.turn(1, turn_rate)
                if phase == "complete":
                    BZ.calibration_finished()
                    return
                if phase == "failed":
                    BZ.init(0.5)
                    return
                # A short polling interval keeps final angular overshoot below
                # the old quarter-second control lag.
                time.sleep(0.05)
        except Exception as exc:
            print(f"传感器校准请求失败: {exc}")
            BZ.init(0.5)
        finally:
            if auto_turning:
                self.chassis_ctrl.stop()
    
    def update_smooth_speed(self):
        """更新舵机平滑速度"""
        for servo_id in [1, 2]:
            # 平滑过渡
            self.current_speed[servo_id] += (self.target_speed[servo_id] - self.current_speed[servo_id]) * self.smoothing_factor
            
            # 如果速度很小，直接设为0
            if abs(self.current_speed[servo_id]) < 0.5:
                self.current_speed[servo_id] = 0
            
            # 应用速度
            if abs(self.current_speed[servo_id]) > 0.5:
                step = int(self.current_speed[servo_id])
                self.servo_ctrl.control_servo(servo_id, step)
    
    def process_left_joystick(self, x, y):
        """处理左摇杆输入 - 控制小车"""
        # 注意：摇杆坐标系统：
        # x: 左为负，右为正
        # y: 上为负，下为正
        
        # 只有当L1和R1都没有按下时，才使用摇杆控制小车
        if not self.l1_pressed and not self.r1_pressed:
            self.chassis_ctrl.control_chassis(x, y)
        else:
            # 如果L1或R1按下，停止小车
            self.chassis_ctrl.stop()
    
    def process_right_joystick(self, x, y):
        """处理右摇杆输入 - 控制舵机"""
        # 注意：摇杆坐标系统：
        # x: 左为负，右为正
        # y: 上为负，下为正
        
        # 舵机1（上下控制）：摇杆上下 -> 舵机1
        if abs(y) > self.deadzone:
            # 摇杆向上（负值）-> 舵机向上移动（负步长）
            speed_y = self.map_joystick_to_speed(y)
            self.target_speed[1] = -speed_y if y < 0 else speed_y
        else:
            self.target_speed[1] = 0
        
        # 舵机2（左右控制）：摇杆左右 -> 舵机2
        if abs(x) > self.deadzone:
            # 摇杆向左（负值）-> 舵机向左移动（负步长）
            speed_x = self.map_joystick_to_speed(x)
            self.target_speed[2] = speed_x if x < 0 else -speed_x  # 反转符号
        else:
            self.target_speed[2] = 0
    
    def process_buttons(self):
        """处理按钮输入"""
        try:
            select_pressed = self.get_safe_button(key_map["PSB_SELECT"])
            x_pressed = self.get_safe_button(key_map["PSB_X"])
            now = time.monotonic()

            # SELECT + X: full inertial and magnetometer recalibration.
            if self.calibration_combo_active:
                if not select_pressed and not x_pressed:
                    self.calibration_combo_active = False
                    self.calibration_combo_since = None
                    self.calibration_combo_cooldown_until = now + 0.35
                return
            if select_pressed and x_pressed:
                if now < self.calibration_combo_cooldown_until:
                    return
                if self.calibration_combo_since is None:
                    self.calibration_combo_since = now
                    return
                # Both buttons must remain down for 120 ms.  This filters
                # contact bounce and prevents a nearby single-X event.
                if now - self.calibration_combo_since < 0.12:
                    return
                self.calibration_combo_active = True
                self.calibration_combo_since = None
                print("SELECT + X: 重新校准陀螺仪、姿态零点和磁力计")
                self.request_full_sensor_calibration()
                return
            self.calibration_combo_since = None

            # SELECT + START 切换模式
            if select_pressed:
                time.sleep(0.01)
                if self.get_safe_button(key_map["PSB_START"]):
                    self.shield = not self.shield
                    print(f"模式切换: {'模拟' if self.shield else '数字'}")
                    BZ.keydown_combination_PSControler()
                    time.sleep(0.5)
                    return
            
            # L1 左转向
            l1_current = self.get_safe_button(key_map["PSB_L1"])
            if l1_current and not self.l1_pressed:
                print("L1按下: 左转向")
                self.l1_pressed = True
                if self.shield:  # 模拟模式
                    self.chassis_ctrl.turn(1)  # 左转向
                else:
                    BZ.keydown_PSControler()
            elif not l1_current and self.l1_pressed:
                print("L1释放")
                self.l1_pressed = False
                self.chassis_ctrl.stop()
            
            # R1 右转向
            l2_current = self.get_safe_button(key_map["PSB_R1"])
            if l2_current and not self.r1_pressed:
                print("R1按下: 右转向")
                self.r1_pressed = True
                if self.shield:  # 模拟模式
                    self.chassis_ctrl.turn(-1)  # 右转向
                else:
                    BZ.keydown_PSControler()
            elif not l2_current and self.r1_pressed:
                print("R1释放")
                self.r1_pressed = False
                self.chassis_ctrl.stop()

            # L2
            if self.get_safe_button(key_map["PSB_L2"]):
                print("L2按下")
                BZ.keydown_PSControler()
                # 等待按钮释放
                while self.get_safe_button(key_map["PSB_L2"]):
                    pygame.event.pump()
                    time.sleep(0.01)

            # R2
            if self.get_safe_button(key_map["PSB_R2"]):
                print("R2按下")
                BZ.keydown_PSControler()
                # 等待按钮释放
                while self.get_safe_button(key_map["PSB_R2"]):
                    pygame.event.pump()
                    time.sleep(0.01)
            
            # L3
            if self.get_safe_button(key_map["PSB_L3"]):
                print("L3按下")
                BZ.keydown_PSControler()
                # 等待按钮释放
                while self.get_safe_button(key_map["PSB_L3"]):
                    pygame.event.pump()
                    time.sleep(0.01)
            
            # R3 重置舵机
            if self.get_safe_button(key_map["PSB_R3"]):
                print("R3按下: 重置舵机")
                BZ.keydown_PSControler()
                if self.shield:  # 模拟模式
                    self.servo_ctrl.reset_servos()
                    # 重置速度
                    self.target_speed = {1: 0, 2: 0}
                    self.current_speed = {1: 0, 2: 0}
                # 等待按钮释放
                while self.get_safe_button(key_map["PSB_R3"]):
                    pygame.event.pump()
                    time.sleep(0.01)
            
            # Y - 使用边缘检测
            if self.get_safe_button(key_map["PSB_Y"]):
                print("Y按下")
                BZ.keydown_PSControler()
                # 等待按钮释放
                while self.get_safe_button(key_map["PSB_Y"]):
                    pygame.event.pump()
                    time.sleep(0.01)
            
            # B - 使用边缘检测
            if self.get_safe_button(key_map["PSB_B"]):
                print("B按下")
                BZ.keydown_PSControler()
                # 等待按钮释放
                while self.get_safe_button(key_map["PSB_B"]):
                    pygame.event.pump()
                    time.sleep(0.01)
            
            # A - 使用边缘检测
            if self.get_safe_button(key_map["PSB_A"]):
                print("A按下")
                BZ.keydown_PSControler()
                # 等待按钮释放
                while self.get_safe_button(key_map["PSB_A"]):
                    pygame.event.pump()
                    time.sleep(0.01)
            
            # X - 使用边缘检测
            if x_pressed:
                print("X按下")
                BZ.keydown_PSControler()
                # 等待按钮释放
                while self.get_safe_button(key_map["PSB_X"]):
                    pygame.event.pump()
                    time.sleep(0.01)

            hat_x, hat_y = self.js.get_hat(0)
            """处理方向键输入"""
            # 方向键控制（数字模式）
            if hat_y == 1:  # 上
                BZ.keydown_PSControler()
                while hat_y == 1:
                    hat_x, hat_y = self.js.get_hat(0)
                    pygame.event.pump()
                    time.sleep(0.01)
            elif hat_y == -1:  # 下
                BZ.keydown_PSControler()
                while hat_y == -1:
                    hat_x, hat_y = self.js.get_hat(0)
                    pygame.event.pump()
                    time.sleep(0.01)
            else:
                pass
            
            if hat_x == -1:  # 左
                BZ.keydown_PSControler()
                while hat_x == -1:
                    hat_x, hat_y = self.js.get_hat(0)
                    pygame.event.pump()
                    time.sleep(0.01)
            elif hat_x == 1:  # 右
                BZ.keydown_PSControler()
                while hat_x == 1:
                    hat_x, hat_y = self.js.get_hat(0)
                    pygame.event.pump()
                    time.sleep(0.01)
            else:
                pass
            
        except Exception as e:
            print(f"按钮处理错误: {e}")
    
    def run(self):
        """主循环"""
        print("=" * 50)
        print("PS2控制器启动中...")
        print("=" * 50)
        
        # 测试舵机初始状态
        self.servo_ctrl.reset_servos()
        
        last_update_time = time.time()
        frame_count = 0
        
        while RUNNING:
            # 检测手柄连接
            if os.path.exists("/dev/input/js0"):
                if not self.connected:
                    if self.joystick_init():
                        self.connected = True
                        print("手柄已连接")
            else:
                if self.connected:
                    self.connected = False
                    if self.js:
                        self.js.quit()
                    pygame.joystick.quit()
                    print("手柄已断开")
            
            if self.connected:
                # 处理事件
                for event in pygame.event.get():
                    if event.type == pygame.JOYAXISMOTION:
                        # 左摇杆移动事件（小车控制）
                        if event.axis == self.axis_mapping["left_x"] or event.axis == self.axis_mapping["left_y"]:
                            current_Lx = self.js.get_axis(self.axis_mapping["left_x"])
                            current_Ly = self.js.get_axis(self.axis_mapping["left_y"])
                            if self.shield:  # 模拟模式
                                self.process_left_joystick(current_Lx, current_Ly)
                        
                        # 右摇杆移动事件（舵机控制）
                        if event.axis == self.axis_mapping["right_x"] or event.axis == self.axis_mapping["right_y"]:
                            current_Rx = self.js.get_axis(self.axis_mapping["right_x"])
                            current_Ry = self.js.get_axis(self.axis_mapping["right_y"])
                            
                            if self.shield:  # 模拟模式
                                self.process_right_joystick(current_Rx, current_Ry)
                    
                    elif event.type == pygame.JOYHATMOTION:
                        # 方向键事件
                        pass
                
                # 处理按钮
                self.process_buttons()
                
                # 更新舵机平滑速度
                self.update_smooth_speed()
                
                # 帧率统计
                frame_count += 1
                current_time = time.time()
                if current_time - last_update_time > 1.0:
                    # print(f"帧率: {frame_count} FPS")
                    frame_count = 0
                    last_update_time = current_time
            
            # 控制更新频率
            time.sleep(0.02)  # 50Hz

if __name__ == '__main__':
    # 注册信号处理器
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        controller = PS2Controller()
        controller.run()
    except KeyboardInterrupt:
        print("\n程序被键盘中断")
    except Exception as e:
        print(f"程序错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("正在清理资源...")
        # 停止所有舵机移动
        controller.target_speed = {1: 0, 2: 0}
        controller.current_speed = {1: 0, 2: 0}
        controller.update_smooth_speed()
        
        # 停止小车
        controller.chassis_ctrl.stop()
        
        # 清理手柄资源
        if controller.connected and controller.js:
            controller.js.quit()
        pygame.joystick.quit()
        pygame.quit()
        
        print("PS2控制器资源已清理")
