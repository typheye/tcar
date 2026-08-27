#!/usr/bin/python3
# coding=utf8
import sys
import os
import cv2
import time
import queue
import Camera
import logging
import threading
import RPCServer
import MjpgServer
import tCar
import numpy as np
import subprocess
import signal
import atexit
import Utils.buzzer as BZ
import HiwonderSDK.Sonar as Sonar
import HiwonderSDK.Board as Board
import Functions.Running as Running
import Functions.Avoidance as Avoidance
import Functions.RemoteControl as RemoteControl

PS_CONTROLLER_PROC = None  # PS2控制器进程
TCAR_SERVICE = None
RUNNING = True  # 全局运行标志

# TurboPi主程序

if sys.version_info.major == 2:
    print('Please run this program with python3!')
    sys.exit(0)

HWSONAR = Sonar.Sonar() #超声波传感器

QUEUE_RPC = queue.Queue(10)

def setBuzzer(timer):
    BZ.init()

def cleanup():
    """清理资源"""
    global PS_CONTROLLER_PROC, TCAR_SERVICE, RUNNING
    
    RUNNING = False
    print("正在清理资源...")
    
    # 终止PS2控制器进程
    if PS_CONTROLLER_PROC and PS_CONTROLLER_PROC.poll() is None:
        try:
            print("正在终止PS2控制器...")
            # 先尝试优雅终止
            PS_CONTROLLER_PROC.terminate()
            
            # 等待最多3秒
            for _ in range(30):
                if PS_CONTROLLER_PROC.poll() is not None:
                    break
                time.sleep(0.1)
            
            # 如果还在运行，强制终止
            if PS_CONTROLLER_PROC.poll() is None:
                PS_CONTROLLER_PROC.kill()
                PS_CONTROLLER_PROC.wait()
                
            print("PS2控制器已终止")
        except Exception as e:
            print(f"终止PS2控制器时出错: {e}")

    if TCAR_SERVICE:
        try:
            TCAR_SERVICE.stop()
        except Exception as e:
            print(f"停止tCar传感器服务时出错: {e}")
        TCAR_SERVICE = None
    
    # 清理Board资源
    try:
        Board.setBuzzer(0)
    except:
        pass
    
    print("资源清理完成")

voltage = 0.0

def voltageDetection():
    global voltage
    vi = 0
    dat = []
    previous_time = 0.00
    try:
        while RUNNING:  # 添加运行条件
            if time.time() >= previous_time + 1.00 :
                previous_time = time.time()
                volt = Board.getBattery()/1000.0
                
                if 5.0 < volt  < 8.5:
                    dat.insert(vi, volt)
                    vi = vi + 1            
                if vi >= 3:
                    vi = 0
                    volt1 = dat[0]
                    volt2 = dat[1]
                    volt3 = dat[2]
                    voltage = (volt1+volt2+volt3)/3.0 
                    print('Voltage:','%0.2f' % voltage)
            else:
                time.sleep(0.01)
            
    except Exception as e:
        print('Error', e)
            
        
# 运行子线程
VD = threading.Thread(target=voltageDetection)
VD.setDaemon(True)
VD.start()


def startTruckPi():
    global HWEXT, HWSONIC
    global voltage, TCAR_SERVICE, RUNNING
    
    BZ.init()

    # Share the one sonar object with tCar telemetry.  Creating a second
    # object caused concurrent stateful transactions against I2C address 0x77.
    TCAR_SERVICE = tCar.TCarService(
        sonar=HWSONAR,
        battery_reader=lambda: voltage,
    )
    TCAR_SERVICE.start()

    previous_time = 0.00
    # 超声波开启后默认关闭灯，使用共享实例的原子复位。
    if hasattr(HWSONAR, 'resetLights'):
        HWSONAR.resetLights()
    else:
        HWSONAR.setRGBMode(0)
        HWSONAR.setPixelColor(0, Board.PixelColor(0,0,0))
        HWSONAR.setPixelColor(1, Board.PixelColor(0,0,0))
        HWSONAR.show()
    
    # 玩法调用的超声波
    RemoteControl.HWSONAR = HWSONAR
    RemoteControl.init()
    RPCServer.HWSONAR = HWSONAR
    Avoidance.HWSONAR = HWSONAR
    
    RPCServer.QUEUE = QUEUE_RPC
    
    # 启动PS2控制器
    startPSControler()

    threading.Thread(target=RPCServer.startRPCServer,
                     daemon=True).start()  # rpc服务器
    threading.Thread(target=MjpgServer.startMjpgServer,
                     daemon=True).start()  # mjpg流服务器
    
    loading_picture = cv2.imread('/home/pi/MiniPi/CameraCalibration/loading.jpg')
    cam = Camera.Camera()  # 相机读取
    
    cam.camera_close()
    cam.camera_open()

    Running.cam = cam

    def publish_camera():
        while RUNNING:
            MjpgServer.set_frame(cam.frame)
            time.sleep(1.0 / 30.0)

    threading.Thread(target=publish_camera, daemon=True).start()

    while RUNNING:  # 使用RUNNING标志控制循环
        
        time.sleep(0.03)
        # 执行需要在本线程中执行的RPC命令
        while True:
            try:
                req, ret = QUEUE_RPC.get(False)
                event, params, *_ = ret
                ret[2] = req(params)  # 执行RPC命令
                event.set()
            except:
                break

        # 执行功能玩法程序：
        try:
            if Running.RunningFunc > 0 and Running.RunningFunc <= 9:
                if cam.frame is not None:
                    frame = cam.frame.copy()
                    img = Running.CurrentEXE().run(frame)
            # Camera streaming is independent from gameplay processing.
                
        except KeyboardInterrupt:
            print('收到键盘中断')
            break
        except Exception as e:
            print(f"主循环错误: {e}")
            time.sleep(0.1)  # 防止错误循环占用CPU
    
    print("主循环退出，开始清理...")
    cleanup()

def startPSControler():
    """在新线程中启动PS2控制器"""
    global PS_CONTROLLER_PROC, RUNNING
    
    def run_ps_controller():
        global PS_CONTROLLER_PROC, RUNNING
        try:
            print("正在启动PS2控制器...")
            # 启动PS2控制器
            PS_CONTROLLER_PROC = subprocess.Popen(
                ["python3", "/home/pi/TurboPi/PSControler.py"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            print(f"PS2控制器已启动，PID: {PS_CONTROLLER_PROC.pid}")
            
            # 监控子进程，同时检查RUNNING标志
            while RUNNING and PS_CONTROLLER_PROC.poll() is None:
                # 非阻塞读取输出，避免死锁
                try:
                    line = PS_CONTROLLER_PROC.stdout.readline()
                    if line:
                        print(f"[PS2控制器] {line.strip()}")
                except:
                    pass
                
                try:
                    err_line = PS_CONTROLLER_PROC.stderr.readline()
                    if err_line:
                        print(f"[PS2控制器错误] {err_line.strip()}")
                except:
                    pass
                
                time.sleep(0.1)  # 短暂休眠
            
            # 如果RUNNING为False，需要终止子进程
            if not RUNNING and PS_CONTROLLER_PROC.poll() is None:
                print("正在终止PS2控制器...")
                PS_CONTROLLER_PROC.terminate()
                time.sleep(0.5)
                if PS_CONTROLLER_PROC.poll() is None:
                    PS_CONTROLLER_PROC.kill()
            
            # 确保进程完全结束
            PS_CONTROLLER_PROC.wait(timeout=2)
            
            print("PS2控制器线程退出")
        except Exception as e:
            print(f"PS2控制器线程错误: {e}")
    
    # 在新线程中运行
    ps_thread = threading.Thread(target=run_ps_controller, daemon=True)
    ps_thread.start()


if __name__ == '__main__':
    logging.basicConfig(level=logging.ERROR)
    
    def signal_handler(signum, frame):
        """信号处理函数"""
        global RUNNING
        print(f"\n收到信号 {signum}，准备退出...")
        RUNNING = False
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # systemctl stop
    
    # 注册退出时的清理函数
    atexit.register(cleanup)
    
    try:
        startTruckPi()
    except KeyboardInterrupt:
        print("主程序被键盘中断")
    except Exception as e:
        print(f"主程序异常: {e}")
    finally:
        # 确保清理函数被调用
        cleanup()
    
    print("TurboPi程序正常退出")
    sys.exit(0)
