#!/usr/bin/env python3
"""HMC5883L magnetic heading driver for the installed upside-down board."""

import json
import math
import os
import time
from collections import deque

from hardware.i2c_bus import shared_i2c
from server.core.logd_manager import get_logger


def wrap_angle(value):
    return (float(value) + 180.0) % 360.0 - 180.0


class HMC5883L:
    ADDRESS = 0x1E
    AXIS_MAP = (1, 2, 0)
    AXIS_SIGN = (1.0, -1.0, -1.0)

    def __init__(self, bus=shared_i2c, calibration_path=None):
        self.bus = bus
        self.log = get_logger("HMC5883L")
        self.calibration_path = calibration_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "media", "magnetometer.json"
        )
        self.offset = [0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0, 1.0]
        self.field_radius = 0.0
        self.calibrated = False
        self.samples = deque(maxlen=61)
        self.last_heading = None
        self._load()

    def start(self):
        if not self._probe():
            raise RuntimeError("HMC5883L not found at 0x1E")
        self.bus.write_byte_data(self.ADDRESS, 0x00, 0x70)
        self.bus.write_byte_data(self.ADDRESS, 0x01, 0xE0)
        self.bus.write_byte_data(self.ADDRESS, 0x02, 0x00)
        time.sleep(0.02)
        self.log.info("initialized at 0x%02X", self.ADDRESS)

    def stop(self):
        pass

    @staticmethod
    def _i16_be(data, index):
        value = data[index] << 8 | data[index + 1]
        return value - 0x10000 if value & 0x8000 else value

    def _probe(self):
        try:
            self.bus.read_byte_data(self.ADDRESS, 0x00, attempts=1)
            return True
        except OSError:
            return False

    def read_raw(self):
        data = self.bus.read_block(self.ADDRESS, 0x03, 6)
        # HMC5883L register order is X, Z, Y.
        return [self._i16_be(data, 0), self._i16_be(data, 4), self._i16_be(data, 2)]

    def read_calibrated(self):
        raw = self.read_raw()
        if any(abs(value) >= 4090 for value in raw):
            return None
        mapped = [raw[self.AXIS_MAP[i]] * self.AXIS_SIGN[i] for i in range(3)]
        return [(mapped[i] - self.offset[i]) * self.scale[i] for i in range(3)]

    def heading(self):
        if not self.calibrated:
            return None
        values = self.read_calibrated()
        if values is None:
            return None
        x, y, _ = values
        strength = math.hypot(x, y)
        if not (self.field_radius * 0.55 <= strength <= self.field_radius * 1.8):
            return None
        # This is the only N/S mounting compensation in the whole stack.
        heading = math.degrees(math.atan2(y, -x)) % 360.0
        self.samples.append(heading)
        center = heading if self.last_heading is None else self.last_heading
        deltas = sorted(wrap_angle(value - center) for value in self.samples)
        delta = deltas[len(deltas) // 2]
        self.last_heading = (center + delta * 0.12) % 360.0
        return self.last_heading

    def calibrate(self, seconds=30.0, yaw_rate_reader=None, progress=None,
                  cancelled=None):
        raw_samples = []
        turned = 0.0
        last = time.monotonic()
        deadline = last + float(seconds)
        while time.monotonic() < deadline:
            if cancelled and cancelled():
                raise RuntimeError("magnetometer calibration cancelled")
            raw_samples.append(self.read_raw())
            now = time.monotonic()
            if yaw_rate_reader:
                rate = abs(float(yaw_rate_reader()))
                if rate >= 3.0:
                    turned += rate * min(0.1, now - last)
                if progress:
                    progress(min(360.0, turned))
                if turned >= 358.0:
                    break
            last = now
            time.sleep(0.03)
        if len(raw_samples) < 20 or (yaw_rate_reader and turned < 350.0):
            raise RuntimeError(f"incomplete magnetic rotation: {turned:.1f} degrees")
        mapped = [[s[self.AXIS_MAP[i]] * self.AXIS_SIGN[i] for i in range(3)] for s in raw_samples]
        minimum = [min(row[i] for row in mapped) for i in range(3)]
        maximum = [max(row[i] for row in mapped) for i in range(3)]
        radii = [(maximum[i] - minimum[i]) * 0.5 for i in range(3)]
        if min(radii[:2]) < 35.0:
            raise RuntimeError(f"insufficient magnetic coverage: {radii}")
        radius = sum(radii[:2]) * 0.5
        self.offset = [(maximum[i] + minimum[i]) * 0.5 for i in range(3)]
        self.scale = [radius / radii[0], radius / radii[1], 1.0]
        self.field_radius = radius
        self.calibrated = True
        self.samples.clear()
        self.last_heading = None
        self._save(turned)
        return True

    def _load(self):
        try:
            with open(self.calibration_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            self.offset = [float(v) for v in data["offset"]]
            self.scale = [float(v) for v in data["scale"]]
            self.field_radius = float(data["field_radius"])
            self.calibrated = bool(data.get("calibrated"))
        except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError):
            self.calibrated = False

    def _save(self, turned):
        os.makedirs(os.path.dirname(self.calibration_path), exist_ok=True)
        with open(self.calibration_path, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "offset": self.offset, "scale": self.scale,
                       "field_radius": self.field_radius, "turn_degrees": turned,
                       "calibrated": True}, handle, indent=2)
            handle.write("\n")
