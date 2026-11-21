"""Apply device configuration and lease exclusive, slow gimbal calibration."""

import secrets
import threading
import time

from server.core.logd_manager import get_logger


class DeviceSetup:
    LEASE_SECONDS = 5.0

    def __init__(self, config, control, battery):
        self.config, self.control, self.battery = config, control, battery
        self.servos = control.servos
        self.lock = threading.RLock()
        self.session = None
        self.expires = 0.0
        self.last_move = {}
        self.stopped = threading.Event()
        self.thread = None
        self.log = get_logger("DeviceSetup")
        self.apply(config.snapshot())

    def apply(self, data):
        self.servos.apply_config(data["servos"])
        self.battery.apply_config(data["battery"])

    def start(self):
        self.thread = threading.Thread(target=self._watch, name="setup-watchdog", daemon=True)
        self.thread.start()

    def stop(self):
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=1.0)
        with self.lock:
            self._end()

    def _watch(self):
        while not self.stopped.wait(0.25):
            with self.lock:
                if self.session and (time.monotonic() >= self.expires or self.control.operation_cancel.is_set()):
                    try:
                        self._end()
                    except RuntimeError:
                        pass  # _end logs the hardware failure and releases ownership.

    def _check(self, session):
        if not self.session or session != self.session:
            raise RuntimeError("calibration session expired; start calibration again")
        if time.monotonic() >= self.expires or self.control.operation_cancel.is_set():
            self._end()
            raise RuntimeError("calibration expired or cancelled by R2")
        self.expires = time.monotonic() + self.LEASE_SECONDS

    def begin(self):
        with self.lock:
            if self.session or not self.control.begin_exclusive_operation("gimbal calibration"):
                raise RuntimeError("vehicle is busy")
            try:
                self.servos.begin_calibration()
            except Exception:
                self.control.end_exclusive_operation()
                raise
            self.session = secrets.token_urlsafe(24)
            self.expires = time.monotonic() + self.LEASE_SECONDS
            self.last_move = {1: time.monotonic(), 2: time.monotonic()}
            return {"session": self.session, "positions": self.positions()}

    def positions(self):
        return {str(i): self.servos.get_pulse(i) for i in (1, 2)}

    def preview(self, request):
        with self.lock:
            self._check(request.get("session"))
            servo_id = request.get("servo_id")
            if servo_id is not None:
                pulse = request.get("pulse_us")
                if type(servo_id) is not int or servo_id not in (1, 2) or type(pulse) is not int or not 500 <= pulse <= 2500:
                    raise ValueError("servo 1/2 requires an integer pulse from 500 to 2500 us")
                now = time.monotonic()
                step = min(40, int(400 * (now - self.last_move[servo_id])))
                if step > 0:
                    current = self.servos.get_pulse(servo_id)
                    target = max(current - step, min(current + step, pulse))
                    self.servos.calibration_pulse(servo_id, target)
                    self.last_move[servo_id] = now
            return {"positions": self.positions()}

    def end(self, session):
        with self.lock:
            if self.session:
                self._check(session)
                self._end()
            return {"positions": self.positions()}

    def _end(self):
        if not self.session:
            return
        try:
            self.servos.end_calibration()
        except Exception as error:
            self.log.exception("failed to restore gimbal after calibration")
            raise RuntimeError("gimbal restore failed; check hardware and reload configuration") from error
        finally:
            self.session = None
            self.control.end_exclusive_operation()

    def save(self, request):
        with self.lock:
            if self.session:
                self._check(request.get("session"))
            elif self.control.busy or self.servos.is_resetting():
                raise RuntimeError("vehicle is busy; retry after operation completes")
            data = self.config.prepare(request)
            # Applying settings is serialized with calibration and motor policy.
            with self.control.lock:
                previous = self.config.snapshot()
                if not self.session:
                    self.begin()
                try:
                    self.apply(data)
                    self.config.commit(data)
                except Exception:
                    self.apply(previous)
                    raise
                finally:
                    self._end()
                return self.config.public()
