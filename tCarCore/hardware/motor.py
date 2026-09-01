#!/usr/bin/env python3
"""Atomic four-motor driver and mecanum mixer."""

import math
import threading
import time

from hardware.i2c_bus import shared_i2c
from server.core.logd_manager import get_logger


class MotorController:
    ADDRESS = 0x7A
    FIRST_REGISTER = 31

    def __init__(self, bus=shared_i2c, minimum_speed=26):
        self.bus = bus
        self.log = get_logger("Motor")
        self.minimum_speed = int(minimum_speed)
        self.lock = threading.RLock()
        self.commands = (0, 0, 0, 0)
        self.braked = True
        # Last accepted chassis translation.  Consumers such as trajectory
        # odometry read this instead of trying to reverse the four PWM values.
        self.motion_velocity = 0.0
        self.motion_direction = 0.0
        self.motion_updated_at = 0.0
        self._last_error_log = 0.0
        self._last_forced_brake = 0.0

    def start(self): self.brake()
    def stop(self): self.brake()

    @staticmethod
    def _physical(index, value):
        value = max(-100, min(100, int(round(value))))
        return -value if index in (1, 3) else value

    def set_all(self, commands, bypass_brake=False):
        values = tuple(max(-100, min(100, int(round(v)))) for v in commands)
        if len(values) != 4:
            raise ValueError("exactly four motor commands are required")
        with self.lock:
            if self.braked and any(values) and not bypass_brake:
                return False
            # The controller refreshes at 50 Hz. Rewriting an unchanged vector
            # would create 200 motor I2C transactions per second and starve the
            # other devices sharing this bus. Hardware holds its last PWM, so
            # only transitions need to be written.
            if values == self.commands:
                return True
            try:
                self._write_vector_locked(values)
            except (OSError, IOError, RuntimeError) as error:
                # A four-register update can fail halfway through. Never leave
                # that mixed old/new vector energized: immediately converge
                # every channel to zero, then let the caller retry later.
                self._emergency_zero_locked()
                now = time.monotonic()
                if now - self._last_error_log >= 2.0:
                    self.log.warning("motor vector write failed; forced brake: %s", error)
                    self._last_error_log = now
                raise
            self.commands = values
            # A raw per-wheel command has no unambiguous chassis vector.
            # Invalidate a previous drive() vector so it cannot leak into
            # trajectory integration through RPC or self-test operations.
            self.motion_velocity = 0.0
            self.motion_updated_at = time.monotonic()
            return True

    def authorize(self):
        with self.lock: self.braked = False

    def brake(self, force=False):
        with self.lock:
            self.braked = True
            self.motion_velocity = 0.0
            self.motion_updated_at = time.monotonic()
            now = time.monotonic()
            force_due = bool(force) and now - self._last_forced_brake >= 0.08
            if self.commands == (0, 0, 0, 0) and not force_due:
                return True
            if force_due:
                self._last_forced_brake = now
            return self._emergency_zero_locked()

    def _write_vector_locked(self, values):
        """Write each motor with an independent retry boundary."""
        for index, value in enumerate(values, start=1):
            physical = self._physical(index, value)
            self.bus.write_byte_data(
                self.ADDRESS,
                self.FIRST_REGISTER + index - 1,
                physical & 0xFF,
                attempts=4,
                delay=0.008,
            )

    def _emergency_zero_locked(self):
        """Best-effort repeated all-channel zero that never stops halfway."""
        # Require two acknowledged zero writes per channel. There is no motor
        # PWM readback on this board, so duplicate writes are the closest
        # available confirmation against a silently missed transaction.
        acknowledgements = {index: 0 for index in range(1, 5)}
        last_error = None
        for _round in range(3):
            for index in range(1, 5):
                if acknowledgements[index] >= 2:
                    continue
                try:
                    self.bus.write_byte_data(
                        self.ADDRESS,
                        self.FIRST_REGISTER + index - 1,
                        0,
                        attempts=3,
                        delay=0.006,
                    )
                    acknowledgements[index] += 1
                except (OSError, IOError, RuntimeError) as error:
                    last_error = error
            pending = {
                index for index, count in acknowledgements.items() if count < 2
            }
            if not pending:
                self.commands = (0, 0, 0, 0)
                return True
            time.sleep(0.012)
        # Preserve a nonzero software marker for every uncertain motor. Future
        # idle/brake callbacks must retry instead of deduplicating the stop.
        self.commands = tuple(
            1 if index in pending else 0 for index in range(1, 5)
        )
        self.log.error(
            "emergency brake incomplete; pending motors %s: %s",
            sorted(pending), last_error,
        )
        return False

    def drive(self, velocity, direction, angular_rate=0.0):
        radians = math.radians(direction)
        vx, vy = velocity * math.cos(radians), velocity * math.sin(radians)
        vp = -angular_rate * 126.0
        accepted = self.set_all(self._normalize((vy + vx - vp, vy - vx + vp,
                                                 vy - vx - vp, vy + vx + vp)))
        if accepted:
            with self.lock:
                self.motion_velocity = max(0.0, float(velocity))
                self.motion_direction = float(direction) % 360.0
                self.motion_updated_at = time.monotonic()
        return accepted

    def motion_snapshot(self, max_age=0.15):
        """Return fresh chassis translation in mm/s and vehicle degrees."""
        with self.lock:
            age = time.monotonic() - self.motion_updated_at
            if self.braked or age > max_age:
                return 0.0, self.motion_direction
            return self.motion_velocity, self.motion_direction

    def _normalize(self, values):
        peak = max(abs(v) for v in values)
        if peak < 1e-6:
            return (0, 0, 0, 0)
        cutoff = peak * 0.08
        values = [0.0 if abs(v) <= cutoff else v for v in values]
        active = [abs(v) for v in values if v]
        gain = max(1.0, self.minimum_speed / min(active)) if active else 1.0
        gain = min(gain, 100.0 / max(active)) if active else 1.0
        result = []
        for value in values:
            command = int(round(value * gain))
            result.append(0 if command and abs(command) < self.minimum_speed else command)
        return tuple(result)
