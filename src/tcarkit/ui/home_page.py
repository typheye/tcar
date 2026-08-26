import math

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from tcarkit.depends.tcar_view import CameraReceiver, ThirdPersonView, UDPReceiver


class HomePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.view = ThirdPersonView()
        layout.addWidget(self.view, 1)

        telemetry = QHBoxLayout()
        self.yaw = QLabel("Yaw: --")
        self.pitch = QLabel("Pitch: --")
        self.roll = QLabel("Roll: --")
        self.mag = QLabel("Mag: --")
        self.status = QLabel("Waiting")
        for label in (self.yaw, self.pitch, self.roll, self.mag):
            label.setAlignment(Qt.AlignCenter)
            telemetry.addWidget(label)
        telemetry.addStretch(1)
        telemetry.addWidget(self.status)
        layout.addLayout(telemetry)

        self.camera_label = QLabel(self.view)
        self.camera_label.setFixedSize(240, 180)
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setStyleSheet("background:#111;border:1px solid #666;")
        self.camera_label.setText("Camera offline")

        self.receiver = UDPReceiver()
        self.receiver.data_received.connect(self.update_data)
        self.receiver.connection_status.connect(
            lambda connected: self.status.setText("Connected" if connected else "Waiting")
        )
        self.receiver.start()
        self.camera = CameraReceiver()
        self.camera.frame_received.connect(self.update_camera)
        self.camera.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.camera_label.move(self.view.width() - self.camera_label.width() - 10, 10)

    def update_camera(self, image):
        self.camera_label.setPixmap(QPixmap.fromImage(image).scaled(
            self.camera_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def update_data(self, data):
        if len(data) < 10:
            return
        pitch, roll, yaw = data[:3]
        self.view.set_cube_angles(yaw, pitch, roll)
        if len(data) >= 7:
            self.view.set_cube_quaternion(*data[3:7])
        mag = data[14] if len(data) >= 15 else float("nan")
        self.view.set_sensor_data(pitch, roll, yaw, data[7], data[8], data[9], mag)
        self.yaw.setText(f"Yaw: {yaw:6.1f} deg")
        self.pitch.setText(f"Pitch: {pitch:6.1f} deg")
        self.roll.setText(f"Roll: {roll:6.1f} deg")
        if math.isfinite(mag):
            directions = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
            direction = directions[int((mag + 22.5) % 360.0 // 45.0)]
            self.mag.setText(f"Mag: {mag:6.1f} deg {direction}")
        else:
            self.mag.setText("Mag: --")

    def stop(self):
        self.receiver.stop()
        self.receiver.wait(1500)
        self.camera.stop()
        self.camera.wait(1500)
