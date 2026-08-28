#!/usr/bin/env python3
import threading
import time

try: import RPi.GPIO as GPIO
except ImportError: GPIO = None


class Buzzer:
    # Physical pin 31 is BCM GPIO6. tCar Core uses BCM numbering globally so
    # board keys and the buzzer can safely coexist in one process.
    PIN = 6
    def __init__(self): self.lock = threading.RLock()
    def start(self):
        if GPIO:
            GPIO.setwarnings(False)
            if GPIO.getmode() is None:
                GPIO.setmode(GPIO.BCM)
            elif GPIO.getmode() != GPIO.BCM:
                raise RuntimeError("tCar Core GPIO mode must be BCM")
            GPIO.setup(self.PIN, GPIO.OUT)
            GPIO.output(self.PIN, 0)
    def stop(self): self.off()
    def on(self):
        if GPIO: GPIO.output(self.PIN, 1)
    def off(self):
        if GPIO: GPIO.output(self.PIN, 0)
    def pattern(self, durations):
        def run():
            with self.lock:
                for state, duration in durations:
                    self.on() if state else self.off(); time.sleep(duration)
                self.off()
        threading.Thread(target=run, name="buzzer-pattern", daemon=True).start()
