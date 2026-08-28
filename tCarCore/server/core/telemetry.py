#!/usr/bin/env python3
"""The sole telemetry model shared by UDP, HTTP API and internal RPC."""

import threading
import time


class Telemetry:
    def __init__(self, mpu, magnetometer, sonar, battery, servo):
        self.mpu, self.magnetometer, self.sonar = mpu, magnetometer, sonar
        self.battery, self.servo = battery, servo
        self.lock = threading.RLock(); self.distance = 5000.0; self.mag_heading = None
        self.running = False; self.thread = None
    def start(self):
        self.running = True; self.thread = threading.Thread(target=self._run, name="telemetry", daemon=True); self.thread.start()
    def stop(self):
        self.running = False
        if self.thread: self.thread.join(timeout=1.0)
    def _run(self):
        while self.running:
            try: distance = self.sonar.distance_mm()
            except (OSError, RuntimeError): distance = 5000.0
            try: mag = self.magnetometer.heading()
            except (OSError, RuntimeError): mag = None
            with self.lock: self.distance, self.mag_heading = distance, mag
            time.sleep(0.05)
    def snapshot(self):
        attitude = self.mpu.snapshot()
        with self.lock: distance, mag = self.distance, self.mag_heading
        return {**attitude, "mag_heading": mag, "distance_mm": distance,
                "battery_voltage": self.battery.voltage, "battery_percent": self.battery.percent,
                "camera_pan": self.servo.horizontal_angle(), "timestamp": time.time()}

