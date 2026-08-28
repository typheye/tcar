#!/usr/bin/env python3
"""Singleton PWM-servo driver with authoritative position tracking."""

import os
import threading
import time

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
        self.limits = {
            1: (self.factory[1] - 700, self.factory[1] + 300),
            2: (self.factory[2] - 700, self.factory[2] + 700),
        }
        self.target_speed = {1: 0.0, 2: 0.0}
        self.current_speed = {1: 0.0, 2: 0.0}
        self.running = False
        self.thread = None
        self.resetting = False
        self.last_write = 0.0
        self.initialized = True

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, name="servo-motion", daemon=True)
        self.thread.start()
        self.reset(wait=True)
    def stop(self):
        self.running = False
        if self.thread: self.thread.join(timeout=1.0)

    def set_pulse(self, servo_id, pulse, duration_ms=100):
        if servo_id not in range(1, 7): raise ValueError("servo id must be 1..6")
        low, high = self.limits.get(servo_id, (500, 2500))
        pulse = max(low, min(high, int(pulse)))
        duration_ms = max(0, min(30000, int(duration_ms)))
        payload = [self.COMMAND, 1, duration_ms & 0xFF, duration_ms >> 8,
                   servo_id, pulse & 0xFF, pulse >> 8]
        with self.lock:
            self.bus.write(self.ADDRESS, payload)
            self.positions[servo_id] = pulse
            self.last_write = time.monotonic()
        return pulse

    def get_pulse(self, servo_id): return self.positions.get(int(servo_id))
    def set_velocity(self, servo_id, speed):
        if servo_id not in (1, 2): raise ValueError("camera servo id must be 1 or 2")
        with self.lock:
            self.target_speed[servo_id] = max(-1.0, min(1.0, float(speed)))

    def stop_motion(self):
        with self.lock:
            for servo_id in (1, 2):
                self.target_speed[servo_id] = self.current_speed[servo_id] = 0.0

    def reset(self, wait=False):
        def run():
            with self.lock:
                if self.resetting: return
                self.resetting = True
                self.stop_motion()
            try:
                # Move tilt first. The small gap prevents the expansion board
                # from occasionally dropping the second command.
                self.set_pulse(1, self.factory[1], 500)
                time.sleep(0.12)
                self.set_pulse(2, self.factory[2], 500)
                time.sleep(0.52)
            finally:
                with self.lock: self.resetting = False
        if wait:
            run()
        else:
            threading.Thread(target=run, name="servo-reset", daemon=True).start()

    def _run(self):
        while self.running:
            started = time.monotonic()
            with self.lock:
                resetting = self.resetting
                targets = dict(self.target_speed)
            if not resetting:
                for servo_id in (1, 2):
                    current = self.current_speed[servo_id]
                    target = targets[servo_id]
                    current += (target - current) * 0.28
                    if abs(current) < 0.015 and abs(target) < 0.015: current = 0.0
                    self.current_speed[servo_id] = current
                    if current:
                        step = int(round(current * 9.0))
                        if step and time.monotonic() - self.last_write >= 0.018:
                            self.set_pulse(servo_id, self.get_pulse(servo_id) + step, 45)
            time.sleep(max(0.0, 0.02 - (time.monotonic() - started)))

    def horizontal_angle(self):
        center = self.factory[2]
        return (center - self.positions[2]) * 180.0 / 2000.0
