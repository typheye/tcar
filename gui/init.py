# -*- coding:utf-8 -*-
# 主程序入口

import time
import traceback
import spidev as SPI  # 添加SPI导入
from server.gui.public.utils import log, setup_gpio, press_key, wait_release
from server.gui.public.lcd_controller import DisplayManager
from hardware.buttons import ButtonManager
from hardware.ina219 import INA219
from server.gui.public.network_status import NetworkStatus
from server.gui.public.system_info import SystemInfo
from server.gui.launcher import ScreenManager
from media.config import *


class GUI:
    def __init__(self):
        self.running = False
        self.display = None
        self.buttons = None
        self.system_info = None
        self.network_status = None
        self.power_monitor = None
        self.screen_manager = None
        self.bootloader = None

    def initialize(self):
        """初始化系统"""
        log(3, "初始化系统...")

        try:
            # 初始化GPIO
            setup_gpio()

            # 初始化硬件
            self.display = DisplayManager()
            self.buttons = ButtonManager()
            self.power_monitor = INA219(addr=INA219_ADDR)

            # 初始化管理器
            self.system_info = SystemInfo()
            self.network_status = NetworkStatus()

            # 启动监控服务
            self.system_info.start_monitoring()
            self.network_status.start_monitoring()

            # 初始化屏幕管理器
            self.screen_manager = ScreenManager(
                self.display,
                self.buttons,
                self.system_info,
                self.network_status,
                self.power_monitor,
            )

            log(3, "系统初始化完成")
            return True

        except Exception as e:
            log(4, "系统初始化失败:", str(e))
            traceback.print_exc()
            return False

    def run(self):
        """运行主循环"""
        if not self.initialize():
            return

        self.running = True
        log(3, "启动系统...")

        btn_press = False

        try:
            if SYS_MODE == 1:
                # 显示启动画面
                start_time = time.time()

                while time.time() - start_time < 1.5:
                    self.display.lcd.show_logo()

                    # 处理按键
                    if press_key(main_PIN):
                        press_time = wait_release(main_PIN)
                        if press_time > 800: 
                            btn_press = True
                            pass

                    time.sleep(0.01)  # 避免CPU占用过高

            if SYS_MODE == 2:
                btn_press = True

            if btn_press:
                pass
            else:
                if SYS_MODE == 1:
                    # 显示启动画面
                    self.display.lcd.show_startup_animation()
                
                self.display.lcd.clear()

                # 进入主界面
                while self.running:
                    try:
                        self.screen_manager.show_main_screen()
                    except KeyboardInterrupt:
                        log(3, "用户中断")
                        break
                    except Exception as e:
                        log(4, "主循环错误:", str(e))
                        traceback.print_exc()
                        time.sleep(1)  # 防止错误循环过快

        except Exception as e:
            log(4, "系统运行错误:", str(e))
            traceback.print_exc()

        finally:
            self.shutdown()

    def shutdown(self):
        """关闭系统"""
        log(3, "关闭系统...")
        self.running = False

        try:
            if self.system_info:
                self.system_info.stop_monitoring()
            if self.network_status:
                self.network_status.stop_monitoring()
            if self.display:
                self.display.cleanup()
            if self.buttons:
                self.buttons.cleanup()

        except Exception as e:
            log(4, "系统关闭错误:", str(e))

        log(3, "系统已关闭")


def main():
    """主函数"""
    system = GUI()

    try:
        system.run()
    except KeyboardInterrupt:
        log(3, "程序被用户中断")
    except Exception as e:
        log(4, "程序异常:", str(e))
        traceback.print_exc()
    finally:
        system.shutdown()


if __name__ == "__main__":
    main()
