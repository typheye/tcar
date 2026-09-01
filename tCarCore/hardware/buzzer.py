#!/usr/bin/env python3
import threading
import time

try: import RPi.GPIO as GPIO
except ImportError: GPIO = None


class Buzzer:
    # Physical pin 31 is BCM GPIO6. tCar Core uses BCM numbering globally so
    # board keys and the buzzer can safely coexist in one process.
    PIN = 6
    def __init__(self):
        self.lock = threading.RLock()
        self._muted = False
    def start(self):
        if GPIO:
            GPIO.setwarnings(False)
            if GPIO.getmode() is None:
                GPIO.setmode(GPIO.BCM)
            elif GPIO.getmode() != GPIO.BCM:
                raise RuntimeError("tCar Core GPIO mode must be BCM")
            GPIO.setup(self.PIN, GPIO.OUT)
            GPIO.output(self.PIN, 0)
    def stop(self): self._write(False)
    def _write(self, state):
        if GPIO: GPIO.output(self.PIN, 1 if state else 0)
    def on(self):
        with self.lock:
            if not self._muted: self._write(True)
    def off(self):
        self._write(False)
    @property
    def muted(self):
        with self.lock: return self._muted
    def pattern(self, durations, force=False, after=None):
        if self.muted and not force:
            return False
        def run():
            with self.lock:
                for state, duration in durations:
                    self._write(bool(state)); time.sleep(duration)
                self._write(False)
                if after: after()
        threading.Thread(target=run, name="buzzer-pattern", daemon=True).start()
        return True
    def switch_feedback(self, enabled):
        """Emit the common switch sound, bypassing mute state."""
        pattern = ([(1, .10)] if enabled
                   else [(1, .05), (0, .10), (1, .05)])
        return self.pattern(pattern, force=True)
    def toggle_mute(self):
        with self.lock:
            enabling = not self._muted
            if not enabling:
                self._muted = False
        if enabling:
            self.pattern([(1, .10)], force=True,
                         after=lambda: setattr(self, "_muted", True))
        else:
            self.switch_feedback(False)
        return enabling
