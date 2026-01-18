# turbo_pi_control.py
import requests
import json
import time
import threading
from typing import Optional, List, Dict, Any

class TurboPiController:
    """树莓派小车控制器"""
    
    def __init__(self, device_ip="192.168.166.100"):
        """
        初始化小车控制器
        :param device_ip: 小车IP地址
        """
        self.device_ip = device_ip
        self.rpc_url = f"http://{device_ip}:9030/"
        self.stop_flag = False
        self.heartbeat_thread = None
        self.heartbeat_count = 0
        
    def _send_rpc(self, method: str, rpc_type: int = 1, 
                  int_array: Optional[List[int]] = None,
                  str_array: Optional[List[str]] = None,
                  float_array: Optional[List[float]] = None) -> Dict[str, Any]:
        """
        发送RPC指令（内部方法）
        """
        url = self.rpc_url + method
        
        payload = {
            "type": rpc_type,
            "i": int_array or [],
            "strings": str_array or [],
            "floats": float_array or []
        }
        
        try:
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=2
            )
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"RPC调用失败: {e}")
            return {"error": str(e), "success": False}
    
    # ========== 基本控制指令 ==========
    
    def initialize(self):
        """初始化小车功能（启动时调用）"""
        print("🔄 初始化小车...")
        return self._send_rpc("LoadFunc", 1, int_array=[1])
    
    def cleanup(self):
        """清理资源（退出时调用）"""
        print("🧹 清理小车资源...")
        self.stop_heartbeat()
        self.stop()
        return self._send_rpc("UnloadFunc", 1, int_array=[])
    
    def heartbeat(self):
        """发送心跳包"""
        self.heartbeat_count += 1
        if self.heartbeat_count > 6:
            result = self._send_rpc("Heartbeat", 1, int_array=[])
            self.heartbeat_count = 0
            return result
        return None
    
    # ========== 运动控制指令 ==========
    
    def move_forward(self):
        """前进"""
        print("⬆️ 前进")
        return self._send_rpc("SetMovementAngle", 1, int_array=[90])
    
    def move_backward(self):
        """后退"""
        print("⬇️ 后退")
        return self._send_rpc("SetMovementAngle", 1, int_array=[270])
    
    def move_left(self):
        """左移"""
        print("⬅️ 左移")
        return self._send_rpc("SetMovementAngle", 1, int_array=[180])
    
    def move_right(self):
        """右移"""
        print("➡️ 右移")
        return self._send_rpc("SetMovementAngle", 1, int_array=[0])
    
    def stop(self):
        """停止移动"""
        print("⏹️ 停止")
        return self._send_rpc("SetMovementAngle", 1, int_array=[-1])
    
    def rotate_left(self):
        """原地左转"""
        print("↪️ 原地左转")
        return self._send_rpc("SetBrushMotor", 1, 
                             int_array=[1, -100, 2, 100, 3, -100, 4, 100])
    
    def rotate_right(self):
        """原地右转"""
        print("↩️ 原地右转")
        return self._send_rpc("SetBrushMotor", 1,
                             int_array=[1, 100, 2, -100, 3, 100, 4, -100])
    
    def set_movement_angle(self, angle: int):
        """
        设置移动角度
        :param angle: 0-右, 90-前, 180-左, 270-后, -1-停止
        """
        print(f"🎯 设置移动角度: {angle}°")
        return self._send_rpc("SetMovementAngle", 1, int_array=[angle])
    
    def set_brush_motor(self, motor1: int, motor2: int, motor3: int, motor4: int):
        """
        设置四个刷子电机的速度
        :param motor1-motor4: 电机速度 (-100到100)
        """
        print(f"⚙️ 设置电机速度: {motor1}, {motor2}, {motor3}, {motor4}")
        return self._send_rpc("SetBrushMotor", 1,
                             int_array=[1, motor1, 2, motor2, 3, motor3, 4, motor4])
    
    # ========== 高级控制方法 ==========
    
    def move_direction(self, direction: str, duration: float = 0.5):
        """
        按方向移动一段时间
        :param direction: "forward", "backward", "left", "right"
        :param duration: 持续时间（秒）
        """
        direction_map = {
            "forward": 90,
            "backward": 270,
            "left": 180,
            "right": 0
        }
        
        if direction in direction_map:
            result = self.set_movement_angle(direction_map[direction])
            if duration > 0:
                time.sleep(duration)
                self.stop()
            return result
        else:
            print(f"❌ 未知方向: {direction}")
            return None
    
    def rotate(self, direction: str, duration: float = 0.5):
        """
        旋转一段时间
        :param direction: "left", "right"
        :param duration: 持续时间（秒）
        """
        if direction == "left":
            result = self.rotate_left()
        elif direction == "right":
            result = self.rotate_right()
        else:
            print(f"❌ 未知旋转方向: {direction}")
            return None
        
        if duration > 0:
            time.sleep(duration)
            self.stop()
        return result
    
    # ========== 心跳包维护 ==========
    
    def _heartbeat_loop(self):
        """心跳包循环（每50ms执行一次，每300ms发送心跳）"""
        timer_cnt = 0
        
        while not self.stop_flag:
            # 计数器逻辑
            timer_cnt += 1
            if timer_cnt >= 6:  # 6 * 50ms = 300ms
                self.heartbeat()
                timer_cnt = 0
            
            # 等待50ms
            time.sleep(0.05)
    
    def start_heartbeat(self):
        """启动心跳包线程"""
        self.stop_flag = False
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop)
        self.heartbeat_thread.daemon = True
        self.heartbeat_thread.start()
        print("💓 心跳包线程已启动")
    
    def stop_heartbeat(self):
        """停止心跳包线程"""
        self.stop_flag = True
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=1)
        print("💔 心跳包线程已停止")
    
    # ========== 其他功能 ==========
    
    def get_video_stream_url(self):
        """获取视频流URL"""
        return f"http://{self.device_ip}:8080/?action=stream"
    
    def test_connection(self):
        """测试连接"""
        try:
            result = self.heartbeat()
            if result and not result.get("error"):
                print("✅ 连接正常")
                return True
            else:
                print("❌ 连接失败")
                return False
        except Exception as e:
            print(f"❌ 连接测试异常: {e}")
            return False