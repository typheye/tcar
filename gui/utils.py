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
        # # IP地址
        # cmd = "hostname -I | cut -d' ' -f1"
        # ip = subprocess.check_output(cmd, shell=True).decode("utf-8").strip()
        # if len(ip) == 0: ip = "未知"
        cmd = "ip -4 addr show wlan0 2>/dev/null | grep -oP '(?<=inet\\s)\\d+(\\.\\d+){3}' || echo '未知'"
        ip = subprocess.check_output(cmd, shell=True).decode("utf-8").strip()

        # 如果需要确保不为空
        if len(ip) == 0 or "未知" in ip:
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
        
        # WiFi状态
        wifi = os.popen("iwconfig wlan0 | grep \"IEEE 802.11\"").read().strip()
        r = re.search("ESSID:\"([^\"]*?)\"", wifi)
        if r:
            wifi = "网络: %s" % r.group(1)
        else:
            wifi = "网络: WLAN未连接"
        
        # 温度
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            temp = float(f.read()) / 1000
            temp_str = "%0.1f" % temp
        
        return ip, cpu, mem, disk, wifi, temp_str
    except Exception as e:
        return "未知", "核心: 0%", "内存: 0%", "磁盘: 0%", "网络: WLAN未连接", "0.0"

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