#!/usr/bin/env python3
"""First-person camera view with a compact game-style telemetry HUD."""

import math
import time
from collections import deque

from PyQt5.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt5.QtGui import (
    QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PyQt5.QtWidgets import QWidget

from tcarkit.depends.tcar_view import CameraReceiver, UDPReceiver


class VisionPage(QWidget):
    MAG_SYNC_WINDOW_S = 1.5
    MAG_RESYNC_INTERVAL_S = 15.0
    MAG_SYNC_VALID_S = 45.0
    MAG_SYNC_MIN_SAMPLES = 12
    MAG_SYNC_MIN_CONFIDENCE = 0.90

    def __init__(self, ip, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 360)
        self.frame = QImage()
        self.connected = False
        self.gyro_heading = 0.0
        self.gyro_target = 0.0
        self.gyro_ready = False
        self.heading_offset = None
        self.mag_sync_samples = deque(maxlen=256)
        self.mag_sync_started = None
        self.mag_last_sample_time = None
        self.mag_last_sync_time = None
        self.camera_pan_angle = 0.0
        self.camera_pan_target = 0.0
        self.camera_pan_ready = False
        self.last_inertial_yaw = None
        self.calibration_active = False
        self.battery_voltage = 0.0
        self.battery_percent = 0.0
        self.battery_samples = deque(maxlen=5)
        self.hud_ticks = 0
        self.camera_sequence = 0
        self.frame_times = deque(maxlen=45)
        self.camera_fps = 0.0
        self.frame_delay_ms = 0.0
        self.network_delay_ms = 0.0
        self.debug_visible = False
        self.debug_fps = True
        self.debug_frame_delay = True
        self.debug_network_delay = False

        # Animate heading at display cadence while sensor targets and battery
        # values remain filtered independently.
        self.hud_timer = QTimer(self)
        self.hud_timer.setInterval(16)
        self.hud_timer.timeout.connect(self._advance_hud)
        self.hud_timer.start()

        self.receiver = UDPReceiver(ip=ip)
        self.receiver.data_received.connect(self._update_telemetry)
        self.receiver.battery_status.connect(self._update_battery)
        self.receiver.network_delay.connect(self._update_network_delay)
        self.receiver.calibration_status.connect(self._update_calibration_status)
        self.receiver.start()

        self.camera = CameraReceiver(
            url=f"http://{ip}:8080/?action=stream",
            max_fps=30,
            latest_only=True,
        )
        self.camera.connection_status.connect(self._set_connected)
        self.camera.start()

        # Pull rather than queue frames. If painting ever slows down, the
        # camera thread overwrites its previous result and the GUI catches up
        # immediately on the next tick.
        self.frame_timer = QTimer(self)
        self.frame_timer.setInterval(16)
        self.frame_timer.timeout.connect(self._take_latest_frame)
        self.frame_timer.start()

    def _take_latest_frame(self):
        result = self.camera.take_latest_frame(self.camera_sequence)
        if result is None:
            return
        self.camera_sequence, image, self.frame_delay_ms = result
        self.frame = image
        now = time.monotonic()
        self.frame_times.append(now)
        if len(self.frame_times) >= 2:
            elapsed = self.frame_times[-1] - self.frame_times[0]
            if elapsed > 0:
                self.camera_fps = (len(self.frame_times) - 1) / elapsed
        self.update()

    def _set_connected(self, connected):
        self.connected = connected
        self.update()

    def _update_telemetry(self, data):
        if len(data) < 3:
            return
        # 4B publishes clockwise compass heading separately from the
        # counter-clockwise attitude yaw used by Home's quaternion scene.
        if len(data) < 17:
            return
        yaw = data[15]
        camera_pan = data[16]
        mag = data[14] if len(data) >= 15 else float("nan")
        if not math.isfinite(yaw):
            return
        yaw %= 360.0

        if self.last_inertial_yaw is not None:
            yaw_step = (yaw - self.last_inertial_yaw + 180.0) % 360.0 - 180.0
            # A real 35-degree jump cannot occur between normal telemetry
            # packets. It indicates that attitude calibration reset yaw.
            if abs(yaw_step) > 35.0:
                self._reset_heading_states()
        self.last_inertial_yaw = yaw

        if not self.gyro_ready:
            self.gyro_heading = yaw
            self.gyro_target = yaw
            self.gyro_ready = True
        else:
            self.gyro_target = yaw
        if math.isfinite(camera_pan):
            camera_pan = max(-90.0, min(90.0, camera_pan))
            if not self.camera_pan_ready:
                self.camera_pan_angle = camera_pan
                self.camera_pan_ready = True
            self.camera_pan_target = camera_pan

        # The magnetometer periodically establishes absolute heading, but it
        # never directly animates the HUD. Between syncs, smooth inertial yaw
        # carries every turn without inheriting magnetic jitter.
        if math.isfinite(mag):
            mag %= 360.0
            self._sample_magnetic_sync(yaw, mag, time.monotonic())

    def _sample_magnetic_sync(self, gyro_yaw, magnetic_heading, now):
        needs_sync = (
            self.heading_offset is None
            or self.mag_last_sync_time is None
            or now - self.mag_last_sync_time >= self.MAG_RESYNC_INTERVAL_S
        )
        if not needs_sync:
            return
        if (self.mag_last_sample_time is None
                or now - self.mag_last_sample_time > 0.5):
            self.mag_sync_samples.clear()
            self.mag_sync_started = now
        self.mag_last_sample_time = now
        if self.mag_sync_started is None:
            self.mag_sync_started = now
        self.mag_sync_samples.append((magnetic_heading - gyro_yaw) % 360.0)
        if (now - self.mag_sync_started < self.MAG_SYNC_WINDOW_S
                or len(self.mag_sync_samples) < self.MAG_SYNC_MIN_SAMPLES):
            return

        candidate, confidence = self._circular_mean(self.mag_sync_samples)
        accepted = confidence >= self.MAG_SYNC_MIN_CONFIDENCE
        if accepted and self.heading_offset is not None:
            error = (candidate - self.heading_offset + 180.0) % 360.0 - 180.0
            # A long-running gyro can legitimately drift farther than the old
            # 25-degree gate. Magnetic samples have already passed a coherent
            # multi-second circular check, so allow a re-anchor while still
            # rejecting a near-opposite disturbed field.
            accepted = abs(error) <= 90.0
        if accepted:
            if self.heading_offset is None:
                self.heading_offset = candidate
            else:
                error = (candidate - self.heading_offset + 180.0) % 360.0 - 180.0
                self.heading_offset = (self.heading_offset + error * 0.25) % 360.0
            self.mag_last_sync_time = now
        self.mag_sync_samples.clear()
        self.mag_sync_started = None

    @staticmethod
    def _circular_mean(values):
        sx = sum(math.cos(math.radians(value)) for value in values)
        sy = sum(math.sin(math.radians(value)) for value in values)
        count = max(1, len(values))
        confidence = math.hypot(sx, sy) / count
        return math.degrees(math.atan2(sy, sx)) % 360.0, confidence

    def _reset_heading_states(self):
        self.gyro_ready = False
        self.heading_offset = None
        self.mag_sync_samples.clear()
        self.mag_sync_started = None
        self.mag_last_sample_time = None
        self.mag_last_sync_time = None

    def _display_heading(self):
        offset = self.heading_offset if self.heading_offset is not None else 0.0
        return (self.gyro_heading + offset) % 360.0

    def _camera_heading(self):
        return (self._display_heading() + self.camera_pan_angle) % 360.0

    def _mag_sync_is_valid(self, now=None):
        if self.mag_last_sync_time is None:
            return False
        now = time.monotonic() if now is None else now
        return now - self.mag_last_sync_time <= self.MAG_SYNC_VALID_S

    def _update_calibration_status(self, status):
        active = status not in ("idle", "complete") and not status.startswith("failed:")
        if active and not self.calibration_active:
            self._reset_heading_states()
            self.last_inertial_yaw = None
        elif status == "complete" and self.calibration_active:
            self._reset_heading_states()
            self.last_inertial_yaw = None
        self.calibration_active = active

    def _update_battery(self, voltage, percent):
        if not (math.isfinite(voltage) and math.isfinite(percent)):
            return
        if not (0.0 <= percent <= 100.0 and 0.0 <= voltage <= 20.0):
            return
        self.battery_samples.append((float(voltage), float(percent)))

    def _update_network_delay(self, delay_ms):
        if math.isfinite(delay_ms) and 0.0 <= delay_ms < 10000.0:
            if self.network_delay_ms == 0.0:
                self.network_delay_ms = delay_ms
            else:
                self.network_delay_ms += (delay_ms - self.network_delay_ms) * 0.2

    def set_debug_visible(self, enabled):
        self.debug_visible = bool(enabled)
        self.update()

    def set_debug_metric(self, metric, enabled):
        if metric == "fps":
            self.debug_fps = bool(enabled)
        elif metric == "frame_delay":
            self.debug_frame_delay = bool(enabled)
        elif metric == "network_delay":
            self.debug_network_delay = bool(enabled)
        self.update()

    def _advance_hud(self):
        changed = False
        if self.gyro_ready:
            delta = (self.gyro_target - self.gyro_heading + 180.0) % 360.0 - 180.0
            if abs(delta) > 0.08:
                self.gyro_heading = (self.gyro_heading + delta * 0.08) % 360.0
                changed = True
        if self.camera_pan_ready:
            delta = self.camera_pan_target - self.camera_pan_angle
            if abs(delta) > 0.03:
                self.camera_pan_angle += delta * 0.12
                changed = True
        self.hud_ticks += 1
        if self.hud_ticks >= 60:
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
        self._draw_debug(painter)
        painter.end()

    def _draw_camera(self, painter):
        painter.fillRect(self.rect(), Qt.black)
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
        heading = self._camera_heading() if self.gyro_ready else self.camera_pan_angle
        center_x = self.width() / 2
        top = 0
        span = min(760, self.width() * 0.68)
        pixels_per_degree = span / 180.0
        magnetic_labels = self._mag_sync_is_valid()
        for bearing, offset in self._compass_bearings(heading):
            x = center_x + offset * pixels_per_degree
            normalized = int(bearing) % 360
            major = normalized % 15 == 0
            cardinal = (
                self._cardinal(normalized)
                if magnetic_labels else None
            )
            tick_start = top + 18
            tick_end = top + (29 if major else 23)
            # Soft one-pixel shadow keeps white HUD text readable without a
            # gray strip obscuring the first-person view.
            painter.setPen(QPen(QColor(0, 0, 0, 115), 3))
            painter.drawLine(QPointF(x + 1, tick_start), QPointF(x + 1, tick_end))
            painter.setPen(QPen(QColor(205, 208, 210, 175), 1.0))
            painter.drawLine(QPointF(x, tick_start), QPointF(x, tick_end))
            # Leave a clear focus lane below the fixed yellow marker. The
            # peripheral world ticks continue sliding behind it smoothly.
            if major and abs(offset) >= 7.0:
                label = cardinal or str(normalized)
                text_rect = QRectF(x - 28, top + 31, 56, 22)
                painter.setFont(QFont("Segoe UI", 10, QFont.DemiBold))
                painter.setPen(QPen(QColor(0, 0, 0, 115), 3))
                painter.drawText(
                    text_rect.translated(1, 1), Qt.AlignHCenter | Qt.AlignTop, label
                )
                painter.setPen(QColor(205, 208, 210, 175))
                painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, label)

        # The focus readout is exact rather than snapped to the nearest tick.
        focus_label = str(int(round(heading)) % 360)
        focus_rect = QRectF(center_x - 32, top + 31, 64, 23)
        painter.setFont(QFont("Segoe UI", 11, QFont.DemiBold))
        painter.setPen(QPen(QColor(0, 0, 0, 125), 3))
        painter.drawLine(QPointF(center_x + 1, top + 18), QPointF(center_x + 1, top + 30))
        painter.drawText(
            focus_rect.translated(1, 1), Qt.AlignHCenter | Qt.AlignTop, focus_label
        )
        painter.setPen(QPen(QColor(255, 255, 255, 255), 2.2))
        painter.drawLine(QPointF(center_x, top + 17), QPointF(center_x, top + 30))
        painter.drawText(focus_rect, Qt.AlignHCenter | Qt.AlignTop, focus_label)
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
        return names.get(int(angle) % 360)

    @staticmethod
    def _compass_bearings(heading, half_range=90, step=5):
        """Return fixed world ticks and their continuous offsets from center."""
        start = math.floor((heading - half_range) / step) * step
        end = heading + half_range
        bearings = []
        bearing = start
        while bearing <= end:
            bearings.append((bearing, bearing - heading))
            bearing += step
        return bearings

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
        if not self.gyro_ready:
            return
        heading = self._camera_heading()
        angle = math.radians(heading - 90.0)
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
        if self._mag_sync_is_valid():
            gradient.setColorAt(0.0, QColor(190, 255, 210, 215))
            gradient.setColorAt(1.0, QColor(160, 245, 190, 16))
        else:
            gradient.setColorAt(0.0, QColor(255, 255, 255, 205))
            gradient.setColorAt(1.0, QColor(255, 255, 255, 18))
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(cone)
        painter.setPen(QPen(QColor(255, 255, 255, 225), 2))
        painter.setBrush(QColor(205, 205, 205, 230))
        painter.drawEllipse(center, radius, radius)

    def _draw_debug(self, painter):
        if not self.debug_visible:
            return
        lines = []
        if self.debug_fps:
            lines.append(("FPS", f"{self.camera_fps:.1f}"))
        if self.debug_frame_delay:
            lines.append(("Frame Delay", f"{self.frame_delay_ms:.1f} ms"))
        if self.debug_network_delay:
            lines.append(("Network Delay", f"{self.network_delay_ms:.1f} ms"))
        if not lines:
            return

        panel_width = min(330.0, max(240.0, self.width() * 0.25))
        line_height = 25.0
        panel_height = 30.0 + len(lines) * line_height
        # Extend the rounded left corners outside the viewport so the visible
        # panel edge is exactly flush with the left side.
        x = -6.0
        y = (self.height() - panel_height) / 2.0
        rect = QRectF(x, y, panel_width + 6.0, panel_height)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 155))
        painter.drawRoundedRect(rect, 5, 5)
        painter.setPen(QColor(255, 255, 255, 245))
        painter.setFont(QFont("Segoe UI", 11, QFont.DemiBold))
        label_width = rect.width() * 0.56
        for index, (label, value) in enumerate(lines):
            row_top = rect.top() + 14 + index * line_height
            painter.drawText(
                QRectF(18, row_top, label_width - 18, line_height),
                Qt.AlignLeft | Qt.AlignVCenter,
                label,
            )
            painter.drawText(
                QRectF(label_width, row_top,
                       rect.right() - label_width - 18, line_height),
                Qt.AlignRight | Qt.AlignVCenter,
                value,
            )

    def set_theme(self, dark):
        self.update()

    def set_active(self, active):
        self.receiver.set_active(active)
        self.camera.set_active(active)
        if active:
            self.hud_timer.start(16)
            self.frame_timer.start(16)
            self.update()
        else:
            self.hud_timer.stop()
            self.frame_timer.stop()

    def stop(self):
        self.hud_timer.stop()
        self.frame_timer.stop()
        self.receiver.stop()
        self.camera.stop()
        return self.receiver, self.camera
