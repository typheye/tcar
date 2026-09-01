#!/usr/bin/env python3
"""Filtered expansion-board battery monitor."""

import statistics
import threading
import time
from collections import deque

from hardware.i2c_bus import shared_i2c


class BatteryMonitor:
    ADDRESS = 0x7A
    MINIMUM_VOLTAGE = 6.4
    MAXIMUM_VOLTAGE = 8.4
    RAW_MINIMUM_VOLTAGE = 5.8
    RAW_MAXIMUM_VOLTAGE = 8.8

    def __init__(self, bus=shared_i2c, interval=0.5):
        self.bus = bus
        self.interval = interval
        self.samples = deque(maxlen=15)
        self.voltage = 0.0
        self._percent = 0.0
        self.valid_samples = 0
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
        return self._percent

    @property
    def minimum_voltage(self):
        return self.MINIMUM_VOLTAGE

    @property
    def maximum_voltage(self):
        return self.MAXIMUM_VOLTAGE

    def _accept(self, value):
        if not self.RAW_MINIMUM_VOLTAGE <= value <= self.RAW_MAXIMUM_VOLTAGE:
            return
        self.samples.append(value)
        self.valid_samples += 1
        median = statistics.median(self.samples)
        if self.voltage <= 0.0:
            self.voltage = median
        else:
            # Suppress load spikes and ADC jitter. The slew limit also makes
            # one changing edge unable to move the public value abruptly.
            target = self.voltage + (median - self.voltage) * 0.12
            change = max(-0.015, min(0.015, target - self.voltage))
            self.voltage += change
        target_percent = max(0.0, min(
            100.0,
            (self.voltage - self.MINIMUM_VOLTAGE)
            / (self.MAXIMUM_VOLTAGE - self.MINIMUM_VOLTAGE) * 100.0,
        ))
        if self.valid_samples == 1:
            self._percent = target_percent
        else:
            change = max(-0.25, min(0.25, target_percent - self._percent))
            self._percent += change

    def _run(self):
        while self.running:
            try:
                value = self.read_voltage()
                self._accept(value)
            except (OSError, RuntimeError):
                pass
            time.sleep(self.interval)
