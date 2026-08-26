#!/usr/bin/python3
# coding=utf8
# 文件名: mpu6050_viewer_fixed.py

import sys
import socket
import struct
import threading
import math
import time
from collections import deque
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtOpenGL import QGLWidget
from OpenGL.GL import *
from OpenGL.GLU import *


# ============ UDP 客户端 ============
class UDPReceiver(QThread):
    """UDP接收线程"""
    # 明确指定信号类型为 list
    data_received = pyqtSignal(list)
    connection_status = pyqtSignal(bool)
    
    def __init__(self, ip='192.168.66.3', port=8888):
        super().__init__()
        self.ip = ip
        self.port = port
        self.running = True
        self.connected = False
        self.sock = None

    def run(self):
        """线程主循环"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(0.5)
            
            print(f"尝试连接服务器: {self.ip}:{self.port}")
            
            while self.running:
                try:
                    # 发送请求
                    self.sock.sendto(b'get_data', (self.ip, self.port))
                    
                    try:
                        data, addr = self.sock.recvfrom(1024)
                        
                        if len(data) == 36:  # 9个float
                            # 关键修复: 将tuple转换为list
                            values = list(struct.unpack('!9f', data))
                            
                            # 发送list到主线程
                            self.data_received.emit(values)
                            
                            if not self.connected:
                                self.connected = True
                                self.connection_status.emit(True)
                                print("✓ 连接成功！")
                        
                    except socket.timeout:
                        if self.connected:
                            self.connected = False
                            self.connection_status.emit(False)
                            print("⚠ 连接超时，等待服务器...")
                    
                except socket.error as e:
                    if self.connected:
                        self.connected = False
                        self.connection_status.emit(False)
                        print(f"✗ 连接错误: {e}")
                    time.sleep(1)
                    
        except Exception as e:
            print(f"✗ 线程异常: {e}")
        finally:
            if self.sock:
                self.sock.close()
                self.sock = None

    def stop(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None


# ============ OpenGL 渲染 ============
class GLWidget(QGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.current_angles = [0.0, 0.0, 0.0]
        self.target_angles = [0.0, 0.0, 0.0]
        self.trail_points = deque(maxlen=60)
        self.smooth_factor = 0.3
        
        self.frame_count = 0
        self.last_fps_update = time.time()
        self.current_fps = 0
        
        self.setMinimumSize(600, 600)
        
        # 60fps定时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)

    def set_angles(self, pitch, roll, yaw):
        self.target_angles = [pitch, roll, yaw]

    def initializeGL(self):
        glClearColor(0.05, 0.05, 0.08, 1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_LIGHT1)
        glEnable(GL_COLOR_MATERIAL)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        glLightfv(GL_LIGHT0, GL_POSITION, [5.0, 10.0, 5.0, 1.0])
        glLightfv(GL_LIGHT0, GL_AMBIENT, [0.3, 0.3, 0.3, 1.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.8, 0.8, 0.8, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [0.5, 0.5, 0.5, 1.0])
        
        glLightfv(GL_LIGHT1, GL_POSITION, [-5.0, -5.0, -5.0, 1.0])
        glLightfv(GL_LIGHT1, GL_AMBIENT, [0.15, 0.15, 0.2, 1.0])

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(40, w/h, 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        # 平滑插值
        for i in range(3):
            self.current_angles[i] += (self.target_angles[i] - self.current_angles[i]) * self.smooth_factor
        
        # 轨迹记录
        if len(self.trail_points) == 0 or self.frame_count % 3 == 0:
            self.trail_points.append(tuple(self.current_angles))
        
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        gluLookAt(0, 2.5, 5.5, 0, 0, 0, 0, 1, 0)
        
        self.draw_grid()
        
        glPushMatrix()
        pitch, roll, yaw = self.current_angles
        glRotatef(yaw, 0, 1, 0)
        glRotatef(pitch, 1, 0, 0)
        glRotatef(roll, 0, 0, 1)
        
        self.draw_axes()
        self.draw_cube()
        self.draw_trail()
        glPopMatrix()
        
        # FPS统计
        self.frame_count += 1
        if time.time() - self.last_fps_update > 1.0:
            self.current_fps = self.frame_count
            self.frame_count = 0
            self.last_fps_update = time.time()

    def draw_grid(self):
        glDisable(GL_LIGHTING)
        glColor4f(0.2, 0.25, 0.35, 0.5)
        glLineWidth(1.0)
        glBegin(GL_LINES)
        for i in range(-4, 5):
            glVertex3f(i, -1.8, -4)
            glVertex3f(i, -1.8, 4)
            glVertex3f(-4, -1.8, i)
            glVertex3f(4, -1.8, i)
        glEnd()
        glEnable(GL_LIGHTING)

    def draw_axes(self):
        glDisable(GL_LIGHTING)
        glLineWidth(2.5)
        glColor3f(1.0, 0.2, 0.2)
        glBegin(GL_LINES)
        glVertex3f(0, 0, 0)
        glVertex3f(2.2, 0, 0)
        glEnd()
        glColor3f(0.2, 1.0, 0.2)
        glBegin(GL_LINES)
        glVertex3f(0, 0, 0)
        glVertex3f(0, 2.2, 0)
        glEnd()
        glColor3f(0.2, 0.2, 1.0)
        glBegin(GL_LINES)
        glVertex3f(0, 0, 0)
        glVertex3f(0, 0, 2.2)
        glEnd()
        glEnable(GL_LIGHTING)

    def draw_cube(self):
        size = 0.8
        h = size
        v = [
            [-h, -h, -h], [h, -h, -h], [h, h, -h], [-h, h, -h],
            [-h, -h, h], [h, -h, h], [h, h, h], [-h, h, h]
        ]
        faces = [
            ([0,1,2,3], (0.15, 0.15, 0.85), (0,0,-1)),
            ([4,5,6,7], (0.15, 0.85, 0.15), (0,0,1)),
            ([0,1,5,4], (0.85, 0.15, 0.15), (0,-1,0)),
            ([2,3,7,6], (0.85, 0.85, 0.15), (0,1,0)),
            ([0,3,7,4], (0.85, 0.15, 0.85), (-1,0,0)),
            ([1,2,6,5], (0.15, 0.85, 0.85), (1,0,0))
        ]
        for face, color, normal in faces:
            glBegin(GL_QUADS)
            glNormal3f(*normal)
            glColor3f(*color)
            for idx in face:
                glVertex3f(*v[idx])
            glEnd()
        glDisable(GL_LIGHTING)
        glLineWidth(1.5)
        glColor4f(0.5, 0.7, 1.0, 0.4)
        edges = [(0,1), (1,2), (2,3), (3,0), (4,5), (5,6), (6,7), (7,4), (0,4), (1,5), (2,6), (3,7)]
        glBegin(GL_LINES)
        for edge in edges:
            for idx in edge:
                glVertex3f(*v[idx])
        glEnd()
        glEnable(GL_LIGHTING)

    def draw_trail(self):
        if len(self.trail_points) < 2:
            return
        glDisable(GL_LIGHTING)
        glLineWidth(2.0)
        points = list(self.trail_points)
        step = max(1, len(points) // 30)
        for i in range(step, len(points), step):
            t = i / len(points)
            r, g, b = 0.2 + 0.8*t, 0.8 - 0.6*t, 0.8 + 0.2*t
            glColor4f(r, g, b, 0.5 + 0.5*t)
            glBegin(GL_LINE_STRIP)
            for j in range(max(0, i-2), min(i+1, len(points))):
                px, py, pz = points[j]
                radius = 1.3
                yaw_rad = math.radians(pz)
                pitch_rad = math.radians(px)
                x = radius * math.cos(pitch_rad) * math.sin(yaw_rad)
                y = radius * math.sin(pitch_rad)
                z = radius * math.cos(pitch_rad) * math.cos(yaw_rad)
                glVertex3f(x, y, z)
            glEnd()
        glEnable(GL_LIGHTING)


# ============ 主窗口 ============
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MPU6050 3D姿态显示")
        self.setGeometry(100, 100, 850, 750)
        
        self.setStyleSheet("""
            QMainWindow { background-color: #0a0a12; }
            QLabel {
                background: rgba(0,0,0,0.3);
                border-radius: 6px;
                padding: 6px 12px;
            }
        """)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)
        
        # OpenGL视图
        self.gl_view = GLWidget()
        layout.addWidget(self.gl_view, 1)
        
        # 信息面板
        info_panel = QWidget()
        info_layout = QHBoxLayout(info_panel)
        info_layout.setSpacing(15)
        
        colors = ['#ff6b6b', '#ffd93d', '#6bcb77']
        names = ['Pitch', 'Roll', 'Yaw']
        self.angle_labels = {}
        for name, color in zip(names, colors):
            label = QLabel(f"{name}: 0.0°")
            label.setStyleSheet(f"""
                font-size: 22px; 
                font-weight: bold; 
                color: {color};
                min-width: 140px;
            """)
            info_layout.addWidget(label)
            self.angle_labels[name] = label
        
        info_layout.addStretch()
        
        # 状态显示
        self.status_label = QLabel("🔴 等待连接...")
        self.status_label.setStyleSheet("font-size: 16px; color: #ff4444; min-width: 180px;")
        info_layout.addWidget(self.status_label)
        
        self.fps_label = QLabel("FPS: 0")
        self.fps_label.setStyleSheet("font-size: 16px; color: #88aacc; min-width: 80px;")
        info_layout.addWidget(self.fps_label)
        
        layout.addWidget(info_panel)
        
        # 传感器数据
        self.sensor_label = QLabel("加速度: -- -- -- g | 角速度: -- -- -- °/s")
        self.sensor_label.setStyleSheet("""
            font-size: 13px; 
            color: #88aacc;
            padding: 6px 12px;
        """)
        layout.addWidget(self.sensor_label)
        
        # UDP接收器
        self.receiver = UDPReceiver()
        self.receiver.data_received.connect(self.update_data)
        self.receiver.connection_status.connect(self.update_status)
        self.receiver.start()

    def update_status(self, connected):
        if connected:
            self.status_label.setText("🟢 已连接")
            self.status_label.setStyleSheet("font-size: 16px; color: #44ff44; min-width: 180px;")
        else:
            self.status_label.setText("🔴 等待连接...")
            self.status_label.setStyleSheet("font-size: 16px; color: #ff4444; min-width: 180px;")

    def update_data(self, data):
        """更新数据 - data 现在是 list 类型"""
        pitch, roll, yaw = data[0], data[1], data[2]
        ax, ay, az = data[3], data[4], data[5]
        gx, gy, gz = data[6], data[7], data[8]
        
        self.gl_view.set_angles(pitch, roll, yaw)
        
        self.angle_labels['Pitch'].setText(f"Pitch: {pitch:6.1f}°")
        self.angle_labels['Roll'].setText(f"Roll: {roll:6.1f}°")
        self.angle_labels['Yaw'].setText(f"Yaw: {yaw:6.1f}°")
        
        self.sensor_label.setText(
            f"加速度: {ax/16384.0:6.2f} {ay/16384.0:6.2f} {az/16384.0:6.2f} g  |  "
            f"角速度: {gx/65.5:6.1f} {gy/65.5:6.1f} {gz/65.5:6.1f} °/s"
        )

    def closeEvent(self, event):
        self.receiver.stop()
        self.receiver.wait()
        event.accept()


if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())