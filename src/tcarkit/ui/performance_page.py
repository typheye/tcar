#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local PC information page using the JanPNP performance-page layout."""

import platform
import time
from collections import deque

import psutil
import pyqtgraph as pg
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)


class MetricCard(QGroupBox):
    def __init__(self, title, unit="", parent=None):
        super().__init__(title, parent)
        self.setAlignment(Qt.AlignCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 8, 6, 8)
        self.value = QLabel("--")
        self.value.setAlignment(Qt.AlignCenter)
        self.value.setStyleSheet("font: bold 24px monospace;")
        layout.addWidget(self.value)
        self.subtext = QLabel("")
        self.subtext.setAlignment(Qt.AlignCenter)
        self.subtext.setStyleSheet("font: 10px;")
        layout.addWidget(self.subtext)
        self.unit = unit

    def set_value(self, value, subtext=""):
        self.value.setText(f"{value}{self.unit}")
        self.subtext.setText(subtext)


class PerformanceGraph(QGroupBox):
    def __init__(self, title, color="#4af", parent=None):
        super().__init__(title, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 4, 2, 4)
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.3)
        self.plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.curve = self.plot.plot([], [], pen=pg.mkPen(color=color, width=1.5))
        layout.addWidget(self.plot)

    def set_data(self, xs, ys):
        if len(xs) >= 2:
            self.curve.setData(xs, ys)
            self.plot.setXRange(max(0, xs[-1] - 60), xs[-1] + 1, padding=0)

    def set_theme(self, dark):
        background = "#1e1e1e" if dark else "#ffffff"
        foreground = "#d4d4d4" if dark else "#202020"
        self.plot.setBackground(background)
        for axis_name in ("left", "bottom"):
            axis = self.plot.getAxis(axis_name)
            axis.setPen(foreground)
            axis.setTextPen(foreground)


class PCInfoPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.started = time.time()
        self.history = 600
        self.timestamps = deque(maxlen=self.history)
        self.cpu_values = deque(maxlen=self.history)
        self.memory_values = deque(maxlen=self.history)
        self.disk_values = deque(maxlen=self.history)
        self.network_values = deque(maxlen=self.history)
        counters = psutil.net_io_counters()
        self.last_network_bytes = counters.bytes_sent + counters.bytes_recv
        self.last_network_time = time.monotonic()
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 10)

        cards = QHBoxLayout()
        self.uptime = MetricCard("Uptime")
        self.cpu = MetricCard("CPU", "%")
        self.memory = MetricCard("Memory", "%")
        self.disk = MetricCard("Disk", "%")
        self.network = MetricCard("Network", " MB/s")
        for card in (self.uptime, self.cpu, self.memory, self.disk, self.network):
            cards.addWidget(card)
        root.addLayout(cards)

        first_row = QHBoxLayout()
        self.cpu_graph = PerformanceGraph("CPU (%)", "#4af")
        self.memory_graph = PerformanceGraph("Memory (%)", "#6c7")
        first_row.addWidget(self.cpu_graph)
        first_row.addWidget(self.memory_graph)
        root.addLayout(first_row)

        second_row = QHBoxLayout()
        self.disk_graph = PerformanceGraph("Disk (%)", "#fd5")
        self.network_graph = PerformanceGraph("Network (MB/s)", "#b8f")
        second_row.addWidget(self.disk_graph)
        second_row.addWidget(self.network_graph)
        root.addLayout(second_row)

        info = QLabel(
            f"  {platform.node()} | {platform.platform()} | "
            f"Python {platform.python_version()}"
        )
        info.setStyleSheet("font: 10px monospace;")
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(info)

    def refresh(self):
        elapsed = time.time() - self.started
        cpu = psutil.cpu_percent()
        memory = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
        now = time.monotonic()
        counters = psutil.net_io_counters()
        total_bytes = counters.bytes_sent + counters.bytes_recv
        interval = max(0.001, now - self.last_network_time)
        network = max(0.0, total_bytes - self.last_network_bytes) / interval / 1048576.0
        self.last_network_bytes = total_bytes
        self.last_network_time = now

        self.uptime.set_value(f"{elapsed / 3600:.1f}", "hours")
        self.cpu.set_value(f"{cpu:.1f}", f"{psutil.cpu_count()} logical cores")
        self.memory.set_value(f"{memory:.1f}")
        self.disk.set_value(f"{disk:.1f}")
        self.network.set_value(f"{network:.2f}")

        self.timestamps.append(elapsed)
        self.cpu_values.append(cpu)
        self.memory_values.append(memory)
        self.disk_values.append(disk)
        self.network_values.append(network)
        timestamps = list(self.timestamps)
        self.cpu_graph.set_data(timestamps, list(self.cpu_values))
        self.memory_graph.set_data(timestamps, list(self.memory_values))
        self.disk_graph.set_data(timestamps, list(self.disk_values))
        self.network_graph.set_data(timestamps, list(self.network_values))

    def set_theme(self, dark):
        for graph in (
            self.cpu_graph,
            self.memory_graph,
            self.disk_graph,
            self.network_graph,
        ):
            graph.set_theme(dark)
