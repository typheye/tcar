#!/usr/bin/env python3
"""Vehicle policy: consumes input events and owns every motion decision."""

import math
import threading
import time

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
        self._last_hat = (0, 0)
        self._right_servo_active = {1: False, 2: False}
        self._desktop_combo_active = False

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
            if select and self._edge(previous_buttons, buttons, "y"):
                muted = self.buzzer.toggle_mute()
                self.log.info("buzzer %s", "muted" if muted else "unmuted")
                return
            self._button_feedback(previous_buttons, buttons, select)
            hat = tuple(state.get("hat", (0, 0)))
            if hat != (0, 0) and self._last_hat == (0, 0):
                self.buzzer.pattern([(1, .012)])
            self._last_hat = hat
            desktop_combo = select and buttons.get("x", False)
            if desktop_combo and not self._desktop_combo_active:
                self._desktop_combo_active = True
                if self.desktop_toggle:
                    paused = self.desktop_toggle()
                    self.log.info("desktop routes %s", "paused" if paused else "active")
                    self.buzzer.switch_feedback(paused)
                return
            if not desktop_combo:
                self._desktop_combo_active = False
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
                self._right_servo_active = {1: False, 2: False}
            elif not self.servos.is_resetting():
                for servo_id, value in ((2, -right_x), (1, right_y)):
                    # ServoController reproduces TurboPi's 0.02 deadzone and
                    # amplitude-to-speed curve. Preserve the raw stick value.
                    active = abs(value) > self.servos.JOYSTICK_DEADZONE
                    if active:
                        self.servos.set_velocity(servo_id, value)
                    elif self._right_servo_active[servo_id]:
                        self.servos.set_velocity(servo_id, 0.0)
                    self._right_servo_active[servo_id] = active

            throttle = buttons.get("l2", False)
            if not throttle:
                self.motors.brake(); return
            self.motors.authorize()
            if buttons.get("l1") != buttons.get("r1"):
                direction = -1.0 if buttons.get("l1") else 1.0
                self.motors.drive(0.0, 0.0, direction * 0.30); return
            x, y = axes[0], axes[1]
            hat_x, hat_y = hat
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

    def _button_feedback(self, previous, current, select):
        # L2/R2 intentionally have no sound. Calibration owns the buzzer and
        # suppresses all normal key feedback while it is running.
        for name in ("y", "b", "a", "x", "l1", "r1", "select", "start", "l3", "r3", "mode"):
            if self._edge(previous, current, name):
                if select and name in ("x", "y"):
                    continue
                duration = .05 if select and name in ("a", "b", "x", "start") else .012
                self.buzzer.pattern([(1, duration)])
        # D-pad is a real button surface even when it is feedback-only.
        # Its edge is not represented in pygame's button array.

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
            except RuntimeError as error:
                # Cancellation and failed calibration validation are expected
                # operation results, not uncaught program faults.
                self.status = "failed:" + str(error)
                self.log.warning("%s failed: %s", name, error)
            except Exception as error:
                self.status = "failed:" + str(error)
                self.log.exception("unexpected failure in %s", name)
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
        succeeded = False
        previous = (
            list(self.magnetometer.offset),
            list(self.magnetometer.scale),
            self.magnetometer.field_radius,
            self.magnetometer.calibrated,
            self.magnetometer.last_heading,
        )
        try:
            self.magnetometer.calibrate(
                30.0,
                self.mpu.yaw_rate_dps,
                cancelled=self.operation_cancel.is_set,
            )
            self.motors.brake()
            threading.Event().wait(0.75)
            heading = self.magnetometer.confirm_stable_heading()
            if heading is None:
                raise RuntimeError("magnetometer heading validation failed")
            self.magnetometer.commit_calibration()
            self.log.info("magnetometer heading ready %.1f deg", heading)
            succeeded = True
        finally:
            if not succeeded:
                (self.magnetometer.offset, self.magnetometer.scale,
                 self.magnetometer.field_radius,
                 self.magnetometer.calibrated,
                 self.magnetometer.last_heading) = previous
                self.magnetometer.samples.clear()
            self.motors.brake()
            self.sonar.set_suspended(False)
            self.sonar.reset_lights()
            if succeeded:
                self.buzzer.pattern([(1, .5), (0, .2), (1, .5)])
            else:
                self.buzzer.pattern([(1, 1.0)])

    def _heading_reset(self):
        deadline = time.monotonic() + 12.0
        settled_since = None
        last_direction = None
        final_pulses = 0
        try:
            while time.monotonic() < deadline:
                if self.operation_cancel.is_set():
                    raise RuntimeError("heading reset cancelled")
                heading = self.mpu.snapshot()["heading"]
                error = (0.0 - heading + 180.0) % 360.0 - 180.0
                abs_error = abs(error)

                if abs_error <= 2.0:
                    self.motors.brake()
                    last_direction = None
                    if settled_since is None:
                        settled_since = time.monotonic()
                    elif time.monotonic() - settled_since >= 0.35:
                        self.log.info("heading reset complete %.1f deg", heading)
                        return
                    threading.Event().wait(0.04)
                    continue

                settled_since = None
                if abs_error > 30.0:
                    rate = 0.38
                elif abs_error > 12.0:
                    rate = 0.28
                else:
                    rate = 0.15

                # MotorController angular_rate is the physical yaw sign. The
                # old port accidentally negated it once more, so positive
                # error drove away from zero and produced the dragon-tail
                # oscillation. This matches TurboPi's direction=-1 branch.
                direction = 1 if error > 0.0 else -1
                if last_direction is not None and direction != last_direction:
                    self.motors.brake()
                    threading.Event().wait(0.12)

                self.motors.authorize()
                self.motors.drive(0.0, 0.0, rate * direction)
                last_direction = direction

                # Minimum usable PWM is too coarse for continuous correction
                # near zero. Pulse briefly, brake all four wheels, then
                # remeasure. This is the proven TurboPi convergence strategy.
                if abs_error <= 12.0:
                    threading.Event().wait(0.07)
                    self.motors.brake()
                    last_direction = None
                    final_pulses += 1
                    if final_pulses >= 4:
                        self.log.info(
                            "heading reset reached mechanical limit %.1f deg",
                            heading,
                        )
                        return
                    threading.Event().wait(0.12)
                else:
                    threading.Event().wait(0.04)
            raise RuntimeError("heading reset timed out")
        finally:
            self.motors.brake()
