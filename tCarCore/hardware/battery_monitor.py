#!/usr/bin/env python3
"""Filtered expansion-board battery monitor."""

import statistics
import threading
import time
from collections import deque

from hardware.i2c_bus import shared_i2c


class BatteryMonitor:
    ADDRESS = 0x7A

    def __init__(self, bus=shared_i2c, interval=1.0):
        self.bus = bus
        self.interval = interval
        self.samples = deque(maxlen=5)
        self.voltage = 0.0
        self.running = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, name="battery-monitor", daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.5)

    def read_voltage(self):
        raw = int.from_bytes(self.bus.write_then_read(self.ADDRESS, [0], 2), "little")
        return raw / 1000.0

    @property
    def percent(self):
        return max(0.0, min(100.0, (self.voltage - 6.4) / 2.0 * 100.0)) if self.voltage > 6.0 else 0.0

    def _run(self):
        while self.running:
            try:
                value = self.read_voltage()
                if 5.0 < value < 9.0:
                    self.samples.append(value)
                    self.voltage = statistics.median(self.samples)
            except (OSError, RuntimeError):
                pass
            time.sleep(self.interval)

