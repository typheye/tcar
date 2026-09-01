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
        self.receiver.calibration_status.connect(self._calibration_status)
        self._inertial_reset_active = False
        self.receiver.start()

    def set_theme(self, dark):
        self.view.set_dark_theme(dark)

    def set_active(self, active):
        # Keep the tiny telemetry/status listener alive off-tab so a Select+A
        # reset cannot be missed while Vision or Performance is visible.
        self.receiver.set_active(True)
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
        if self.view.trajectory_enabled and len(data) >= 21:
            self.view.set_trajectory_position(data[18], 0.0, data[20])

    def set_trajectory_enabled(self, enabled):
        # Reset locally first so no old trail survives the state transition;
        # the 4B performs the same atomic reset when it changes state.
        self.view.reset_trajectory()
        self.view.trajectory_enabled = bool(enabled)
        self._send_command(b"trajectory_enable:" + (b"1" if enabled else b"0"))

    def set_display_trajectory(self, enabled):
        self.view.display_trajectory = bool(enabled)

    def reset_trajectory(self):
        # Reposition the model before deleting the vertices. This avoids a
        # final segment from the old position back to the origin.
        self.view.reset_trajectory()
        self._send_command(b"trajectory_reset")

    def set_camera_preset(self, preset):
        self.view.set_camera_preset(preset)

    def _calibration_status(self, status):
        text = str(status)
        inertial = "inertial_calibration" in text or text == "gyro"
        if inertial:
            self._inertial_reset_active = True
        elif self._inertial_reset_active and (
            text in ("complete", "idle") or text.startswith("failed:")
        ):
            # Select+A resets the 4B origin; mirror that session reset in the
            # desktop so its old vertices and camera offset cannot survive.
            self._inertial_reset_active = False
            self.view.reset_trajectory()

    def _send_command(self, command):
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.sendto(command, (self.ip, 8888))
        finally:
            sock.close()

    def stop(self):
        self.view.timer.stop()
        self.receiver.stop()
        return (self.receiver,)
