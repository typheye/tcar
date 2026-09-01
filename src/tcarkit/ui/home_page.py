from PyQt5.QtWidgets import QVBoxLayout, QWidget

from tcarkit.depends.tcar_view import ThirdPersonView, UDPReceiver


class HomePage(QWidget):
    def __init__(self, ip, parent=None):
        super().__init__(parent)
        self.ip = ip
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.view = ThirdPersonView()
        layout.addWidget(self.view, 1)

        self.receiver = UDPReceiver(ip=ip)
        self.receiver.data_received.connect(self.update_data)
        self.receiver.start()

    def set_theme(self, dark):
        self.view.set_dark_theme(dark)

    def set_active(self, active):
        self.receiver.set_active(active)
        if active:
            self.view.timer.start(16)
            self.view.update()
        else:
            self.view.timer.stop()

    def update_data(self, data):
        if len(data) < 10:
            return
        pitch, roll, yaw = data[:3]
        self.view.set_cube_angles(yaw, pitch, roll)
        if len(data) >= 7:
            self.view.set_cube_quaternion(*data[3:7])
        mag = data[14] if len(data) >= 15 else float("nan")
        distance_mm = data[13] if len(data) >= 14 else float("nan")
        self.view.set_sensor_data(
            pitch, roll, yaw, data[7], data[8], data[9], mag, distance_mm
        )
        self.view.infrared_mask = int(round(data[17])) & 0x0F if len(data) >= 18 else 0

    def stop(self):
        self.view.timer.stop()
        self.receiver.stop()
        return (self.receiver,)
