#!/usr/bin/env python3
"""MPU6050 inertial driver with vehicle-axis output and zero-relative yaw."""

import math
import threading
import time

from hardware.i2c_bus import shared_i2c
from server.core.logd_manager import get_logger


class MPU6050:
    ADDRESS = 0x68

    def __init__(self, bus=shared_i2c, sample_hz=100):
        self.bus = bus
        self.log = get_logger("MPU6050")
        self.interval = 1.0 / sample_hz
        self.gyro_offset = [0.0, 0.0, 0.0]
        self.pitch = self.roll = self.yaw = 0.0
        self.accel = (0.0, 0.0, 0.0)
        self.gyro = (0.0, 0.0, 0.0)
        self.quaternion = (1.0, 0.0, 0.0, 0.0)
        self.running = False
        self.thread = None
        self.lock = threading.RLock()
        self.last_time = None
        self._still_pitch = 0.0
        self._still_roll = 0.0
        self.accel_zero_pitch = 0.0
        self.accel_zero_roll = 0.0

    def start(self):
        self._initialize()
        self.calibrate_gyro()
        self.zero_attitude()
        self.running = True
        self.thread = threading.Thread(target=self._run, name="mpu6050", daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread: self.thread.join(timeout=1.5)

    def _initialize(self):
        for register, value in ((0x6B, 0x00), (0x6B, 0x01), (0x19, 0x09),
                                (0x1A, 0x06), (0x1B, 0x18), (0x1C, 0x00)):
            self.bus.write_byte_data(self.ADDRESS, register, value)
            time.sleep(0.02)

    @staticmethod
    def _i16(data, index):
        value = data[index] << 8 | data[index + 1]
        return value - 0x10000 if value & 0x8000 else value

    def read_raw(self):
        data = self.bus.read_block(self.ADDRESS, 0x3B, 14)
        return (self._i16(data, 0), self._i16(data, 2), self._i16(data, 4),
                self._i16(data, 8), self._i16(data, 10), self._i16(data, 12))

    def calibrate_gyro(self, samples=400):
        sums = [0.0, 0.0, 0.0]
        for _ in range(samples):
            values = self.read_raw()[3:]
            for index, value in enumerate(values): sums[index] += value
            time.sleep(0.005)
        self.gyro_offset = [value / samples for value in sums]
        self.log.info("gyro offset %.2f %.2f %.2f", *self.gyro_offset)

    def zero_attitude(self):
        pitch_samples, roll_samples = [], []
        for _ in range(100):
            ax, ay, az = self.read_raw()[:3]
            pitch_samples.append(math.degrees(math.atan2(-ax, -az)))
            roll_samples.append(math.degrees(math.atan2(-ay, -az)))
            time.sleep(0.005)
        with self.lock:
            self.accel_zero_pitch = sum(pitch_samples) / len(pitch_samples)
            self.accel_zero_roll = sum(roll_samples) / len(roll_samples)
            self.pitch = self.roll = self.yaw = 0.0
            self._still_pitch = self._still_roll = 0.0
            self.last_time = time.monotonic()

    def recalibrate(self):
        was_running = self.running
        self.running = False
        if self.thread and self.thread is not threading.current_thread(): self.thread.join(timeout=1.0)
        self._initialize(); self.calibrate_gyro(); self.zero_attitude()
        if was_running:
            self.running = True
            self.thread = threading.Thread(target=self._run, name="mpu6050", daemon=True); self.thread.start()

    def yaw_rate_dps(self):
        raw = self.read_raw()[5]
        return -(raw - self.gyro_offset[2]) / 16.4

    def _run(self):
        while self.running:
            started = time.monotonic()
            try:
                ax, ay, az, gx, gy, gz = self.read_raw()
            except (OSError, IOError, TimeoutError) as error:
                # A transient I2C timeout must not kill the sensor thread or
                # leave the whole UI with a permanently stale attitude.
                self.log.warning("I2C read timeout; retaining last attitude: %s", error)
                self.last_time = time.monotonic()
                time.sleep(max(0.02, self.interval))
                continue
            now = time.monotonic(); dt = min(0.05, max(0.001, now - (self.last_time or now))); self.last_time = now
            accel = (ax / 16384.0, ay / 16384.0, az / 16384.0)
            gyro = ((gx - self.gyro_offset[0]) / 16.4,
                    (gy - self.gyro_offset[1]) / 16.4,
                    (gz - self.gyro_offset[2]) / 16.4)
            norm = math.sqrt(sum(value * value for value in accel))
            with self.lock:
                if norm > 0.1:
                    # The MPU is mounted upside down. Using +Z here makes a
                    # level car look almost 180 degrees tilted after zeroing.
                    accel_pitch = self._wrap(
                        math.degrees(math.atan2(-accel[0], -accel[2]))
                        - self.accel_zero_pitch
                    )
                    accel_roll = self._wrap(
                        math.degrees(math.atan2(-accel[1], -accel[2]))
                        - self.accel_zero_roll
                    )
                    tilt_rate = math.hypot(gyro[0], gyro[1])
                    yaw_rate_abs = abs(gyro[2])
                    gravity_ok = 0.80 <= norm <= 1.25
                    # Be strict about X/Y motion during a flat yaw turn: wheel
                    # vibration must not slowly tip the rendered chassis.
                    accept_tilt = gravity_ok and (tilt_rate > 1.2) and not (
                        yaw_rate_abs > 1.0 and tilt_rate < yaw_rate_abs * 0.40
                    )
                    if accept_tilt:
                        self.pitch = self.pitch * 0.94 + accel_pitch * 0.06
                        self.roll = self.roll * 0.94 + accel_roll * 0.06
                    elif tilt_rate < 0.65:
                        self.pitch = self.pitch * 0.995 + self._still_pitch * 0.005
                        self.roll = self.roll * 0.995 + self._still_roll * 0.005
                yaw_rate = -gyro[2]
                if abs(yaw_rate) < 0.35: yaw_rate = 0.0
                self.yaw = (self.yaw + yaw_rate * dt + 180.0) % 360.0 - 180.0
                self.accel, self.gyro = accel, gyro
                # Reproduce the exact output conversion used by the proven
                # TurboPi implementation, including sign correction before
                # remapping sensor axes into the tCar vehicle frame.
                q = self._quaternion(-self.pitch, self.roll, -self.yaw)
                self.quaternion = (q[0], -q[2], -q[3], q[1])
            time.sleep(max(0.0, self.interval - (time.monotonic() - started)))

    @staticmethod
    def _quaternion(pitch, roll, yaw):
        p, r, y = map(lambda value: math.radians(value) * 0.5, (pitch, roll, yaw))
        cp, sp, cr, sr, cy, sy = math.cos(p), math.sin(p), math.cos(r), math.sin(r), math.cos(y), math.sin(y)
        return (cr*cp*cy + sr*sp*sy, sr*cp*cy - cr*sp*sy,
                cr*sp*cy + sr*cp*sy, cr*cp*sy - sr*sp*cy)

    @staticmethod
    def _wrap(value):
        return (float(value) + 180.0) % 360.0 - 180.0

    def snapshot(self):
        with self.lock:
            return {"pitch": self.pitch, "roll": self.roll, "yaw": self.yaw,
                    "heading": (-self.yaw) % 360.0, "quaternion": self.quaternion,
                    "accel": self.accel, "gyro": self.gyro}
