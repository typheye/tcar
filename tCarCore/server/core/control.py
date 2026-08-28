#!/usr/bin/env python3
"""Vehicle policy: consumes input events and owns every motion decision."""

import math
import threading

from server.core.logd_manager import get_logger


class ControlService:
    def __init__(self, motors, servos, mpu, magnetometer, buzzer, sonar):
        self.motors, self.servos, self.mpu = motors, servos, mpu
        self.magnetometer, self.buzzer, self.sonar = magnetometer, buzzer, sonar
        self.log = get_logger("Control")
        self.lock = threading.RLock(); self.last_buttons = {}; self.mode = "analog"
        self.busy = False; self.worker = None
        self.operation_cancel = threading.Event()
        self.status = "idle"
        self.desktop_toggle = None

    def start(self): self.motors.brake()
    def stop(self): self.motors.brake()

    def handle_input(self, state):
        buttons = state.get("buttons", {})
        with self.lock:
            previous_buttons = self.last_buttons
            self.last_buttons = dict(buttons)
            if buttons.get("r2"):
                self.operation_cancel.set()
                self.motors.brake(); return
            if self.busy:
                return
            select = buttons.get("select", False)
            if select and self._edge(previous_buttons, buttons, "x"):
                if self.desktop_toggle:
                    paused = self.desktop_toggle()
                    self.log.info("desktop routes %s", "paused" if paused else "active")
                return
            if self._edge(previous_buttons, buttons, "start") and select:
                self.mode = "cardinal" if self.mode == "analog" else "analog"
                self.motors.brake(); self.log.info("drive input mode: %s", self.mode); return
            if select and self._edge(previous_buttons, buttons, "a"):
                self._background("inertial calibration", self._calibrate_inertial); return
            if select and self._edge(previous_buttons, buttons, "b"):
                self._background("magnetometer calibration", self._calibrate_magnetic); return
            if self._edge(previous_buttons, buttons, "l3"):
                self._background("heading reset", self._heading_reset); return

            axes = tuple(state.get("axes", (0, 0, 0, 0))) + (0, 0, 0, 0)
            right_x, right_y = axes[2], axes[3]
            if self._edge(previous_buttons, buttons, "r3"):
                self.servos.reset()
            else:
                if abs(right_x) > 0.02:
                    self.servos.set_pulse(2, self.servos.get_pulse(2) - int(right_x * 12), 40)
                if abs(right_y) > 0.02:
                    self.servos.set_pulse(1, self.servos.get_pulse(1) + int(right_y * 12), 40)

            throttle = buttons.get("l2", False)
            if not throttle:
                self.motors.brake(); return
            self.motors.authorize()
            if buttons.get("l1") != buttons.get("r1"):
                direction = -1.0 if buttons.get("l1") else 1.0
                self.motors.drive(0.0, 0.0, direction * 0.30); return
            x, y = axes[0], axes[1]
            hat_x, hat_y = state.get("hat", (0, 0))
            if self.mode == "analog":
                # D-pad is feedback-only in analog mode.
                if hat_x or hat_y:
                    self.motors.brake()
            else:
                # The stick is completely disabled in cardinal mode.
                x, y = float(hat_x), float(-hat_y)
            magnitude = min(1.0, math.hypot(x, y))
            if magnitude <= 0.06:
                self.motors.brake()
            else:
                self.motors.authorize()
                speed = 26.0 + ((magnitude - 0.06) / 0.94) ** 1.5 * 34.0
                direction = math.degrees(math.atan2(-y, x)) % 360.0
                self.motors.drive(speed, direction)
    @staticmethod
    def _edge(previous, current, name):
        return bool(current.get(name)) and not bool(previous.get(name))

    def _background(self, name, function):
        if self.worker and self.worker.is_alive(): return
        self.busy = True; self.status = "starting:" + name.replace(" ", "_")
        self.operation_cancel.clear(); self.motors.brake()
        def run():
            try:
                self.log.info("starting %s", name); function(); self.status = "complete"
                self.log.info("completed %s", name)
            except Exception as error:
                self.status = "failed:" + str(error); self.log.exception("failed %s", name)
            finally:
                self.motors.brake(); self.busy = False; self.operation_cancel.clear()
        self.worker = threading.Thread(target=run, name=name.replace(" ", "-"), daemon=True); self.worker.start()

    def _calibrate_inertial(self):
        self.status = "gyro"
        self.buzzer.pattern([(1, .08), (0, .08), (1, .08), (0, .08), (1, .08)])
        self.sonar.set_suspended(True)
        try: self.mpu.recalibrate()
        finally:
            self.sonar.set_suspended(False)
            self.sonar.reset_lights()
        self.buzzer.pattern([(1, .5), (0, .2), (1, .5)])

    def _calibrate_magnetic(self):
        self.status = "magnetometer"
        self.buzzer.pattern([(1, .08), (0, .08), (1, .08), (0, .08), (1, .08)])
        self.sonar.set_suspended(True)
        self.motors.authorize()
        self.motors.drive(0.0, 0.0, -0.30)
        try:
            self.magnetometer.calibrate(
                30.0,
                self.mpu.yaw_rate_dps,
                cancelled=self.operation_cancel.is_set,
            )
        finally:
            self.motors.brake()
            self.sonar.set_suspended(False)
            self.sonar.reset_lights()
        self.buzzer.pattern([(1, .5), (0, .2), (1, .5)])

    def _heading_reset(self):
        for _ in range(160):
            if self.operation_cancel.is_set():
                raise RuntimeError("heading reset cancelled")
            heading = self.mpu.snapshot()["heading"]
            error = (0.0 - heading + 180.0) % 360.0 - 180.0
            if abs(error) <= 2.0: return
            self.motors.authorize()
            rate = 0.30 if abs(error) > 12.0 else 0.15
            self.motors.drive(0.0, 0.0, -rate if error > 0 else rate)
            threading.Event().wait(0.05)
        raise RuntimeError("heading reset timed out")
