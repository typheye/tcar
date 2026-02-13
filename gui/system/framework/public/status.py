# -*- coding:utf-8 -*-
# 网络状态监测

import threading
import time
import urllib.request
import json
from system.framework.public.rpc import rpc_client
from system.framework.public.utils import *
from system.config import *

class NetworkStatus:
    def __init__(self):
        self.json_data = None
        self.last_update = 0
        self.error_count = 0
        self.update_thread = None
        self.running = False
        self.core_status = False
        self.camera_status = False
        self.have_funtion8 = False
        self.core_battery_info_status = False
        self.core_battery_info_voltage = -1
        self.core_battery_info_battery = -1
        
    def start_monitoring(self):
        """开始监控网络状态"""
        self.running = True
        self.update_thread = threading.Thread(target=self._update_loop)
        self.update_thread.daemon = True
        self.update_thread.start()
        
    def stop_monitoring(self):
        """停止监控"""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=5)
            
    def _update_loop(self):
        """更新循环"""
        while self.running:
            try:
                self.core_status = get_core_status()
                self._fetch_json_data()
                self._get_core_battery()
                self._get_camera_status()
                time.sleep(3)  # 每3秒更新一次
            except Exception as e:
                log(4, "网络状态更新错误:", str(e))
                time.sleep(5)
                
    def _fetch_json_data(self):
        """获取JSON数据"""
        try:
            with urllib.request.urlopen(JSON_DATA_URL, timeout=5) as response:
                data = response.read().decode('utf-8')
                self.json_data = json.loads(data)
                self.error_count = 0
                self.last_update = time.time()
        except Exception as e:
            self.json_data = None
            self.error_count += 1
            log(4, "获取网络数据失败:", str(e))
            
    def get_route_status(self):
        """获取路由器状态"""
        if not self.json_data:
            return "错误", COLOR_YELLOW, "ERR", COLOR_YELLOW
            
        status = self.json_data.get("status", -1)
        if status == 1:
            route_value, route_value_color = self._get_route_temperature()
            return "正常", COLOR_GREEN, route_value, route_value_color
        elif status == 0:
            back = self._get_route_temperature()
            return "正常", COLOR_GREEN, back[0], back[1] 
        else:
            return "等待", COLOR_YELLOW, "---", COLOR_WHITE
        
    def get_ping_status(self, timeout=0.005):
        """测试主机是否在线（防止卡死）"""
        return self.core_status
    
    
    def get_camera_status(self, timeout=0.005):
        """测试相机是否在线（防止卡死）"""
        return self.camera_status
    
    
    def get_core_battery(self):
        status, voltage, battery = self.core_battery_info_status, self.core_battery_info_voltage, self.core_battery_info_battery
        if status:
            # if battery > 20: COLOR = COLOR_BLUE
            # else: COLOR = COLOR_YELLOW
            # return (f"{voltage:.1f} V", int(battery), COLOR)
            return (f"{voltage:.1f} V", 100, COLOR_BLUE)
        else:
            return (f"0.0 V", 100, COLOR_MID_BLUE)
        
    
    def _get_route_temperature(self):
        """获取路由器温度"""
        if self.json_data and self.json_data.get("status") != -1:
            try:
                temp = float(self.json_data.get("esptemp", "0"))
                return f"{temp:.0f}°", COLOR_GREEN if 0 <= temp <= 65 else COLOR_YELLOW
            except:
                return "---", COLOR_WHITE
        return "ERR", COLOR_YELLOW
    
    def _get_camera_status(self ):
        if self.core_status:
            if not self.have_funtion8:
                if self.core_status:
                    self.have_funtion8 = True
                    rpc_client.load_function(8)
            result = rpc_client.heartbeat()

            try:
                # 检查是否成功调用
                if result.get("success"):
                    # 检查返回数据格式
                    result_data = result.get("result")
                    if result_data and isinstance(result_data, list):
                        # 第一个元素是True表示心跳正常
                        self.camera_status = bool(result_data[0])
                    else:
                        self.camera_status = False
                else:
                    self.camera_status = False
            except (AttributeError, KeyError, TypeError, IndexError):
                # 如果result不是字典或格式不对
                self.camera_status = False
        else:
            self.camera_status = False
            self.have_funtion8 = False

    def _get_core_battery(self):
        """获取主机电池信息"""
        status = False
        voltage = -1
        battery = -1
        
        # 检查主机在线状态
        if self.core_status:
            try:
                # 使用subprocess执行ssh命令并获取输出
                cmd = 'ssh -q -t pi@192.168.166.100 "sudo python3 /home/pi/TurboPi/Utils/battery.py"'
                
                # 执行命令并捕获输出
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=2  # 设置2秒超时
                )
                
                # 解析JSON输出
                if result.returncode == 0 and result.stdout:
                    # 获取第一行JSON数据
                    info = result.stdout.strip()
                    # 只取第一行，避免可能的额外输出
                    lines = info.split("\n")
                    for line in lines:
                        if line.strip().startswith("{"):
                            data = json.loads(line.strip())
                            break
                    else:
                        # 如果没有找到JSON数据
                        raise ValueError("未找到有效的JSON数据")
                    
                    # 新格式使用 "success" 字段
                    if data.get("success", False):
                        status = True
                        voltage = data.get("voltage", -1)
                        battery = data.get("battery", -1)
                        
                        # 可选：记录状态信息
                        battery_status = data.get("status", "unknown")
                        # 可以在这里添加状态处理逻辑
                        # 例如：if battery_status == "critical": 发送警报
                    else:
                        # 测量失败，但有错误信息
                        status = False
                        voltage = -1
                        battery = -1
                        # 可以记录错误信息用于调试
                        error_msg = data.get("error", "未知错误")
                        # 可选：记录到日志
                        # print(f"电池测量失败: {error_msg}", file=sys.stderr)
                else:
                    # 命令执行失败
                    status = False
                    voltage = -1
                    battery = -1
                    # 可以记录stderr输出用于调试
                    if result.stderr:
                        # print(f"SSH命令错误: {result.stderr}", file=sys.stderr)
                        pass
                        
            except subprocess.TimeoutExpired:
                # 超时
                status = False
                voltage = -1
                battery = -1
                # print("获取电池信息超时", file=sys.stderr)
            except json.JSONDecodeError as e:
                # JSON解析失败
                status = False
                voltage = -1
                battery = -1
                # print(f"JSON解析失败: {e}", file=sys.stderr)
            except Exception as e:
                # 其他异常
                status = False
                voltage = -1
                battery = -1
                # print(f"获取电池信息异常: {e}", file=sys.stderr)
        else:
            # 主机离线
            status = False
            voltage = -1
            battery = -1
        
        self.core_battery_info_status, self.core_battery_info_voltage, self.core_battery_info_battery = status, voltage, battery
        
    def get_central_status(self):
        """获取中枢状态"""
        if not self.json_data:
            return "错误", COLOR_YELLOW, "ERR", COLOR_YELLOW
            
        status = self.json_data.get("status", -1)
        if status == 1:
            return "正常", COLOR_GREEN, "RUN", COLOR_GREEN
        elif status == 0:
            return "异常", COLOR_YELLOW, "ERR", COLOR_YELLOW
        else:
            return "等待", COLOR_YELLOW, "---", COLOR_WHITE