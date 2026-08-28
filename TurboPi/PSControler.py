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
import struct
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
HEADING_RESET_MIN_YAW_RATE = 0.15
HEADING_RESET_TOLERANCE_DEG = 5.0
HEADING_RESET_PULSE_SECONDS = 0.07
HEADING_RESET_BRAKE_SECONDS = 0.12
HEADING_RESET_MAX_FINAL_PULSES = 4

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
        self.min_yaw_rate = 0.15  # lowest closed-loop rate; below this brake
        self.move_active = False  # 移动激活状态
        
        # 左摇杆控制
        self.last_Lxy = [0, 0]    # 左摇杆值
        self.deadzone = 0.06      # suppress measured analog center noise
        self.release_deadzone = 0.035
        self.min_speed = 26.0     # overcome mecanum static friction
        self.command_lock = threading.RLock()
        self.drive_authorized = False
        self.brake_engaged = False

    def _stop_locked(self):
        self.move_active = False
        if self.chassis is None:
            return True
        try:
            self.chassis.reset_motors()
            return True
        except Exception as exc:
            print(f"底盘停止错误: {exc}")
            return False

    def set_drive_authorization(self, throttle, brake=False):
        """Set the hard motion gate used by every chassis command."""
        with self.command_lock:
            was_enabled = self.drive_authorized and not self.brake_engaged
            self.brake_engaged = bool(brake)
            self.drive_authorized = bool(throttle) and not self.brake_engaged
            if (was_enabled and not self.drive_authorized) or self.brake_engaged:
                self._stop_locked()

    def is_drive_enabled(self):
        with self.command_lock:
            return self.drive_authorized and not self.brake_engaged

    def emergency_stop(self):
        """Latch the brake and synchronously command all motors to zero."""
        with self.command_lock:
            self.brake_engaged = True
            self.drive_authorized = False
            return self._stop_locked()
        
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
        if not self.is_drive_enabled():
            self.stop()
            return False
        if self.chassis is None:
            # 模拟模式
            speed = self.map_joystick_to_velocity(abs(left_y))
            if abs(left_y) > self.deadzone:
                direction = 90 if left_y > 0 else 270  # 前进或后退
                print(f"模拟小车: 速度={speed:.1f}, 方向={direction}")
            return
        
        yaw_rate = 0
        magnitude = min(1.0, math.hypot(left_x, left_y))
        threshold = self.release_deadzone if self.move_active else self.deadzone
        if magnitude <= threshold:
            if self.move_active:
                self.stop()
            return

        self.move_active = True
        linear_speed = self.map_joystick_to_velocity(magnitude)
        # Preserve the full two-axis vector. The wheel mixer removes only
        # terms too small to overcome motor friction.
        direction = math.degrees(math.atan2(-left_y, left_x)) % 360.0
        
        # 设置小车速度
        try:
            with self.command_lock:
                if not self.drive_authorized or self.brake_engaged:
                    return False
                self.chassis.set_velocity(linear_speed, direction, yaw_rate)
            return True
        except Exception as e:
            print(f"小车控制错误: {e}")
    
    def turn(self, direction, yaw_rate=0.3):
        """转向
        direction: 1=左转, -1=右转
        """
        if not self.is_drive_enabled():
            return False
        if self.chassis is None:
            print(f"模拟: {'左' if direction == 1 else '右'}转")
            return True
        
        # 转向
        yaw_rate = max(self.min_yaw_rate, abs(yaw_rate))
        yaw_rate = -yaw_rate if direction == 1 else yaw_rate
        try:
            with self.command_lock:
                if not self.drive_authorized or self.brake_engaged:
                    return False
                self.chassis.set_velocity(0, 0, yaw_rate)
            return True
        except Exception as e:
            print(f"平移控制错误: {e}")
            return False
    
    def stop(self):
        """停止小车"""
        with self.command_lock:
            return self._stop_locked()

class ServoController:
    HORIZONTAL_SERVO_ID = 2
    PWM_SPAN_US = 2000.0
    ANGLE_SPAN_DEG = 180.0

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

    def horizontal_angle_degrees(self):
        """Return camera pan relative to its calibration pulse, right-positive."""
        servo_id = self.HORIZONTAL_SERVO_ID
        center = float(self.calibration[servo_id])
        pulse = float(self.current_pos[servo_id])
        degrees_per_us = self.ANGLE_SPAN_DEG / self.PWM_SPAN_US
        return (center - pulse) * degrees_per_us

class PS2Controller:
    def __init__(self):
        """初始化PS2控制器"""
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        pygame.init()  # 初始化所有pygame模块
        pygame.joystick.init()
        
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
        self.control_mode = "analog"
        
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
        self.shoulder_turn_state = None
        self.calibration_combo_active = None
        self.calibration_combo_pending = None
        self.calibration_combo_since = None
        self.calibration_combo_cooldown_until = 0.0
        self.calibration_monitor = None
        self.calibration_cancel = threading.Event()
        self.heading_reset_monitor = None
        self.heading_reset_cancel = threading.Event()
        self.heading_reset_command_lock = threading.Lock()
        self.l3_pressed = False
        self.throttle_pressed = False
        self.brake_pressed = False
        self.mode_combo_active = False
        self.button_latches = {}
        self.last_hat = (0, 0)
        self.suppressed_combo_active = None
        self.desktop_combo_active = False
        self.last_camera_pan_angle = None
        self.last_camera_pan_publish = 0.0
        
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
            
            print(f"左摇杆模式: {'连续' if self.control_mode == 'analog' else '四方向'}")

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

    def _pressed_edge(self, name, pressed):
        previous = self.button_latches.get(name, False)
        self.button_latches[name] = bool(pressed)
        return bool(pressed) and not previous

    def emergency_brake(self, reason="R2"):
        """Public controller brake interface; no motion command may bypass it."""
        self.heading_reset_cancel.set()
        self.calibration_cancel.set()
        self.chassis_ctrl.emergency_stop()
        self.last_Lxy = [0, 0]
        self.l1_pressed = False
        self.r1_pressed = False
        self.shoulder_turn_state = None
        self.target_speed = {1: 0, 2: 0}
        self.current_speed = {1: 0, 2: 0}
        print(f"急停: {reason}")

    def _update_shoulder_turn(self, l1_current, r1_current, drive_enabled):
        """Apply one coherent chassis command for the complete L1/R1 state."""
        if l1_current and not self.l1_pressed:
            print("L1按下: 左转向")
            BZ.keydown_PSControler()
        elif not l1_current and self.l1_pressed:
            print("L1释放")

        if r1_current and not self.r1_pressed:
            print("R1按下: 右转向")
            BZ.keydown_PSControler()
        elif not r1_current and self.r1_pressed:
            print("R1释放")

        self.l1_pressed = bool(l1_current)
        self.r1_pressed = bool(r1_current)
        if not drive_enabled or self.l1_pressed == self.r1_pressed:
            # None hands control back to the left stick; zero represents the
            # deliberate conflict state where both shoulder keys are held.
            desired_state = 0 if self.l1_pressed else None
        else:
            desired_state = 1 if self.l1_pressed else -1

        if desired_state == self.shoulder_turn_state:
            return
        if desired_state in (None, 0):
            applied = self.chassis_ctrl.stop()
        else:
            applied = self.chassis_ctrl.turn(desired_state)
        # A four-wheel update consists of four independent I2C writes. Keep
        # the old state after a partial failure so the whole command is retried
        # on the next 50 Hz controller frame.
        if applied:
            self.shoulder_turn_state = desired_state

    def request_sensor_calibration(self, kind):
        """Request one sensor-specific calibration from the tCar service."""
        if kind not in ("inertial", "magnetometer"):
            raise ValueError(f"未知校准类型: {kind}")
        if self.calibration_monitor and self.calibration_monitor.is_alive():
            print("传感器校准已在进行")
            return
        self.chassis_ctrl.stop()
        self.calibration_cancel.clear()
        self.target_speed = {1: 0, 2: 0}
        self.current_speed = {1: 0, 2: 0}
        self.calibration_monitor = threading.Thread(
            target=self._monitor_sensor_calibration,
            args=(kind,),
            name=f"{kind}-calibration-monitor",
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

    def _read_gyro_heading(self, timeout=0.5):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            sock.sendto(b"get_data", SENSOR_SERVER_ADDRESS)
            packet, _ = sock.recvfrom(1024)
            if len(packet) != 68:
                raise RuntimeError(f"unexpected sensor packet: {len(packet)} bytes")
            heading = struct.unpack("!17f", packet)[15]
            if not math.isfinite(heading):
                raise RuntimeError("invalid gyro heading")
            return heading % 360.0
        finally:
            sock.close()

    def request_heading_reset(self):
        if self.calibration_monitor and self.calibration_monitor.is_alive():
            print("传感器校准期间不能执行朝向复位")
            BZ.init(0.08)
            return
        if self.heading_reset_monitor and self.heading_reset_monitor.is_alive():
            return
        if not self.chassis_ctrl.is_drive_enabled():
            print("L3朝向复位需要持续按住L2油门")
            BZ.init(0.08)
            return
        with self.heading_reset_command_lock:
            self.chassis_ctrl.stop()
        self.heading_reset_cancel.clear()
        self.heading_reset_monitor = threading.Thread(
            target=self._monitor_heading_reset,
            name="tcar-heading-reset",
            daemon=True,
        )
        self.heading_reset_monitor.start()

    def _cancel_heading_reset(self, reason="刹车"):
        monitor = self.heading_reset_monitor
        if monitor is None or not monitor.is_alive():
            return False
        self.heading_reset_cancel.set()
        with self.heading_reset_command_lock:
            self.chassis_ctrl.stop()
        print(f"朝向复位中断: {reason}")
        return True

    def _toggle_desktop_services(self):
        """Toggle the remote desktop routes without blocking the input loop."""
        try:
            reply = self._sensor_command(b"desktop_services_toggle", timeout=0.6)
            print(f"桌面通信服务: {reply or 'no reply'}")
            if reply.strip() == "paused":
                BZ.desktop_services_paused()
            elif reply.strip() == "active":
                BZ.desktop_services_resumed()
        except Exception as exc:
            print(f"桌面通信切换失败: {exc}")
            BZ.init(0.08)

    def _monitor_heading_reset(self):
        """Return to inertial zero with a deadband and pulsed final approach."""
        deadline = time.monotonic() + 12.0
        settled_since = None
        last_command = None
        final_pulses = 0
        try:
            while (RUNNING and not self.heading_reset_cancel.is_set()
                   and time.monotonic() < deadline):
                if not self.chassis_ctrl.is_drive_enabled():
                    self.heading_reset_cancel.set()
                    break
                heading = self._read_gyro_heading()
                if self.heading_reset_cancel.is_set() or not RUNNING:
                    break
                error = (0.0 - heading + 180.0) % 360.0 - 180.0
                abs_error = abs(error)
                if abs_error <= HEADING_RESET_TOLERANCE_DEG:
                    if last_command is not None:
                        with self.heading_reset_command_lock:
                            self.chassis_ctrl.stop()
                        last_command = None
                    if settled_since is None:
                        settled_since = time.monotonic()
                    elif time.monotonic() - settled_since >= 0.35:
                        print(f"朝向复位完成: {heading:.1f}°")
                        return
                else:
                    settled_since = None
                    if abs_error > 30.0:
                        yaw_rate = 0.38
                    elif abs_error > 12.0:
                        yaw_rate = 0.28
                    else:
                        yaw_rate = HEADING_RESET_MIN_YAW_RATE

                    # ChassisController maps direction=1 to the physical left
                    # turn. Keep this sign conversion in one place for the
                    # installed sensor orientation.
                    direction = -1 if error > 0.0 else 1
                    command = (direction, yaw_rate)
                    if (last_command is not None
                            and last_command[0] != direction):
                        with self.heading_reset_command_lock:
                            self.chassis_ctrl.stop()
                        last_command = None
                        time.sleep(HEADING_RESET_BRAKE_SECONDS)

                    if command != last_command:
                        with self.heading_reset_command_lock:
                            if self.heading_reset_cancel.is_set() or not RUNNING:
                                break
                            if not self.chassis_ctrl.turn(direction, yaw_rate):
                                self.heading_reset_cancel.set()
                                break
                        last_command = command

                    # Minimum usable PWM is too coarse for continuous motion
                    # near zero. Apply one short pulse, brake, then remeasure.
                    if abs_error <= 12.0:
                        time.sleep(HEADING_RESET_PULSE_SECONDS)
                        with self.heading_reset_command_lock:
                            self.chassis_ctrl.stop()
                        last_command = None
                        final_pulses += 1
                        if final_pulses >= HEADING_RESET_MAX_FINAL_PULSES:
                            print(
                                f"朝向复位达到机械微调极限: {heading:.1f}°"
                            )
                            return
                        time.sleep(HEADING_RESET_BRAKE_SECONDS)
                        continue
                time.sleep(0.04)
            if self.heading_reset_cancel.is_set() or not RUNNING:
                print("朝向复位已取消")
                return
            raise RuntimeError("heading reset timed out")
        except Exception as exc:
            print(f"朝向复位失败: {exc}")
            BZ.init(0.5)
        finally:
            with self.heading_reset_command_lock:
                self.chassis_ctrl.stop()

    def _publish_camera_pan(self, force=False):
        angle = self.servo_ctrl.horizontal_angle_degrees()
        now = time.monotonic()
        if not force:
            if now - self.last_camera_pan_publish < 0.05:
                return
            if (self.last_camera_pan_angle is not None
                    and abs(angle - self.last_camera_pan_angle) < 0.05):
                return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.sendto(f"camera_pan:{angle:.3f}".encode(), SENSOR_SERVER_ADDRESS)
            self.last_camera_pan_angle = angle
            self.last_camera_pan_publish = now
        finally:
            sock.close()

    def _monitor_sensor_calibration(self, kind):
        auto_turning = False
        turn_rate = None
        try:
            command = {
                "inertial": b"calibrate_inertial",
                "magnetometer": b"calibrate_magnetometer",
            }[kind]
            reply = self._sensor_command(command)
            print(f"传感器校准请求: {reply}")
            if reply.startswith("busy:"):
                print("传感器校准忙，本次请求未执行")
                BZ.init(0.08)
                return
            if not reply.startswith("started:"):
                raise RuntimeError(reply)
            BZ.calibration_started()
            last_phase = None
            while RUNNING and not self.calibration_cancel.is_set():
                if (kind == "magnetometer"
                        and not self.chassis_ctrl.is_drive_enabled()):
                    self.calibration_cancel.set()
                    print("磁力校准停止: L2油门已释放或R2刹车已按下")
                    break
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
                    if kind == "magnetometer" and phase == "magnetometer":
                        # tCar integrates the calibrated Z gyro and ends this
                        # phase after one real 360-degree rotation.
                        if (self.calibration_cancel.is_set()
                                or not self.chassis_ctrl.is_drive_enabled()):
                            break
                        turn_rate = 0.30
                        if not self.chassis_ctrl.turn(1, turn_rate):
                            self.calibration_cancel.set()
                            break
                        auto_turning = True
                    elif auto_turning:
                        self.chassis_ctrl.stop()
                        auto_turning = False
                    last_phase = phase
                if auto_turning and progress is not None:
                    if progress >= 330.0:
                        desired_rate = HEADING_RESET_MIN_YAW_RATE
                    else:
                        desired_rate = 0.30
                    if desired_rate != turn_rate:
                        if (self.calibration_cancel.is_set()
                                or not self.chassis_ctrl.is_drive_enabled()):
                            break
                        turn_rate = desired_rate
                        if not self.chassis_ctrl.turn(1, turn_rate):
                            self.calibration_cancel.set()
                            break
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
        self._publish_camera_pan()
    
    def process_left_joystick(self, x, y):
        """处理左摇杆输入 - 控制小车"""
        # 注意：摇杆坐标系统：
        # x: 左为负，右为正
        # y: 上为负，下为正
        
        if not self.chassis_ctrl.is_drive_enabled():
            self.chassis_ctrl.stop()
            return
        if self.control_mode == "cardinal":
            magnitude = min(1.0, math.hypot(x, y))
            if magnitude <= self.chassis_ctrl.deadzone:
                x, y = 0.0, 0.0
            elif abs(x) >= abs(y):
                x, y = math.copysign(magnitude, x), 0.0
            else:
                x, y = 0.0, math.copysign(magnitude, y)

        # 只有当L1和R1都没有按下时，才使用摇杆控制小车
        if not self.l1_pressed and not self.r1_pressed:
            self.chassis_ctrl.control_chassis(x, y)
    
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
            l2_pressed = self.get_safe_button(key_map["PSB_L2"])
            r2_pressed = self.get_safe_button(key_map["PSB_R2"])
            self.throttle_pressed = bool(l2_pressed)

            # R2 is evaluated before every other state. The brake is latched
            # in ChassisController, so concurrent worker threads cannot issue
            # a nonzero command after this point.
            if r2_pressed:
                if not self.brake_pressed:
                    self.brake_pressed = True
                    self.emergency_brake()
                return
            if self.brake_pressed:
                self.brake_pressed = False
                print("R2刹车释放")
            self.chassis_ctrl.set_drive_authorization(l2_pressed, brake=False)

            select_pressed = self.get_safe_button(key_map["PSB_SELECT"])
            start_pressed = self.get_safe_button(key_map["PSB_START"])
            a_pressed = self.get_safe_button(key_map["PSB_A"])
            b_pressed = self.get_safe_button(key_map["PSB_B"])
            x_pressed = self.get_safe_button(key_map["PSB_X"])
            y_pressed = self.get_safe_button(key_map["PSB_Y"])
            l3_current = self.get_safe_button(key_map["PSB_L3"])
            now = time.monotonic()

            # SELECT+Y toggles desktop camera/telemetry routes. Latch the
            # chord so a held button produces one request only.
            if select_pressed and y_pressed:
                if not self.desktop_combo_active:
                    self.desktop_combo_active = True
                    self._toggle_desktop_services()
                return
            if self.desktop_combo_active:
                if not select_pressed and not y_pressed:
                    self.desktop_combo_active = False
                return

            if (self.heading_reset_monitor is not None
                    and self.heading_reset_monitor.is_alive()):
                if not l2_pressed:
                    self._cancel_heading_reset("L2油门释放")
                if not l3_current:
                    self.l3_pressed = False
                return

            if (self.calibration_monitor is not None
                    and self.calibration_monitor.is_alive()):
                return

            if select_pressed and start_pressed:
                if not self.mode_combo_active:
                    self.mode_combo_active = True
                    self.control_mode = (
                        "cardinal"
                        if self.control_mode == "analog"
                        else "analog"
                    )
                    self.chassis_ctrl.stop()
                    mode_text = "四方向" if self.control_mode == "cardinal" else "连续"
                    print(f"左摇杆模式切换: {mode_text}")
                    BZ.keydown_combination_PSControler()
                return
            if self.mode_combo_active:
                if not select_pressed and not start_pressed:
                    self.mode_combo_active = False
                return

            # SELECT+X remains intentionally unassigned. Latch it until both
            # keys are released so it cannot leak into a normal X action.
            if self.suppressed_combo_active is not None:
                face_pressed = x_pressed
                if not select_pressed and not face_pressed:
                    self.suppressed_combo_active = None
                return
            if select_pressed and x_pressed:
                self.suppressed_combo_active = "x"
                return

            # SELECT+A recalibrates inertial origin; SELECT+B performs the
            # one-turn magnetic-axis calibration. Both retain the existing
            # debounce and calibration sounds.
            if self.calibration_combo_active is not None:
                active_pressed = (
                    a_pressed
                    if self.calibration_combo_active == "inertial"
                    else b_pressed
                )
                if not select_pressed and not active_pressed:
                    self.calibration_combo_active = None
                    self.calibration_combo_pending = None
                    self.calibration_combo_since = None
                    self.calibration_combo_cooldown_until = now + 0.35
                return

            combo_kind = None
            if select_pressed and a_pressed != b_pressed:
                combo_kind = "inertial" if a_pressed else "magnetometer"
            if combo_kind is not None:
                if now < self.calibration_combo_cooldown_until:
                    return
                if self.calibration_combo_pending != combo_kind:
                    self.calibration_combo_pending = combo_kind
                    self.calibration_combo_since = now
                    return
                if now - self.calibration_combo_since < 0.12:
                    return
                self.calibration_combo_active = combo_kind
                self.calibration_combo_pending = None
                self.calibration_combo_since = None
                if combo_kind == "magnetometer" and not l2_pressed:
                    print("SELECT + B磁力校准需要持续按住L2油门")
                    BZ.init(0.08)
                    return
                if combo_kind == "inertial":
                    print("SELECT + A: 重新校准陀螺仪、姿态和初始朝向")
                else:
                    print("SELECT + B: 原地旋转一圈校准磁力轴")
                self.request_sensor_calibration(combo_kind)
                return
            self.calibration_combo_pending = None
            self.calibration_combo_since = None

            if select_pressed and (a_pressed or b_pressed):
                return

            if l3_current and not self.l3_pressed:
                self.l3_pressed = True
                print("L3按下: 朝向复位")
                BZ.keydown_PSControler()
                self.request_heading_reset()
                if (self.heading_reset_monitor is not None
                        and self.heading_reset_monitor.is_alive()):
                    return
            elif not l3_current and self.l3_pressed:
                self.l3_pressed = False

            # Resolve both shoulder keys together so rapid direction changes
            # cannot leave a stale stop or partial wheel command behind.
            self._update_shoulder_turn(
                self.get_safe_button(key_map["PSB_L1"]),
                self.get_safe_button(key_map["PSB_R1"]),
                self.chassis_ctrl.is_drive_enabled(),
            )

            r3_pressed = self.get_safe_button(key_map["PSB_R3"])
            if self._pressed_edge("r3", r3_pressed):
                print("R3按下: 重置舵机")
                BZ.keydown_PSControler()
                self.servo_ctrl.reset_servos()
                self.target_speed = {1: 0, 2: 0}
                self.current_speed = {1: 0, 2: 0}

            for name, pressed in (
                ("y", y_pressed), ("b", b_pressed),
                ("a", a_pressed), ("x", x_pressed),
            ):
                if self._pressed_edge(name, pressed):
                    print(f"{name.upper()}按下")
                    BZ.keydown_PSControler()

            hat = self.js.get_hat(0) if self.js.get_numhats() else (0, 0)
            previous_hat = self.last_hat
            self.last_hat = hat
            if hat != (0, 0) and self.chassis_ctrl.is_drive_enabled():
                # D-pad is the discrete four-direction drive input. It is
                # intentionally independent from the left-stick mode toggle.
                hat_x, hat_y = hat
                if hat_x:
                    self.chassis_ctrl.control_chassis(float(hat_x), 0.0)
                elif hat_y:
                    self.chassis_ctrl.control_chassis(0.0, float(-hat_y))
            elif hat == (0, 0) and previous_hat != (0, 0):
                self.chassis_ctrl.stop()
            
        except Exception as e:
            print(f"按钮处理错误: {e}")
    
    def run(self):
        """主循环"""
        print("=" * 50)
        print("PS2控制器启动中...")
        print("=" * 50)
        
        # 测试舵机初始状态
        self.servo_ctrl.reset_servos()
        self._publish_camera_pan(force=True)
        
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
                    if not self._cancel_heading_reset("手柄断开"):
                        self.chassis_ctrl.stop()
                    self.l1_pressed = False
                    self.r1_pressed = False
                    self.shoulder_turn_state = None
                    if self.js:
                        self.js.quit()
                    pygame.joystick.quit()
                    print("手柄已断开")
            
            if self.connected:
                # Drain SDL's queue, then poll the latest complete stick state.
                # Axis events themselves are intentionally ignored because an
                # event-only controller can miss the final centered position.
                pygame.event.get()
                
                # 处理按钮
                self.process_buttons()

                calibrating = (
                    self.calibration_monitor is not None
                    and self.calibration_monitor.is_alive()
                )
                resetting_heading = (
                    self.heading_reset_monitor is not None
                    and self.heading_reset_monitor.is_alive()
                )
                current_Lx = self.js.get_axis(self.axis_mapping["left_x"])
                current_Ly = self.js.get_axis(self.axis_mapping["left_y"])
                current_Rx = self.js.get_axis(self.axis_mapping["right_x"])
                current_Ry = self.js.get_axis(self.axis_mapping["right_y"])
                if (not calibrating and not resetting_heading
                        and self.last_hat == (0, 0)):
                    self.process_left_joystick(current_Lx, current_Ly)
                if not self.brake_pressed:
                    self.process_right_joystick(current_Rx, current_Ry)
                
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
