#!/usr/bin/env python3
"""Atomic four-motor driver and mecanum mixer."""

import math
import threading

from hardware.i2c_bus import shared_i2c


class MotorController:
    ADDRESS = 0x7A
    FIRST_REGISTER = 31

    def __init__(self, bus=shared_i2c, minimum_speed=26):
        self.bus = bus
        self.minimum_speed = int(minimum_speed)
        self.lock = threading.RLock()
        self.commands = (0, 0, 0, 0)
        self.braked = True

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
            def operation(bus):
                for index, value in enumerate(values, start=1):
                    physical = self._physical(index, value)
                    bus.write_byte_data(self.ADDRESS, self.FIRST_REGISTER + index - 1,
                                        physical & 0xFF)
            self.bus.retry(operation)
            self.commands = values
            return True

    def authorize(self):
        with self.lock: self.braked = False

    def brake(self):
        with self.lock:
            self.braked = True
            return self.set_all((0, 0, 0, 0), bypass_brake=True)

    def drive(self, velocity, direction, angular_rate=0.0):
        radians = math.radians(direction)
        vx, vy = velocity * math.cos(radians), velocity * math.sin(radians)
        vp = -angular_rate * 126.0
        return self.set_all(self._normalize((vy + vx - vp, vy - vx + vp,
                                             vy - vx - vp, vy + vx + vp)))

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

