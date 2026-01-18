# -*- coding:utf-8 -*-
# WiFi管理

import os
import re
import time
import threading
from utils import log

class WiFiManager:
    def __init__(self):
        self.scan_flag = False
        self.wifi_list = []
        self.current_wifi = None
        self.scan_thread = None

    def get_interfaces(self):
        """获取无线网卡接口"""
        try:
            iwconfig = os.popen("iwconfig 2>/dev/null | grep IEEE").read()
            interfaces = filter(lambda x: bool(x), 
                              [line.split(" ")[0] for line in iwconfig.split("\n")])
            
            result = {}
            for iface in interfaces:
                # 检查是否为监听模式
                r = re.search("^([a-z]*?\d+)mon$", iface)
                if r:
                    iface = r.group(1)
                
                status = self.get_interface_status(iface)
                # wlan0用于互联网接入，其他用于监控
                if iface != "wlan0" and iface != "wlan0mon":
                    result[iface] = status
            return result
        except Exception as e:
            log(4, "获取网络接口失败:", str(e))
            return {}

    def get_interface_status(self, iface):
        """获取接口状态"""
        if os.popen(f"iwconfig {iface}mon 2>/dev/null | grep 'IEEE 802.11'").read().strip():
            return True  # 监听模式
        elif os.popen(f"iwconfig {iface} 2>/dev/null | grep 'IEEE 802.11'").read().strip():
            return False  # 普通模式
        else:
            return None  # 不可用

    def get_visible_networks(self):
        """扫描可见WiFi网络"""
        try:
            from urllib.parse import unquote
        except ImportError:
            from urllib import unquote
            
        try:
            wifi_list = os.popen("sudo iw dev wlan0 scan | grep 'SSID: '").read()
            networks = []
            
            for wifi in wifi_list.split("\n"):
                wifi = wifi.strip()
                if wifi:
                    try:
                        # 解码SSID
                        ssid_encoded = wifi.split(": ", 1)[1]
                        ssid = unquote(ssid_encoded.replace("\\x", "%").encode("utf-8").decode("unicode-escape"))
                        networks.append(ssid)
                    except Exception as e:
                        log(4, "SSID解码失败:", str(e))
            return networks
        except Exception as e:
            log(4, "WiFi扫描失败:", str(e))
            return []

    def start_monitor_mode(self, iface):
        """启动监听模式"""
        os.system(f"sudo airmon-ng start {iface} {iface}mon &")

    def stop_monitor_mode(self, iface):
        """停止监听模式"""
        os.system(f"sudo airmon-ng stop {iface}mon &")

    def start_airodump(self):
        """启动airodump扫描"""
        os.system("sudo /home/pi/start.sh &")
        self.scan_flag = True
        self.scan_thread = threading.Thread(target=self._parse_wifi_results)
        self.scan_thread.daemon = True
        self.scan_thread.start()

    def stop_airodump(self):
        """停止airodump扫描"""
        os.system("sudo killall -s 9 airodump-ng 2>/dev/null &")
        self.scan_flag = False

    def _parse_wifi_results(self, filename="/home/pi/result-01.csv"):
        """解析airodump结果"""
        while self.scan_flag:
            try:
                if not os.path.exists(filename):
                    time.sleep(1)
                    continue
                    
                wifi_networks = []
                connected_clients = {}
                
                with open(filename, 'r') as f:
                    lines = f.readlines()
                
                in_stations_section = False
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                        
                    parts = line.split(",")
                    if parts[0] == 'BSSID':
                        in_stations_section = False
                        continue
                    elif parts[0] == 'Station MAC':
                        in_stations_section = True
                        continue
                        
                    if not in_stations_section and len(parts) >= 14:
                        # 解析AP信息
                        try:
                            ap_info = {
                                'bssid': parts[0].strip(),
                                'channel': parts[3].strip(),
                                'privacy': parts[5].strip(),
                                'signal': parts[8].strip(),
                                'ssid': parts[13].strip()
                            }
                            wifi_networks.append(ap_info)
                        except Exception as e:
                            log(4, "AP信息解析错误:", str(e))
                    elif in_stations_section and len(parts) >= 6:
                        # 解析客户端信息
                        try:
                            client_info = {
                                'mac': parts[0].strip(),
                                'bssid': parts[5].strip()
                            }
                            if client_info['bssid'] in connected_clients:
                                connected_clients[client_info['bssid']].append(client_info)
                            else:
                                connected_clients[client_info['bssid']] = [client_info]
                        except Exception as e:
                            log(4, "客户端信息解析错误:", str(e))
                
                # 合并AP和客户端信息
                for ap in wifi_networks:
                    ap['clients'] = connected_clients.get(ap['bssid'], [])
                
                self.wifi_list = wifi_networks
                
                # 更新当前选择的WiFi信息
                if self.current_wifi:
                    matching = [w for w in self.wifi_list if w['bssid'] == self.current_wifi['bssid']]
                    if matching:
                        self.current_wifi = matching[0]
                        
                time.sleep(1)
            except Exception as e:
                log(4, "WiFi结果解析异常:", str(e))
                time.sleep(1)

    def connect_to_network(self, ssid, password):
        """连接到WiFi网络"""
        cmd = f"/home/pi/connect_pi.sh wlan0 {ssid} {password}"
        log(1, "连接WiFi:", cmd)
        return os.system(cmd)