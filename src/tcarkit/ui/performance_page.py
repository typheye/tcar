#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Raspberry Pi performance page using the JanPNP layout."""

import json
import socket
import threading
import time
from collections import deque

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
        self.last_network_bytes = None
        self.last_network_time = time.monotonic()
        self.performance_lock = threading.Lock()
        self.last_snapshot = None
        self.last_latency = None
        self.running = True
        self.active = True
        self.stop_event = threading.Event()
        self.performance_thread = threading.Thread(
            target=self._performance_loop,
            name="tcarkit-performance",
            daemon=True,
        )
        self.performance_thread.start()
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

        self.info = QLabel("  Raspberry Pi 4B | waiting for performance data")
        self.info.setStyleSheet("font: 10px monospace;")
        self.info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.info)

    def refresh(self):
        elapsed = time.time() - self.started
        with self.performance_lock:
            snapshot = dict(self.last_snapshot) if self.last_snapshot else None
            latency = self.last_latency
        now = time.monotonic()
        cpu = float(snapshot.get("cpu", float("nan"))) if snapshot else float("nan")
        memory = float(snapshot.get("memory", float("nan"))) if snapshot else float("nan")
        total_bytes = int(snapshot.get("network_bytes", 0)) if snapshot else 0
        if snapshot and self.last_network_bytes is not None:
            interval = max(0.001, now - self.last_network_time)
            network = max(0.0, total_bytes - self.last_network_bytes) / interval / 1048576.0
        else:
            network = float("nan")
        if snapshot:
            self.last_network_bytes = total_bytes
            self.last_network_time = now

        self.cpu.set_value("--" if snapshot is None else f"{cpu:.1f}",
                           "" if snapshot is None else f"{snapshot.get('cores', '--')} cores")
        self.memory.set_value("--" if snapshot is None else f"{memory:.1f}")
        self.latency.set_value("--" if latency is None else f"{latency:.1f}")
        self.network.set_value(
            "--" if snapshot is None or network != network else f"{network:.2f}"
        )
        if snapshot:
            self.info.setText(
                f"  {snapshot.get('hostname', 'Raspberry Pi 4B')} | "
                f"{snapshot.get('platform', 'Linux')} | "
                f"Python {snapshot.get('python', '--')}"
            )

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

    def _poll_performance(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.6)
        started = time.perf_counter()
        try:
            sock.sendto(b"performance_status", (self.ip, 8888))
            packet, _ = sock.recvfrom(2048)
            latency = (time.perf_counter() - started) * 1000.0
            snapshot = json.loads(packet.decode("utf-8"))
            if not isinstance(snapshot, dict) or "error" in snapshot:
                return None, None
            return snapshot, latency
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
            return None, None
        finally:
            sock.close()

    def _performance_loop(self):
        while self.running:
            if not self.active:
                self.stop_event.wait(0.1)
                continue
            snapshot, latency = self._poll_performance()
            with self.performance_lock:
                self.last_snapshot = snapshot
                self.last_latency = latency
            self.stop_event.wait(1.0)

    def set_active(self, active):
        self.active = bool(active)
        if active:
            self.timer.start(1000)
            self.refresh()
        else:
            self.timer.stop()

    def stop(self):
        self.running = False
        self.stop_event.set()
        self.timer.stop()
        return (self.performance_thread,)

    def set_theme(self, dark):
        for graph in (
            self.cpu_graph,
            self.memory_graph,
            self.latency_graph,
            self.network_graph,
        ):
            graph.set_theme(dark)
