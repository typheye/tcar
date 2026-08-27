#!/usr/bin/env python3
"""First-person camera view with a compact game-style telemetry HUD."""

import math
from collections import deque

from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import (
    QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PyQt5.QtWidgets import QWidget

from tcarkit.depends.tcar_view import CameraReceiver, UDPReceiver


class VisionPage(QWidget):
    def __init__(self, ip, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 360)
        self.frame = QImage()
        self.connected = False
        self.heading = 0.0
        self.heading_target = 0.0
        self.heading_ready = False
        self.battery_voltage = 0.0
        self.battery_percent = 0.0
        self.battery_samples = deque(maxlen=5)
        self.hud_ticks = 0

        # Camera frames may arrive at 20 FPS, but noisy telemetry is sampled
        # into the HUD at a stable cadence so labels and indicators do not
        # visibly twitch on every packet.
        self.hud_timer = QTimer(self)
        self.hud_timer.setInterval(100)
        self.hud_timer.timeout.connect(self._advance_hud)
        self.hud_timer.start()

        self.receiver = UDPReceiver(ip=ip)
        self.receiver.data_received.connect(self._update_telemetry)
        self.receiver.battery_status.connect(self._update_battery)
        self.receiver.start()

        self.camera = CameraReceiver(
            url=f"http://{ip}:8080/?action=stream",
            max_fps=20,
        )
        self.camera.frame_received.connect(self._update_frame)
        self.camera.connection_status.connect(self._set_connected)
        self.camera.start()

    def _update_frame(self, image):
        self.frame = image
        self.update()

    def _set_connected(self, connected):
        self.connected = connected
        self.update()

    def _update_telemetry(self, data):
        if len(data) < 3:
            return
        yaw = data[2]
        mag = data[14] if len(data) >= 15 else float("nan")
        candidate = mag if math.isfinite(mag) else yaw
        if not math.isfinite(candidate):
            return
        candidate %= 360.0
        if not self.heading_ready:
            self.heading = candidate
            self.heading_target = candidate
            self.heading_ready = True
        else:
            self.heading_target = candidate

    def _update_battery(self, voltage, percent):
        if not (math.isfinite(voltage) and math.isfinite(percent)):
            return
        if not (0.0 <= percent <= 100.0 and 0.0 <= voltage <= 20.0):
            return
        self.battery_samples.append((float(voltage), float(percent)))

    def _advance_hud(self):
        changed = False
        if self.heading_ready:
            # Circular low-pass filtering follows the shortest route through
            # 0/360 degrees and still remains responsive during real turns.
            delta = (self.heading_target - self.heading + 180.0) % 360.0 - 180.0
            if abs(delta) > 0.08:
                self.heading = (self.heading + delta * 0.24) % 360.0
                changed = True

        self.hud_ticks += 1
        if self.hud_ticks >= 10:
            self.hud_ticks = 0
            if self.battery_samples:
                samples = sorted(self.battery_samples)
                voltage = sorted(value[0] for value in samples)[len(samples) // 2]
                percent = sorted(value[1] for value in samples)[len(samples) // 2]
                if self.battery_percent == 0.0:
                    self.battery_percent = percent
                    self.battery_voltage = voltage
                else:
                    # Battery state changes slowly.  A gentle EMA removes ADC
                    # noise without making a genuine discharge invisible.
                    self.battery_percent += (percent - self.battery_percent) * 0.25
                    self.battery_voltage += (voltage - self.battery_voltage) * 0.25
                changed = True
        if changed:
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        self._draw_camera(painter)
        self._draw_compass(painter)
        self._draw_battery(painter)
        self._draw_map(painter)
        painter.end()

    def _draw_camera(self, painter):
        painter.fillRect(self.rect(), QColor(22, 24, 27))
        if self.frame.isNull():
            painter.setPen(QColor(220, 220, 220))
            painter.setFont(QFont("Segoe UI", 16))
            painter.drawText(self.rect(), Qt.AlignCenter, "Camera offline")
            return
        source_ratio = self.frame.width() / max(1, self.frame.height())
        target_ratio = self.width() / max(1, self.height())
        source = QRectF(0, 0, self.frame.width(), self.frame.height())
        if source_ratio > target_ratio:
            width = self.frame.height() * target_ratio
            source.setLeft((self.frame.width() - width) / 2)
            source.setWidth(width)
        else:
            height = self.frame.width() / target_ratio
            source.setTop((self.frame.height() - height) / 2)
            source.setHeight(height)
        painter.drawImage(QRectF(self.rect()), self.frame, source)

    def _draw_compass(self, painter):
        center_x = self.width() / 2
        top = 0
        span = min(760, self.width() * 0.68)
        for offset in range(-90, 91, 15):
            angle = (self.heading + offset) % 360.0
            x = center_x + offset / 180.0 * span
            cardinal = self._cardinal(angle)
            label = cardinal if cardinal else f"{int(round(angle / 15) * 15) % 360}"
            major = cardinal is not None
            selected = offset == 0
            tick_start = top + 17
            tick_end = top + (29 if major else 25)
            text_rect = QRectF(x - 28, top + 31, 56, 22)
            # Soft one-pixel shadow keeps white HUD text readable without a
            # gray strip obscuring the first-person view.
            painter.setPen(QPen(QColor(0, 0, 0, 115), 3))
            painter.drawLine(QPointF(x + 1, tick_start), QPointF(x + 1, tick_end))
            painter.setFont(QFont("Segoe UI", 11 if selected else 10, QFont.DemiBold))
            painter.drawText(text_rect.translated(1, 1), Qt.AlignHCenter | Qt.AlignTop, label)
            # Only the value selected by the yellow marker is bright white;
            # peripheral bearings recede in soft gray to strengthen focus.
            painter.setPen(
                QPen(QColor(255, 255, 255, 255), 2.2)
                if selected
                else QPen(QColor(205, 208, 210, 175), 1.0)
            )
            painter.drawLine(QPointF(x, tick_start), QPointF(x, tick_end))
            painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, label)
        # Downward equilateral marker sits above the scale and never covers a
        # heading label.
        marker = QPainterPath(QPointF(center_x - 7, top + 1))
        marker.lineTo(QPointF(center_x + 7, top + 1))
        marker.lineTo(QPointF(center_x, top + 13))
        marker.closeSubpath()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(238, 205, 72, 255))
        painter.drawPath(marker)

    @staticmethod
    def _cardinal(angle):
        names = {0: "N", 45: "NE", 90: "E", 135: "SE", 180: "S", 225: "SW", 270: "W", 315: "NW"}
        nearest = int((angle + 2.5) // 5 * 5) % 360
        return names.get(nearest)

    def _draw_battery(self, painter):
        width = min(500, self.width() * 0.48)
        height = 26
        x = (self.width() - width) / 2
        y = self.height() - height - 22
        outer = QRectF(x, y, width, height)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 145))
        painter.drawRect(outer)
        fill = QRectF(outer)
        fill.setWidth(fill.width() * self.battery_percent / 100.0)
        painter.setBrush(QColor(248, 248, 248, 245))
        painter.drawRect(fill)

    def _draw_map(self, painter):
        size = min(230, max(150, self.width() * 0.17))
        margin = 22
        rect = QRectF(self.width() - size - margin, self.height() - size - margin, size, size)
        painter.setPen(QPen(QColor(235, 235, 235, 185), 2))
        painter.setBrush(QColor(92, 96, 101, 185))
        painter.drawRect(rect)
        painter.setPen(QPen(QColor(215, 215, 215, 55), 1))
        for index in range(1, 4):
            px = rect.left() + rect.width() * index / 4
            py = rect.top() + rect.height() * index / 4
            painter.drawLine(QPointF(px, rect.top()), QPointF(px, rect.bottom()))
            painter.drawLine(QPointF(rect.left(), py), QPointF(rect.right(), py))
        center = rect.center()
        radius = max(8.0, size * 0.045)
        painter.setPen(QPen(QColor(255, 255, 255, 225), 2))
        painter.setBrush(QColor(205, 205, 205, 230))
        painter.drawEllipse(center, radius, radius)
        angle = math.radians(self.heading - 90.0)
        cone_length = size * 0.28
        half_fov = math.radians(24.0)
        left = QPointF(
            center.x() + math.cos(angle - half_fov) * cone_length,
            center.y() + math.sin(angle - half_fov) * cone_length,
        )
        right = QPointF(
            center.x() + math.cos(angle + half_fov) * cone_length,
            center.y() + math.sin(angle + half_fov) * cone_length,
        )
        cone = QPainterPath(center)
        cone.lineTo(left)
        cone.quadTo(
            QPointF(center.x() + math.cos(angle) * cone_length * 1.06,
                    center.y() + math.sin(angle) * cone_length * 1.06),
            right,
        )
        cone.closeSubpath()
        gradient = QLinearGradient(
            center,
            QPointF(center.x() + math.cos(angle) * cone_length,
                    center.y() + math.sin(angle) * cone_length),
        )
        gradient.setColorAt(0.0, QColor(255, 255, 255, 205))
        gradient.setColorAt(1.0, QColor(255, 255, 255, 18))
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(cone)
        painter.setPen(QPen(QColor(255, 255, 255, 225), 2))
        painter.setBrush(QColor(205, 205, 205, 230))
        painter.drawEllipse(center, radius, radius)

    def set_theme(self, dark):
        self.update()

    def stop(self):
        self.hud_timer.stop()
        self.receiver.stop()
        self.receiver.wait(1500)
        self.camera.stop()
        self.camera.wait(2500)
