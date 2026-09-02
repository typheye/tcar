#!/usr/bin/env python3
"""The sole telemetry model shared by UDP, HTTP API and internal RPC."""

import threading
import time


class Telemetry:
    def __init__(self, mpu, magnetometer, sonar, battery, servo, infrared=None):
        self.mpu, self.magnetometer, self.sonar = mpu, magnetometer, sonar
        self.battery, self.servo = battery, servo
        self.infrared = infrared
        self.lock = threading.RLock(); self.distance = 5000.0; self.mag_heading = None
        self.infrared_mask = 0
        self.heading = 0.0; self.camera_heading = 0.0
        self.heading_absolute = False; self.heading_source = "inertial"
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
            attitude = self.mpu.snapshot()
            camera_pan = self.servo.horizontal_angle()
            resolved = self.magnetometer.resolve_heading(
                attitude["heading"], mag, camera_pan
            )
            try: infrared = self.infrared.read_mask() if self.infrared else 0
            except (OSError, RuntimeError): infrared = self.infrared_mask
            with self.lock:
                self.distance, self.mag_heading, self.infrared_mask = distance, mag, infrared
                self.heading = resolved["heading"]
                self.camera_heading = resolved["camera_heading"]
                self.heading_absolute = resolved["heading_absolute"]
                self.heading_source = resolved["heading_source"]
            time.sleep(0.05)
    def snapshot(self):
        attitude = self.mpu.snapshot()
        with self.lock:
            distance, mag, infrared = self.distance, self.mag_heading, self.infrared_mask
            heading, camera_heading = self.heading, self.camera_heading
            heading_absolute, heading_source = self.heading_absolute, self.heading_source
        inertial_heading = attitude["heading"]
        return {**attitude, "inertial_heading": inertial_heading, "heading": heading,
                "camera_heading": camera_heading,
                "heading_absolute": heading_absolute, "heading_source": heading_source,
                "mag_heading": mag, "distance_mm": distance,
                "battery_voltage": self.battery.voltage, "battery_percent": self.battery.percent,
                "battery_min_voltage": self.battery.minimum_voltage,
                "battery_max_voltage": self.battery.maximum_voltage,
                "camera_pan": self.servo.horizontal_angle(),
                "infrared_mask": infrared, "timestamp": time.time()}
