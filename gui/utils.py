# -*- coding:utf-8 -*-
# 工具函数

import time
import RPi.GPIO as GPIO
import subprocess
import re
import subprocess
import platform
from config import *

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
    """获取中枢信息（通过SSH连接到远程树莓派）"""
    if get_core_status():
        try:
            # SSH连接信息
            ssh_prefix = "ssh -o ConnectTimeout=5 -o BatchMode=yes pi@192.168.166.100"
            
            def ssh_exec(cmd):
                """执行SSH命令并返回结果"""
                full_cmd = f'{ssh_prefix} "{cmd}"'
                try:
                    return subprocess.check_output(full_cmd, shell=True, stderr=subprocess.DEVNULL, timeout=10).decode("utf-8").strip()
                except:
                    return ""
            
            ip = ssh_exec("ip -4 addr show wlan0 2>/dev/null | grep -oP '(?<=inet\\s)\\d+(\\.\\d+){3}' || echo ''")

            # 如果需要确保不为空
            if len(ip) == 0 or not is_valid_ip(ip):
                ip = "未知"
            
            # 温度
            temp_output = ssh_exec("cat /sys/class/thermal/thermal_zone0/temp")
            try:
                temp = float(temp_output) / 1000 if temp_output else 0
                temp_str = "%0.1f" % temp
            except:
                temp_str = "0.0"
            
            return ip, temp_str
            
        except Exception as e:
            return "未知", "0.0"
    else:
        return "未知", "0.0"

def log(level, *info):
    """日志记录"""
    _time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    symbols = {1: "+", 2: "-", 3: "*", 4: "!"}
    s = symbols.get(level, " ")
    print("[%s] %s - %s" % (s, _time, ", ".join([str(x) for x in info])))

def get_core_status(timeout=0.005):
    """测试主机是否在线（防止卡死）"""
    host = "192.168.166.100"
        
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
        # 其他所有异常都视为失败
        return False
    
def is_valid_ip(ip_str):
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
        # first_octet = int(parts[0])
        # if first_octet == 10:  # 10.0.0.0/8
        #     return False
        # if first_octet == 172 and 16 <= int(parts[1]) <= 31:  # 172.16.0.0/12
        #     return False
        # if first_octet == 192 and parts[1] == '168':  # 192.168.0.0/16
        #     return False
    
    # 检查IPv6格式（简化检查）
    elif ':' in ip_str:
        # 基本格式检查
        if ip_str.count('::') > 1:
            return False
        # 更多IPv6检查可以在这里添加
    
    else:
        return False
    
    return True