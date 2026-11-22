#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sensor log page with session time, gyroscope, accelerometer and magnetometer."""

import csv
import json
import math
import os
import socket
import time

from PyQt5.QtCore import (
    QAbstractTableModel, QModelIndex, QPointF, QRectF, QSettings, Qt, QThread,
    QTimer, pyqtSignal,
)
from PyQt5.QtGui import QColor, QFont, QPainter, QPalette, QPen, QPolygonF
from PyQt5.QtWidgets import (
    QAction, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QMenu, QMessageBox, QPushButton, QSpinBox, QTableView, QVBoxLayout,
    QWidget,
)


COLUMN_SPECS = (
    ("Time (s)", 4),
    ("Gyro X (deg/s)", 2),
    ("Gyro Y (deg/s)", 2),
    ("Gyro Z (deg/s)", 2),
    ("Accel X (g)", 3),
    ("Accel Y (g)", 3),
    ("Accel Z (g)", 3),
    ("Mag X (uT)", 2),
    ("Mag Y (uT)", 2),
    ("Mag Z (uT)", 2),
    ("Mag Strength (uT)", 2),
    ("Mag Heading (deg)", 1),
    ("Mag Raw X (counts)", 0),
    ("Mag Raw Y (counts)", 0),
    ("Mag Raw Z (counts)", 0),
)

COLUMN_INDEX = {
    label: index for index, (label, _decimals) in enumerate(COLUMN_SPECS)
}

CHART_GROUPS = (
    ("Gyro (deg/s)", ("Gyro X (deg/s)", "Gyro Y (deg/s)", "Gyro Z (deg/s)")),
    ("Accel (g)", ("Accel X (g)", "Accel Y (g)", "Accel Z (g)")),
    ("Mag field (uT)", ("Mag X (uT)", "Mag Y (uT)", "Mag Z (uT)")),
    ("Mag strength (uT)", ("Mag Strength (uT)",)),
    ("Mag heading (deg)", ("Mag Heading (deg)",)),
)

CHART_COLORS = ("#e5484d", "#30a46c", "#3e63dd")

# Temporary chart-only accelerometer zero correction, measured from a static
# sample on 2026-11-20. Keep recorded data and CSV exports in raw units.
ACCEL_CHART_ZERO_OFFSETS_G = {
    "Accel X (g)": 0.028010638,
    "Accel Y (g)": -0.018631206,
}


class SensorTableModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.records = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.records)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(COLUMN_SPECS)

    def headerData(self, section, orientation, role):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(COLUMN_SPECS):
            return COLUMN_SPECS[section][0]
        return None

    def data(self, index, role):
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            _label, decimals = COLUMN_SPECS[index.column()]
            return self.format_value(
                self.records[index.row()][index.column()], decimals
            )
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    @staticmethod
    def format_value(value, decimals):
        if value is None:
            return "--"
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "--"
        if not math.isfinite(number):
            return "--"
        return f"{number:.{decimals}f}"

    def append_many(self, records):
        if not records:
            return
        first = len(self.records)
        self.beginInsertRows(QModelIndex(), first, first + len(records) - 1)
        self.records.extend(records)
        self.endInsertRows()

    def clear(self):
        if not self.records:
            return
        self.beginResetModel()
        self.records = []
        self.endResetModel()

    def export_row(self, record):
        values = []
        for index, (_label, decimals) in enumerate(COLUMN_SPECS):
            value = record[index] if index < len(record) else None
            try:
                number = float(value)
            except (TypeError, ValueError):
                values.append("")
                continue
            if not math.isfinite(number):
                values.append("")
            elif decimals == 0:
                values.append(str(int(round(number))))
            else:
                values.append(f"{number:.{decimals}f}")
        return values


class SensorChart(QWidget):
    """Auto-scaled line chart drawn directly on the recorded samples."""

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.group_index = 0
        self.window_s = 30.0
        self.setMinimumHeight(220)

    def set_group(self, index):
        self.group_index = max(0, min(len(CHART_GROUPS) - 1, int(index)))
        self.update()

    def set_window(self, seconds):
        self.window_s = max(0.0, float(seconds))
        self.update()

    @staticmethod
    def _number(value):
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    def _collect(self, indices, t_start):
        """Return ascending (time, values) pairs for the newest session."""
        samples = []
        previous_t = None
        for record in reversed(self.model.records):
            t = self._number(record[0])
            if t is None:
                continue
            # A Select+A reset restarts the clock; ignore the older session.
            if previous_t is not None and t > previous_t + 1e-6:
                break
            if t < t_start:
                break
            previous_t = t
            samples.append(
                (t, [self._number(record[index]) for index in indices])
            )
        samples.reverse()
        if len(samples) > 4000:
            stride = int(math.ceil(len(samples) / 4000.0))
            newest = samples[-1]
            samples = samples[::stride]
            if samples[-1] is not newest:
                samples.append(newest)
        return samples

    @staticmethod
    def _apply_display_offsets(samples, columns):
        offsets = [
            ACCEL_CHART_ZERO_OFFSETS_G.get(column, 0.0)
            for column in columns
        ]
        if not any(offsets):
            return samples
        return [
            (
                t,
                [
                    None if value is None else value - offset
                    for value, offset in zip(values, offsets)
                ],
            )
            for t, values in samples
        ]

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.color(QPalette.Base))
        text_color = palette.color(QPalette.WindowText)
        grid_color = QColor(text_color)
        grid_color.setAlpha(45)

        font = painter.font()
        font.setPointSizeF(8.5)
        painter.setFont(font)

        plot = QRectF(
            62.0, 26.0,
            max(10.0, self.width() - 76.0),
            max(10.0, self.height() - 56.0),
        )

        _label, columns = CHART_GROUPS[self.group_index]
        indices = [COLUMN_INDEX[column] for column in columns]

        records = self.model.records
        if not records:
            painter.setPen(QPen(text_color))
            painter.drawText(self.rect(), Qt.AlignCenter, "No data recorded yet")
            return

        t_end = None
        for record in reversed(records):
            t = self._number(record[0])
            if t is not None:
                t_end = t
                break
        if t_end is None:
            painter.setPen(QPen(text_color))
            painter.drawText(self.rect(), Qt.AlignCenter, "No data recorded yet")
            return

        t_start = max(0.0, t_end - self.window_s) if self.window_s > 0 else 0.0
        samples = self._collect(indices, t_start)
        if not samples:
            painter.setPen(QPen(text_color))
            painter.drawText(self.rect(), Qt.AlignCenter, "No data in window")
            return
        samples = self._apply_display_offsets(samples, columns)

        values = [
            value for _t, sample in samples for value in sample
            if value is not None
        ]
        if not values:
            painter.setPen(QPen(text_color))
            painter.drawText(self.rect(), Qt.AlignCenter, "No data in window")
            return

        # Keep the zero reference in view even for one-sided measurements
        # such as magnetic-field strength.
        y_min = min(min(values), 0.0)
        y_max = max(max(values), 0.0)
        span = y_max - y_min
        if span <= 0:
            span = max(abs(y_max), 1.0) * 0.5
        y_min -= span * 0.08
        y_max += span * 0.08
        if y_max <= y_min:
            y_max = y_min + 1.0

        # Grid and value labels.
        for step in range(5):
            ratio = step / 4.0
            y = plot.bottom() - ratio * plot.height()
            painter.setPen(QPen(grid_color, 1))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(QPen(text_color))
            painter.drawText(
                QRectF(0.0, y - 8.0, plot.left() - 6.0, 16.0),
                Qt.AlignRight | Qt.AlignVCenter,
                f"{y_min + ratio * (y_max - y_min):.2f}",
            )
            t = t_start + ratio * max(t_end - t_start, 0.0)
            x = plot.left() + ratio * plot.width()
            painter.setPen(QPen(grid_color, 1))
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            painter.setPen(QPen(text_color))
            painter.drawText(
                QRectF(x - 40.0, plot.bottom() + 4.0, 80.0, 18.0),
                Qt.AlignHCenter | Qt.AlignTop,
                f"{t:.2f}",
            )

        # Emphasize the physical zero level without hiding data lines.
        zero_y = plot.bottom() - (
            (0.0 - y_min) / (y_max - y_min) * plot.height()
        )
        zero_color = QColor(text_color)
        zero_color.setAlpha(165)
        painter.setPen(QPen(zero_color, 1.4, Qt.DashLine))
        painter.drawLine(
            QPointF(plot.left(), zero_y), QPointF(plot.right(), zero_y)
        )

        painter.setPen(QPen(text_color, 1))
        painter.drawRect(plot)

        # Series polylines, clipped to the plot rectangle.
        t_span = max(t_end - t_start, 1e-9)
        painter.save()
        painter.setClipRect(plot)
        for series_index in range(len(indices)):
            color = QColor(CHART_COLORS[series_index % len(CHART_COLORS)])
            painter.setPen(QPen(color, 1.6))
            polygon = QPolygonF()
            for t, sample in samples:
                value = sample[series_index]
                if value is None:
                    if polygon.size() > 1:
                        painter.drawPolyline(polygon)
                    polygon = QPolygonF()
                    continue
                x = plot.left() + (t - t_start) / t_span * plot.width()
                y = (
                    plot.bottom()
                    - (value - y_min) / (y_max - y_min) * plot.height()
                )
                polygon.append(QPointF(x, y))
            if polygon.size() > 1:
                painter.drawPolyline(polygon)
            elif polygon.size() == 1:
                painter.drawEllipse(polygon.at(0), 2.0, 2.0)
        painter.restore()

        # Legend across the top.
        legend_x = plot.left()
        for series_index, column in enumerate(columns):
            color = QColor(CHART_COLORS[series_index % len(CHART_COLORS)])
            painter.setPen(QPen(color, 2))
            painter.drawLine(
                QPointF(legend_x, 13.0), QPointF(legend_x + 16.0, 13.0)
            )
            painter.setPen(QPen(text_color))
            name = column.split(" (")[0]
            painter.drawText(QPointF(legend_x + 21.0, 17.0), name)
            legend_x += 21.0 + painter.fontMetrics().width(name) + 18.0


class SensorReceiver(QThread):
    sample_received = pyqtSignal(dict)
    connection_status = pyqtSignal(bool)

    def __init__(self, ip, port=8888, parent=None):
        super().__init__(parent)
        self.ip = ip
        self.port = port
        self.running = True
        self.active = False
        self.rate_hz = 10
        self.sock = None

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock = sock
        connected = False
        misses = 0
        deadline = time.monotonic()
        try:
            while self.running:
                if not self.active:
                    misses = 0
                    self.msleep(30)
                    deadline = time.monotonic()
                    continue
                rate = max(1, min(50, int(self.rate_hz)))
                period = 1.0 / rate
                # A short timeout keeps one lost reply from freezing the log for
                # half a second, but still tolerates a slow magnetometer read.
                timeout = min(0.30, max(0.06, period * 4.0))
                # Discard late replies to earlier requests so the current sample
                # is not delayed behind a queue of stale datagrams.
                try:
                    sock.setblocking(False)
                    while True:
                        sock.recvfrom(8192)
                except OSError:
                    pass
                try:
                    sock.settimeout(timeout)
                    sock.sendto(b"sensor_sample", (self.ip, self.port))
                    packet, _address = sock.recvfrom(8192)
                    payload = json.loads(packet.decode("utf-8"))
                    if not isinstance(payload, dict) or "t" not in payload:
                        raise ValueError("invalid sensor sample")
                    misses = 0
                    if not connected:
                        connected = True
                        self.connection_status.emit(True)
                    self.sample_received.emit(payload)
                except socket.timeout:
                    misses += 1
                    if connected and misses >= 3:
                        connected = False
                        self.connection_status.emit(False)
                except (OSError, ValueError, UnicodeDecodeError):
                    if not self.running:
                        break
                    misses += 1
                    if connected and misses >= 3:
                        connected = False
                        self.connection_status.emit(False)
                # Pace against an absolute deadline so small network hiccups do
                # not accumulate drift; when behind, restart from now.
                deadline += period
                now = time.monotonic()
                if deadline < now:
                    deadline = now
                delay = deadline - now
                if delay > 0:
                    self.msleep(max(1, int(round(delay * 1000))))
        finally:
            try:
                sock.close()
            except OSError:
                pass
            self.sock = None

    def stop(self):
        self.running = False
        sock, self.sock = self.sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def set_active(self, active):
        self.active = bool(active)

    def set_rate(self, rate_hz):
        self.rate_hz = max(1, min(50, int(rate_hz)))


class SensorPage(QWidget):
    def __init__(self, ip, parent=None):
        super().__init__(parent)
        self.ip = ip
        self.recording = False
        self.connected = False
        self.pending = []
        self.receiver = SensorReceiver(ip)
        self.receiver.sample_received.connect(self._on_sample)
        self.receiver.connection_status.connect(self._set_connected)
        self._build_ui()
        self._build_show_menu()
        self.receiver.start()
        self.flush_timer = QTimer(self)
        self.flush_timer.setInterval(33)
        self.flush_timer.timeout.connect(self._flush)
        self.flush_timer.start()
        self.chart_timer = QTimer(self)
        self.chart_timer.setInterval(50)
        self.chart_timer.timeout.connect(self._refresh_chart)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(500)
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 10)

        controls = QHBoxLayout()
        self.record_button = QPushButton("Start")
        self.record_button.setCheckable(True)
        self.record_button.setMinimumWidth(90)
        self.record_button.toggled.connect(self._toggle_recording)
        controls.addWidget(self.record_button)
        controls.addWidget(QLabel("Rate:"))
        self.rate_spin = QSpinBox()
        self.rate_spin.setRange(1, 50)
        self.rate_spin.setValue(10)
        self.rate_spin.setSuffix(" Hz")
        self.rate_spin.setMinimumWidth(90)
        self.rate_spin.valueChanged.connect(self._set_rate)
        controls.addWidget(self.rate_spin)
        self.auto_scroll = QCheckBox("Auto-scroll to bottom")
        self.auto_scroll.setChecked(True)
        controls.addWidget(self.auto_scroll)
        controls.addStretch(1)
        self.chart_button = QPushButton("Chart")
        self.chart_button.setCheckable(True)
        self.chart_button.setMinimumWidth(80)
        self.chart_button.toggled.connect(self._set_chart_mode)
        controls.addWidget(self.chart_button)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self._clear)
        controls.addWidget(self.clear_button)
        self.export_button = QPushButton("Export CSV")
        self.export_button.clicked.connect(self._export_csv)
        controls.addWidget(self.export_button)
        root.addLayout(controls)

        self.hint = QLabel(
            "Time starts at 0 after the last Select+A inertial initialization."
        )
        self.hint.setStyleSheet("font: 10px;")
        root.addWidget(self.hint)

        self.model = SensorTableModel(self)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        table_font = QFont("Monospace")
        table_font.setStyleHint(QFont.TypeWriter)
        self.table.setFont(table_font)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setDefaultSectionSize(140)
        header.setStretchLastSection(True)
        self.table.setColumnWidth(0, 110)
        root.addWidget(self.table, 1)

        self.chart_panel = QWidget()
        chart_layout = QVBoxLayout(self.chart_panel)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.setSpacing(6)
        chart_controls = QHBoxLayout()
        chart_controls.addWidget(QLabel("Series:"))
        self.series_combo = QComboBox()
        for label, _columns in CHART_GROUPS:
            self.series_combo.addItem(label)
        self.series_combo.currentIndexChanged.connect(self._set_chart_group)
        chart_controls.addWidget(self.series_combo)
        chart_controls.addWidget(QLabel("Window:"))
        self.window_combo = QComboBox()
        for label, seconds in (
            ("10 s", 10.0), ("30 s", 30.0), ("60 s", 60.0), ("All", 0.0),
        ):
            self.window_combo.addItem(label, seconds)
        self.window_combo.setCurrentIndex(1)
        self.window_combo.currentIndexChanged.connect(self._set_chart_window)
        chart_controls.addWidget(self.window_combo)
        chart_controls.addStretch(1)
        chart_layout.addLayout(chart_controls)
        self.chart = SensorChart(self.model)
        chart_layout.addWidget(self.chart, 1)
        self.chart_panel.setVisible(False)
        root.addWidget(self.chart_panel, 1)

        self.status = QLabel("idle")
        self.status.setStyleSheet("font: 10px monospace;")
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.status)

    def _build_show_menu(self):
        self.show_menu = QMenu("Show", self)
        self._column_actions = []
        for index, (label, _decimals) in enumerate(COLUMN_SPECS):
            action = QAction(label, self, checkable=True)
            action.setChecked(True)
            action.toggled.connect(
                lambda checked, column=index: self._set_column_visible(
                    column, checked
                )
            )
            self.show_menu.addAction(action)
            self._column_actions.append(action)

    def _set_column_visible(self, column, visible):
        if 0 <= column < len(COLUMN_SPECS):
            self.table.setColumnHidden(column, not visible)

    @staticmethod
    def _record_from_payload(payload):
        gyro = list(payload.get("gyro") or ()) + [None, None, None]
        accel = list(payload.get("accel") or ()) + [None, None, None]
        field = list(payload.get("mag_field") or ()) + [None, None, None]
        raw = list(payload.get("mag_raw") or ()) + [None, None, None]
        return (
            payload.get("t"),
            gyro[0],
            gyro[1],
            gyro[2],
            accel[0],
            accel[1],
            accel[2],
            field[0],
            field[1],
            field[2],
            payload.get("mag_strength"),
            payload.get("mag_heading"),
            raw[0],
            raw[1],
            raw[2],
        )

    def _toggle_recording(self, enabled):
        self.recording = bool(enabled)
        self.record_button.setText("Stop" if self.recording else "Start")
        self.receiver.set_rate(self.rate_spin.value())
        self.receiver.set_active(self.recording)
        self._update_status()

    def _set_rate(self, rate_hz):
        self.receiver.set_rate(rate_hz)
        self._update_status()

    def _set_connected(self, connected):
        self.connected = bool(connected)
        self._update_status()

    def _set_chart_mode(self, enabled):
        enabled = bool(enabled)
        self.table.setVisible(not enabled)
        self.chart_panel.setVisible(enabled)
        self.chart_button.setText("Table" if enabled else "Chart")
        if enabled:
            self.chart_timer.start()
            self._refresh_chart()
        else:
            self.chart_timer.stop()
            if self.auto_scroll.isChecked() and self.model.rowCount():
                self.table.scrollToBottom()

    def _set_chart_group(self, index):
        self.chart.set_group(index)

    def _set_chart_window(self, index):
        self.chart.set_window(self.window_combo.itemData(index))

    def _refresh_chart(self):
        if self.chart_panel.isVisible():
            self.chart.update()

    def _on_sample(self, payload):
        if not self.recording:
            return
        self.pending.append(self._record_from_payload(payload))

    def _flush(self):
        if not self.pending:
            return
        records, self.pending = self.pending, []
        self.model.append_many(records)
        if not self.chart_button.isChecked() and self.auto_scroll.isChecked():
            self.table.scrollToBottom()

    def _update_status(self):
        if self.recording:
            state = "recording"
            link = "connected" if self.connected else "no response"
        else:
            state = "idle"
            link = "connected" if self.connected else "not sampling"
        self.status.setText(
            f"{state} | {link} | {self.rate_spin.value()} Hz | "
            f"{self.model.rowCount()} rows"
        )

    def _clear(self):
        self.pending = []
        self.model.clear()
        self._refresh_chart()
        self._update_status()

    def _export_csv(self):
        self._flush()
        if not self.model.records:
            QMessageBox.information(
                self, "Sensor log", "There is no data to export."
            )
            return
        settings = QSettings("tCar", "tCarKit")
        directory = settings.value("sensor/export_dir", os.path.expanduser("~"))
        default_path = os.path.join(
            str(directory),
            f"sensor_log_{time.strftime('%Y%m%d_%H%M%S')}.csv",
        )
        path, _selected = QFileDialog.getSaveFileName(
            self, "Export sensor log", default_path,
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow([spec[0] for spec in COLUMN_SPECS])
                for record in self.model.records:
                    writer.writerow(self.model.export_row(record))
        except OSError as error:
            QMessageBox.warning(self, "Export failed", str(error))
            return
        settings.setValue("sensor/export_dir", os.path.dirname(path))
        QMessageBox.information(
            self, "Sensor log",
            f"Exported {self.model.rowCount()} rows to\n{path}",
        )

    def set_active(self, active):
        # Recording continues across tab switches so no sample is lost.
        if active:
            self._update_status()
            if self.chart_button.isChecked():
                self.chart.update()
            elif (
                self.auto_scroll.isChecked()
                and self.model.rowCount()
            ):
                self.table.scrollToBottom()

    def set_theme(self, dark):
        self.update()
        if self.chart_panel.isVisible():
            self.chart.update()

    def stop(self):
        self.recording = False
        self.receiver.set_active(False)
        self.receiver.stop()
        self.flush_timer.stop()
        self.chart_timer.stop()
        self.status_timer.stop()
        return (self.receiver,)
