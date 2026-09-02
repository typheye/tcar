#!/usr/bin/env python3
"""HMC5883L magnetic heading driver for the installed upside-down board."""

import json
import math
import os
import threading
import time
from collections import deque

from hardware.i2c_bus import shared_i2c
from server.core.logd_manager import get_logger


def wrap_angle(value):
    return (float(value) + 180.0) % 360.0 - 180.0


class HMC5883L:
    ADDRESS = 0x1E
    # HMC5883L read_raw() already normalizes the register order to X/Y/Z.
    # The installed board turns around its physical X/Y plane; Z is vertical.
    # The previous QMC-era Y/Z/X mapping calibrated one horizontal axis
    # against vertical Z and therefore saw almost no coverage during a turn.
    AXIS_MAP = (0, 1, 2)
    AXIS_SIGN = (1.0, 1.0, -1.0)
    # Installed board reports physical East as North before mounting
    # compensation. Rotate once here; consumers must not remap it again.
    HEADING_OFFSET_DEG = 90.0
    HEADING_SYNC_WINDOW_S = 1.5
    HEADING_RESYNC_INTERVAL_S = 15.0
    HEADING_SYNC_VALID_S = 45.0
    HEADING_SYNC_MIN_SAMPLES = 12
    HEADING_SYNC_MIN_CONFIDENCE = 0.90

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
        self._heading_lock = threading.RLock()
        self._heading_offset = None
        self._heading_sync_samples = deque(maxlen=256)
        self._heading_sync_started = None
        self._heading_last_sample_time = None
        self._heading_last_sync_time = None
        self._heading_last_inertial = None
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
        heading = self._heading_from_xy(x, y)
        self.samples.append(heading)
        center = heading if self.last_heading is None else self.last_heading
        deltas = sorted(wrap_angle(value - center) for value in self.samples)
        delta = deltas[len(deltas) // 2]
        self.last_heading = (center + delta * 0.12) % 360.0
        return self.last_heading

    def resolve_heading(self, inertial_heading, magnetic_heading, camera_pan=0.0,
                        now=None):
        """Return the one authoritative vehicle/camera compass solution.

        The magnetometer establishes an absolute offset periodically. The MPU
        then carries smooth turns between accepted magnetic synchronization
        windows. Consumers must render these values without remapping them.
        """
        now = time.monotonic() if now is None else float(now)
        inertial = float(inertial_heading) % 360.0
        pan = max(-90.0, min(90.0, float(camera_pan)))
        with self._heading_lock:
            if self._heading_last_inertial is not None:
                step = wrap_angle(inertial - self._heading_last_inertial)
                if abs(step) > 35.0:
                    self._reset_heading_estimator_locked()
            self._heading_last_inertial = inertial

            if magnetic_heading is not None and math.isfinite(magnetic_heading):
                self._sample_heading_sync(
                    inertial, float(magnetic_heading) % 360.0, now
                )

            offset = self._heading_offset or 0.0
            vehicle = (inertial + offset) % 360.0
            absolute = (
                self._heading_last_sync_time is not None
                and now - self._heading_last_sync_time <= self.HEADING_SYNC_VALID_S
            )
            return {
                "heading": vehicle,
                "camera_heading": (vehicle + pan) % 360.0,
                "heading_absolute": absolute,
                "heading_source": "magnetic_sync" if absolute else "inertial",
            }

    def reset_heading_estimator(self):
        with self._heading_lock:
            self._reset_heading_estimator_locked()

    def _sample_heading_sync(self, inertial, magnetic, now):
        needs_sync = (
            self._heading_offset is None
            or self._heading_last_sync_time is None
            or now - self._heading_last_sync_time >= self.HEADING_RESYNC_INTERVAL_S
        )
        if not needs_sync:
            return
        if (self._heading_last_sample_time is None
                or now - self._heading_last_sample_time > 0.5):
            self._heading_sync_samples.clear()
            self._heading_sync_started = now
        self._heading_last_sample_time = now
        if self._heading_sync_started is None:
            self._heading_sync_started = now
        self._heading_sync_samples.append((magnetic - inertial) % 360.0)
        if (now - self._heading_sync_started < self.HEADING_SYNC_WINDOW_S
                or len(self._heading_sync_samples) < self.HEADING_SYNC_MIN_SAMPLES):
            return

        candidate, confidence = self._circular_mean(self._heading_sync_samples)
        accepted = confidence >= self.HEADING_SYNC_MIN_CONFIDENCE
        if accepted and self._heading_offset is not None:
            error = wrap_angle(candidate - self._heading_offset)
            accepted = abs(error) <= 90.0
        if accepted:
            if self._heading_offset is None:
                self._heading_offset = candidate
            else:
                error = wrap_angle(candidate - self._heading_offset)
                self._heading_offset = (self._heading_offset + error * 0.25) % 360.0
            self._heading_last_sync_time = now
        self._heading_sync_samples.clear()
        self._heading_sync_started = None

    @staticmethod
    def _circular_mean(values):
        sx = sum(math.cos(math.radians(value)) for value in values)
        sy = sum(math.sin(math.radians(value)) for value in values)
        count = max(1, len(values))
        return math.degrees(math.atan2(sy, sx)) % 360.0, math.hypot(sx, sy) / count

    def _reset_heading_estimator_locked(self):
        self._heading_offset = None
        self._heading_sync_samples.clear()
        self._heading_sync_started = None
        self._heading_last_sample_time = None
        self._heading_last_sync_time = None
        self._heading_last_inertial = None

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
        self.pending_turn_degrees = turned
        return True

    def commit_calibration(self):
        """Persist only after the caller has validated a stable heading."""
        self._save(getattr(self, "pending_turn_degrees", 0.0))

    def confirm_stable_heading(self, seconds=1.5, min_samples=20,
                               min_confidence=0.88):
        """Validate and seed the heading immediately after calibration."""
        headings = []
        deadline = time.monotonic() + float(seconds)
        while time.monotonic() < deadline:
            values = self.read_calibrated()
            if values is not None:
                x, y, _ = values
                strength = math.hypot(x, y)
                if (self.field_radius * 0.55 <= strength
                        <= self.field_radius * 1.8):
                    headings.append(self._heading_from_xy(x, y))
            time.sleep(0.03)
        if len(headings) < int(min_samples):
            return None
        sx = sum(math.cos(math.radians(value)) for value in headings)
        sy = sum(math.sin(math.radians(value)) for value in headings)
        confidence = math.hypot(sx, sy) / len(headings)
        if confidence < float(min_confidence):
            return None
        heading = math.degrees(math.atan2(sy, sx)) % 360.0
        self.samples.clear()
        self.samples.append(heading)
        self.last_heading = heading
        return heading

    @classmethod
    def _heading_from_xy(cls, x, y):
        # The HMC board's connector orientation rotates its physical X/Y
        # frame 90 degrees relative to the tCar nose. Keep this one mounting
        # correction in the 4B driver: W must remain W, not appear as S.
        return (math.degrees(math.atan2(y, -x)) + cls.HEADING_OFFSET_DEG) % 360.0

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
