#!/usr/bin/env python3
"""Atomic distance and RGB control for the 0x77 ultrasonic module."""

from hardware.i2c_bus import shared_i2c


class Sonar:
    ADDRESS = 0x77

    def __init__(self, bus=shared_i2c):
        self.bus = bus
        self.pixels = [(0, 0, 0), (0, 0, 0)]
        self.suspended = False

    def start(self):
        self.reset_lights()

    def stop(self):
        self.reset_lights()

    def set_suspended(self, value):
        self.suspended = bool(value)

    def distance_mm(self):
        if self.suspended:
            return 5000
        data = self.bus.write_then_read(self.ADDRESS, [0], 2)
        distance = int.from_bytes(data, "little")
        return distance if 30 <= distance <= 5000 else 5000

    def set_pixels(self, first, second, mode=0):
        colors = [tuple(first), tuple(second)]
        def operation(bus):
            bus.write_byte_data(self.ADDRESS, 2, int(mode))
            for index, color in enumerate(colors):
                register = 3 + index * 3
                for offset, value in enumerate(color):
                    bus.write_byte_data(self.ADDRESS, register + offset, max(0, min(255, int(value))))
        self.bus.retry(operation)
        self.pixels = colors

    def reset_lights(self):
        def operation(bus):
            bus.write_byte_data(self.ADDRESS, 2, 0)
            for register in range(3, 15):
                bus.write_byte_data(self.ADDRESS, register, 0)
            bus.write_byte_data(self.ADDRESS, 2, 0)
        self.bus.retry(operation, attempts=3, delay=0.05, allow_suspended=True)
        self.pixels = [(0, 0, 0), (0, 0, 0)]

