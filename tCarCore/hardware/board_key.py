#!/usr/bin/env python3
try: import RPi.GPIO as GPIO
except ImportError: GPIO = None


class BoardKeys:
    PINS = (13, 23)
    def start(self):
        if GPIO:
            GPIO.setwarnings(False)
            if GPIO.getmode() is None:
                GPIO.setmode(GPIO.BCM)
            elif GPIO.getmode() != GPIO.BCM:
                raise RuntimeError("tCar Core GPIO mode must be BCM")
            for pin in self.PINS: GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    def pressed(self, index): return bool(GPIO and GPIO.input(self.PINS[index]) == GPIO.LOW)
    def stop(self): pass
