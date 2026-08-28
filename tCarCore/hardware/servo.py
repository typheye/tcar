#!/usr/bin/env python3
"""Singleton PWM-servo driver with authoritative position tracking."""

import os
import threading

import yaml

from hardware.i2c_bus import shared_i2c


class ServoController:
    ADDRESS = 0x7A
    COMMAND = 40
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self, bus=shared_i2c, config_path=None):
        if getattr(self, "initialized", False): return
        self.bus = bus
        self.lock = threading.RLock()
        self.config_path = config_path or os.path.join(os.path.dirname(os.path.dirname(__file__)), "media", "servo_config.yaml")
        with open(self.config_path, "r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        self.factory = {1: int(config.get("servo1", 1500)), 2: int(config.get("servo2", 1500))}
        self.positions = dict(self.factory)
        self.initialized = True

    def start(self): self.reset()
    def stop(self): pass

    def set_pulse(self, servo_id, pulse, duration_ms=100):
        if servo_id not in range(1, 7): raise ValueError("servo id must be 1..6")
        pulse = max(500, min(2500, int(pulse)))
        duration_ms = max(0, min(30000, int(duration_ms)))
        payload = [self.COMMAND, 1, duration_ms & 0xFF, duration_ms >> 8,
                   servo_id, pulse & 0xFF, pulse >> 8]
        with self.lock:
            self.bus.write(self.ADDRESS, payload)
            self.positions[servo_id] = pulse
        return pulse

    def get_pulse(self, servo_id): return self.positions.get(int(servo_id))
    def reset(self):
        for servo_id, pulse in self.factory.items(): self.set_pulse(servo_id, pulse, 500)

    def horizontal_angle(self):
        center = self.factory[2]
        return (center - self.positions[2]) * 180.0 / 2000.0

