#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local performance page using the JanPNP performance-page layout."""

import platform
import socket
import threading
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


class PerformancePage(QWidget):
    def __init__(self, ip, parent=None):
        super().__init__(parent)
        self.ip = ip
        self.started = time.time()
        self.history = 600
        self.timestamps = deque(maxlen=self.history)
        self.cpu_values = deque(maxlen=self.history)
        self.memory_values = deque(maxlen=self.history)
        self.latency_values = deque(maxlen=self.history)
        self.network_values = deque(maxlen=self.history)
        counters = psutil.net_io_counters()
        self.last_network_bytes = counters.bytes_sent + counters.bytes_recv
        self.last_network_time = time.monotonic()
        self.latency_lock = threading.Lock()
        self.last_latency = None
        self.latency_thread = threading.Thread(
            target=self._latency_loop,
            name="tcarkit-latency",
            daemon=True,
        )
        self.latency_thread.start()
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
        self.cpu = MetricCard("CPU", "%")
        self.memory = MetricCard("Memory", "%")
        self.latency = MetricCard("Latency", " ms")
        self.network = MetricCard("Network", " MB/s")
        for card in (self.latency, self.cpu, self.memory, self.network):
            cards.addWidget(card)
        root.addLayout(cards)

        first_row = QHBoxLayout()
        self.cpu_graph = PerformanceGraph("CPU (%)", "#4af")
        self.memory_graph = PerformanceGraph("Memory (%)", "#6c7")
        first_row.addWidget(self.cpu_graph)
        first_row.addWidget(self.memory_graph)
        root.addLayout(first_row)

        second_row = QHBoxLayout()
        self.latency_graph = PerformanceGraph("Latency (ms)", "#fd5")
        self.network_graph = PerformanceGraph("Network (MB/s)", "#b8f")
        second_row.addWidget(self.latency_graph)
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
        with self.latency_lock:
            latency = self.last_latency
        now = time.monotonic()
        counters = psutil.net_io_counters()
        total_bytes = counters.bytes_sent + counters.bytes_recv
        interval = max(0.001, now - self.last_network_time)
        network = max(0.0, total_bytes - self.last_network_bytes) / interval / 1048576.0
        self.last_network_bytes = total_bytes
        self.last_network_time = now

        self.cpu.set_value(f"{cpu:.1f}", f"{psutil.cpu_count()} logical cores")
        self.memory.set_value(f"{memory:.1f}")
        self.latency.set_value("--" if latency is None else f"{latency:.1f}")
        self.network.set_value(f"{network:.2f}")

        self.timestamps.append(elapsed)
        self.cpu_values.append(cpu)
        self.memory_values.append(memory)
        self.latency_values.append(float("nan") if latency is None else latency)
        self.network_values.append(network)
        timestamps = list(self.timestamps)
        self.cpu_graph.set_data(timestamps, list(self.cpu_values))
        self.memory_graph.set_data(timestamps, list(self.memory_values))
        self.latency_graph.set_data(timestamps, list(self.latency_values))
        self.network_graph.set_data(timestamps, list(self.network_values))

    def _measure_latency(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.35)
        started = time.perf_counter()
        try:
            sock.sendto(b"get_data", (self.ip, 8888))
            packet, _ = sock.recvfrom(1024)
            if len(packet) not in (40, 56, 60):
                return None
            return (time.perf_counter() - started) * 1000.0
        except OSError:
            return None
        finally:
            sock.close()

    def _latency_loop(self):
        while True:
            latency = self._measure_latency()
            with self.latency_lock:
                self.last_latency = latency
            time.sleep(1.0)

    def set_theme(self, dark):
        for graph in (
            self.cpu_graph,
            self.memory_graph,
            self.latency_graph,
            self.network_graph,
        ):
            graph.set_theme(dark)
