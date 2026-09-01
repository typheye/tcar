# -*- coding:utf-8 -*-
# 网络状态监测

import threading
import time
import urllib.request
import json
from server.rpc.core_host import get_core_host
from server.rpc.car_rpc import rpc_client
from server.gui.public.utils import *
from media.config import *


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
                data = response.read().decode("utf-8")
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
        status, voltage, battery = (
            self.core_battery_info_status,
            self.core_battery_info_voltage,
            self.core_battery_info_battery,
        )
        if status and voltage > 0:
            # 根据电量选择颜色
            if battery > 30:
                color = COLOR_BLUE
            elif battery > 15:
                color = COLOR_YELLOW
            else:
                color = COLOR_RED
            remaining_wh = (
                BATTERY_NOMINAL_VOLTAGE
                * BATTERY_CAPACITY_AH
                * max(0.0, min(100.0, battery)) / 100.0
            )
            runtime_hours = (
                remaining_wh / CAR_REFERENCE_POWER_W
                if CAR_REFERENCE_POWER_W > 0 else 0.0
            )
            return (f"{runtime_hours:.1f} h", int(battery), color)
        else:
            return ("0.0 h", 0, COLOR_MID_BLUE)

    def _get_route_temperature(self):
        """获取路由器温度"""
        if self.json_data and self.json_data.get("status") != -1:
            try:
                temp = float(self.json_data.get("esptemp", "0"))
                return f"{temp:.0f}°", COLOR_GREEN if 0 <= temp <= 65 else COLOR_YELLOW
            except:
                return "---", COLOR_WHITE
        return "ERR", COLOR_YELLOW

    def _get_camera_status(self):
        if self.core_status:
            result = rpc_client.heartbeat()

            try:
                # 检查是否成功调用
                if result.get("success"):
                    # 检查返回数据格式
                    result_data = result.get("result")
                    if result_data and isinstance(result_data, (list, tuple)):
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
                result = rpc_client.get_battery()
                data = result.get("result") if result.get("success") else None
                if isinstance(data, (list, tuple)) and len(data) >= 2 and data[0]:
                    voltage = float(data[1]) / 1000.0
                    battery = max(0.0, min(100.0, (voltage - 6.4) / 2.0 * 100.0))
                    status = voltage > 5.0

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

        (
            self.core_battery_info_status,
            self.core_battery_info_voltage,
            self.core_battery_info_battery,
        ) = (status, voltage, battery)

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
