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
    JOYSTICK_DEADZONE = 0.02
    MIN_SPEED = 4.0
    MAX_SPEED = 50.0
    SMOOTHING = 0.30
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
        self.reset_generation = 0
        self.reset_thread = None
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
        return pulse

    def get_pulse(self, servo_id): return self.positions.get(int(servo_id))
    def is_resetting(self):
        with self.lock: return self.resetting

    def set_velocity(self, servo_id, speed):
        if servo_id not in (1, 2): raise ValueError("camera servo id must be 1 or 2")
        speed = max(-1.0, min(1.0, float(speed)))
        magnitude = abs(speed)
        if magnitude <= self.JOYSTICK_DEADZONE:
            target = 0.0
        else:
            normalized = ((magnitude - self.JOYSTICK_DEADZONE)
                          / (1.0 - self.JOYSTICK_DEADZONE))
            pulse_step = self.MIN_SPEED + normalized ** 1.5 * (
                self.MAX_SPEED - self.MIN_SPEED
            )
            target = pulse_step if speed > 0.0 else -pulse_step
        with self.lock:
            self.target_speed[servo_id] = target

    def stop_motion(self):
        with self.lock:
            for servo_id in (1, 2):
                self.target_speed[servo_id] = self.current_speed[servo_id] = 0.0

    def reset(self, wait=False):
        with self.lock:
            self.reset_generation += 1
            requested_generation = self.reset_generation

        def sequence():
            with self.lock:
                self.resetting = True
                self.stop_motion()
            try:
                # The expansion board can lose the second command if both
                # loaded axes are started together. Fully settle tilt first,
                # then pan, and finish with a short confirmation command for
                # each axis. This is deliberately slower than normal control.
                self.set_pulse(1, self.factory[1], 500)
                time.sleep(0.68)
                self.set_pulse(2, self.factory[2], 500)
                time.sleep(0.68)
                self.set_pulse(1, self.factory[1], 120)
                time.sleep(0.20)
                self.set_pulse(2, self.factory[2], 120)
                time.sleep(0.20)
            finally:
                self.stop_motion()

        def run():
            nonlocal requested_generation
            while True:
                sequence()
                with self.lock:
                    if requested_generation == self.reset_generation:
                        self.resetting = False
                        return
                    requested_generation = self.reset_generation

        if wait:
            run()
        else:
            with self.lock:
                if self.reset_thread and self.reset_thread.is_alive():
                    return
                self.reset_thread = threading.Thread(
                    target=run, name="servo-reset", daemon=True
                )
                self.reset_thread.start()

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
                    current += (target - current) * self.SMOOTHING
                    if abs(current) < 0.5: current = 0.0
                    self.current_speed[servo_id] = current
                    if abs(current) > 0.5:
                        step = int(current)
                        self.set_pulse(
                            servo_id,
                            self.get_pulse(servo_id) + step,
                            30,
                        )
            time.sleep(max(0.0, 0.02 - (time.monotonic() - started)))

    def horizontal_angle(self):
        center = self.factory[2]
        return (center - self.positions[2]) * 180.0 / 2000.0
