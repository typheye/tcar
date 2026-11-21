#!/usr/bin/env python3
"""The sole telemetry model shared by UDP, HTTP API and internal RPC."""

import math
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
        self.mag_sample = None
        self.session_started = time.monotonic(); self.session_epoch = 0
        self.running = False; self.thread = None
    def start(self):
        with self.lock:
            self.session_started = time.monotonic()
        self.running = True; self.thread = threading.Thread(target=self._run, name="telemetry", daemon=True); self.thread.start()
    def stop(self):
        self.running = False
        if self.thread: self.thread.join(timeout=1.0)
    def reset_session(self):
        """Start a new sensor-log session at the Select+A origin."""
        with self.lock:
            self.session_epoch = (self.session_epoch + 1) % 1000000
            self.session_started = time.monotonic()
    def session_elapsed(self):
        with self.lock:
            started = self.session_started
        return max(0.0, time.monotonic() - started)
    def _run(self):
        while self.running:
            try: distance = self.sonar.distance_mm()
            except (OSError, RuntimeError): distance = 5000.0
            try: mag_sample = self.magnetometer.sample()
            except (OSError, RuntimeError): mag_sample = None
            mag = mag_sample["heading"] if mag_sample else None
            attitude = self.mpu.snapshot()
            camera_pan = self.servo.horizontal_angle()
            resolved = self.magnetometer.resolve_heading(
                attitude["heading"], mag, camera_pan
            )
            try: infrared = self.infrared.read_mask() if self.infrared else 0
            except (OSError, RuntimeError): infrared = self.infrared_mask
            with self.lock:
                self.distance, self.mag_heading, self.infrared_mask = distance, mag, infrared
                self.mag_sample = mag_sample
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
            mag_sample = self.mag_sample or {}
            elapsed = max(0.0, time.monotonic() - self.session_started)
            session = self.session_epoch
        inertial_heading = attitude["heading"]
        field = mag_sample.get("field_ut")
        raw = mag_sample.get("raw")
        battery = self.battery.snapshot()
        return {**attitude, "inertial_heading": inertial_heading, "heading": heading,
                "camera_heading": camera_heading,
                "heading_absolute": heading_absolute, "heading_source": heading_source,
                "mag_heading": mag, "distance_mm": distance,
                "mag_field_ut": field, "mag_raw": raw,
                "mag_strength_ut": mag_sample.get("strength_ut"),
                "elapsed_s": elapsed, "session": session,
                "battery_voltage": battery["voltage"], "battery_percent": battery["percent"],
                "battery_min_voltage": battery["minimum_voltage"],
                "battery_max_voltage": battery["maximum_voltage"],
                "battery_full_runtime_minutes": battery["full_runtime_minutes"],
                "battery_remaining_minutes": battery["remaining_minutes"],
                "camera_pan": self.servo.horizontal_angle(),
                "infrared_mask": infrared, "timestamp": time.time()}
    def sensor_sample(self):
        """One complete gyro/magnetometer record with session-relative time."""
        attitude = self.mpu.snapshot()
        try: mag_sample = self.magnetometer.sample()
        except (OSError, RuntimeError): mag_sample = None
        with self.lock:
            elapsed = max(0.0, time.monotonic() - self.session_started)
            session = self.session_epoch
        mag_sample = mag_sample or {}
        field = mag_sample.get("field_ut") or (None, None, None)
        raw = mag_sample.get("raw") or (None, None, None)
        return {
            "session": session,
            "t": round(elapsed, 4),
            "gyro": [self._finite(value) for value in attitude["gyro"]],
            "accel": [self._finite(value) for value in attitude["accel"]],
            "mag_field": [self._finite(value) for value in field],
            "mag_raw": [self._finite(value) for value in raw],
            "mag_strength": self._finite(mag_sample.get("strength_ut")),
            "mag_heading": self._finite(mag_sample.get("heading")),
        }
    @staticmethod
    def _finite(value):
        if value is None: return None
        try: value = float(value)
        except (TypeError, ValueError): return None
        return value if math.isfinite(value) else None
