# -*- coding:utf-8 -*-
# 工具函数

import socket
import time
import RPi.GPIO as GPIO
import subprocess
import re
import os
import platform
from media.config import *
from server.rpc.core_host import get_core_host

_online_cache = {
    "value": False,
    "checked_at": 0.0,
    "fail_count": 0,
}

def setup_gpio():
    """初始化GPIO引脚"""
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(KEY_up_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(KEY_down_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(KEY_left_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(KEY_right_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(KEY_press_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(ok_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(main_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(cancel_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def wait_release(pin, count=999999999999):
    """等待释放按键，返回等待时间"""
    _tcount = 0
    while GPIO.input(pin) == 0 and count > 0:
        time.sleep(0.001)
        count -= 1
        _tcount += 1
    return _tcount

def wait_press(pin):
    """等待按键按下并释放，返回是否按下"""
    flag = False
    while GPIO.input(pin) == 0:
        if not flag:
            flag = True
        time.sleep(0.001)
    return flag

def press_key(pin):
    """判断按键是否按下"""
    return GPIO.input(pin) == 0

def get_system_info():
    """获取系统信息"""
    try:
        # IP地址
        
        cmd = "ip -4 addr show wlan0 2>/dev/null | grep -oP '(?<=inet\\s)\\d+(\\.\\d+){3}' || echo ''"
        ip = subprocess.check_output(cmd, shell=True).decode("utf-8").strip()

        # 如果需要确保不为空
        if len(ip) == 0 or not is_valid_ip(ip):
            ip = "未知"
        
        # CPU使用率
        cmd = "top -bn1 | grep '%Cpu(s)' | awk '{print $2 + $4}'"
        cpu_usage = float(subprocess.check_output(cmd, shell=True).decode("utf-8").strip())
        cpu = "核心: %.0f%%" % cpu_usage
        
        # 内存使用率
        cmd = "free -m | awk 'NR==2{printf \"内存: %.1f%% (%s/%sM)\", $3*100/$2,$3,$2 }'"
        mem = subprocess.check_output(cmd, shell=True).decode("utf-8")
        
        # 磁盘使用率
        cmd = "df -h | awk '$NF==\"/\"{printf \"磁盘: %s (%d/%dG) \", $5,$3,$2}'"
        disk = subprocess.check_output(cmd, shell=True).decode("utf-8")
        
        # 检查WLAN
        wifi_check = os.popen("iwconfig wlan0 2>/dev/null | grep 'ESSID:\"'").read().strip()
        wlan_connected = bool(wifi_check)

        # 检查以太网
        eth_check = os.popen("ip link show eth0 2>/dev/null | grep 'state UP'").read().strip()
        eth_connected = bool(eth_check)

        # 判断状态
        if wlan_connected and eth_connected:
            wifi = "网络: WLAN 和 以太网"
        elif wlan_connected:
            wifi = "网络: WLAN"
        elif eth_connected:
            wifi = "网络: 以太网"
        else:
            wifi = "网络: 未连接"
        
        # 温度
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            temp = float(f.read()) / 1000
            temp_str = "%0.1f" % temp
        
        return ip, cpu, mem, disk, wifi, temp_str
    except Exception as e:
        return "未知", "核心: 0%", "内存: 0%", "磁盘: 0%", "网络: 未连接", "0.0"
    
def get_core_info():
    """获取中枢信息（通过 tCarCore RPC，不再依赖旧 TurboPi/SSH）。"""
    if get_core_status():
        try:
            from server.rpc.car_rpc import rpc_client
            result = rpc_client.call("GetSystemInfo")
            envelope = result.get("result") if result.get("success") else None
            data = envelope[1] if isinstance(envelope, (list, tuple)) and len(envelope) >= 2 and envelope[0] else None
            if not isinstance(data, dict): return "未知", "0.0"
            ip = str(data.get("ip", "未知"))
            if not is_valid_ip(ip): ip = get_core_host()
            return ip, "%0.1f" % float(data.get("temperature_c", 0.0))
            
        except Exception as e:
            return "未知", "0.0"
    else:
        return "未知", "0.0"
    
def _tcp_probe(host, port, timeout):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

def _has_usable_ipv4():
    """本机有可用 IPv4 就认为局域网基本可用，不强依赖公网 DNS。"""
    try:
        output = subprocess.check_output(
            ["ip", "-o", "-4", "addr", "show", "scope", "global"],
            stderr=subprocess.DEVNULL,
            timeout=0.5,
        ).decode("utf-8", errors="ignore")
        for match in re.finditer(r"\binet\s+(\d+(?:\.\d+){3})/", output):
            if is_valid_ip(match.group(1)):
                return True
    except Exception:
        pass
    return False

def _has_default_route():
    try:
        output = subprocess.check_output(
            ["ip", "route", "show", "default"],
            stderr=subprocess.DEVNULL,
            timeout=0.5,
        ).decode("utf-8", errors="ignore").strip()
        return bool(output)
    except Exception:
        return False

def get_online(timeout=1):
    """检测网络状态：先看本地链路，再多目标 TCP 探测，并用短缓存防抖。"""
    now = time.monotonic()
    if now - _online_cache["checked_at"] < 2.0:
        return _online_cache["value"]

    try:
        timeout = max(0.15, min(float(timeout), 2.0))
    except Exception:
        timeout = 1.0

    local_online = _has_usable_ipv4()
    routed = _has_default_route()
    probe_timeout = max(0.15, timeout / 2.0)
    internet_online = any(
        _tcp_probe(host, port, probe_timeout)
        for host, port in (
            ("223.5.5.5", 53),
            ("1.1.1.1", 53),
            ("8.8.8.8", 53),
        )
    )

    online = internet_online or (local_online and routed)
    if online:
        _online_cache["fail_count"] = 0
        _online_cache["value"] = True
    else:
        _online_cache["fail_count"] += 1
        if _online_cache["fail_count"] >= 2:
            _online_cache["value"] = False
    _online_cache["checked_at"] = now
    return _online_cache["value"]

def log(level, *info):
    """日志记录"""
    _time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    symbols = {1: "+", 2: "-", 3: "*", 4: "!"}
    s = symbols.get(level, " ")
    print("[%s] %s - %s" % (s, _time, ", ".join([str(x) for x in info])))

def get_core_status(timeout=0.05):
    """测试主机是否在线（防止卡死）"""
    try:
        host = get_core_host(timeout=max(0.2, timeout))
    except Exception:
        return False
    
    try:
        # Linux/Mac: -c 次数, -W 超时(秒)
        cmd = ['ping', '-c', '1', '-W', str(timeout), host]
            
        # 使用subprocess.run，设置超时
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,  # 丢弃输出
            stderr=subprocess.DEVNULL,   # 丢弃错误
            timeout=timeout + 1,         # 总超时时间
            encoding='utf-8',
            errors='ignore'
        )
            
        # 返回码为0表示成功
        return result.returncode == 0
            
    except subprocess.TimeoutExpired:
        # 命令执行超时
        return False
    except Exception:
        return False
    
def is_valid_ip(ip_str, octet = False):
    """判断IP地址字符串是否合法"""
    if not ip_str or ip_str == "未知":
        return False
    
    # 检查是否是常见的无效IP
    invalid_ips = ["0.0.0.0", "127.0.0.1", "255.255.255.255", "169.254.", "::1"]
    for invalid_ip in invalid_ips:
        if ip_str.startswith(invalid_ip):
            return False
    
    # 检查IPv4格式
    if '.' in ip_str:
        parts = ip_str.split('.')
        if len(parts) != 4:
            return False
        
        for part in parts:
            if not part.isdigit():
                return False
            num = int(part)
            if num < 0 or num > 255:
                return False
        
        # 检查是否是私有地址（可选，根据需求决定是否排除）
        if octet:
            first_octet = int(parts[0])
            if first_octet == 10:  # 10.0.0.0/8
                return False
            if first_octet == 172 and 16 <= int(parts[1]) <= 31:  # 172.16.0.0/12
                return False
            if first_octet == 192 and parts[1] == '168':  # 192.168.0.0/16
                return False
    
    # 检查IPv6格式（简化检查）
    elif ':' in ip_str:
        # 基本格式检查
        if ip_str.count('::') > 1:
            return False
        # 更多IPv6检查可以在这里添加
    
    else:
        return False
    
    return True
