# -*- coding:utf-8 -*-
# 系统信息管理

import threading
import time
from utils import get_system_info, log

class SystemInfo:
    def __init__(self):
        self.info = ("", "", "", "", "", "")  # ip, cpu, mem, disk, wifi, temp
        self.update_thread = None
        self.running = False
        
    def start_monitoring(self):
        """开始监控系统信息"""
        self.running = True
        self.update_thread = threading.Thread(target=self._update_loop)
        self.update_thread.daemon = True
        self.update_thread.start()
        
    def stop_monitoring(self):
        """停止监控"""
        self.running = False
        if self.update_thread:
            self.update_thread.join(timeout=2)
            
    def _update_loop(self):
        """更新循环"""
        while self.running:
            try:
                self.info = get_system_info()
                time.sleep(2)  # 每2秒更新一次
            except Exception as e:
                log(4, "系统信息更新错误:", str(e))
                time.sleep(5)
                
    def get_info(self):
        """获取当前系统信息"""
        return self.info