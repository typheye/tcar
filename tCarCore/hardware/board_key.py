#!/usr/bin/env python3
import subprocess
import threading
import time
try: import RPi.GPIO as GPIO
except ImportError: GPIO = None


class BoardKeys:
    PINS = (13, 23)
    LONG_PRESS_SECONDS = 3.0

    def __init__(self, buzzer=None):
        self.buzzer = buzzer
        self.running = False
        self.thread = None

    def start(self):
        if GPIO:
            GPIO.setwarnings(False)
            if GPIO.getmode() is None:
                GPIO.setmode(GPIO.BCM)
            elif GPIO.getmode() != GPIO.BCM:
                raise RuntimeError("tCar Core GPIO mode must be BCM")
            for pin in self.PINS: GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            self.running = True
            self.thread = threading.Thread(target=self._run, name="board-keys", daemon=True)
            self.thread.start()
    def pressed(self, index): return bool(GPIO and GPIO.input(self.PINS[index]) == GPIO.LOW)
    def stop(self):
        self.running = False
        if self.thread: self.thread.join(timeout=1.0)

    def _run(self):
        pressed_at = [None, None]
        fired = [False, False]
        while self.running and GPIO:
            now = time.monotonic()
            for index, pin in enumerate(self.PINS):
                pressed = GPIO.input(pin) == GPIO.LOW
                if pressed:
                    if pressed_at[index] is None:
                        pressed_at[index] = now
                        fired[index] = False
                    elif not fired[index] and now - pressed_at[index] >= self.LONG_PRESS_SECONDS:
                        fired[index] = True
                        if index == 0:
                            self._reset_wifi()
                        else:
                            self._shutdown()
                else:
                    pressed_at[index] = None
                    fired[index] = False
            time.sleep(0.05)

    def _reset_wifi(self):
        """Reconfigure the native wpa_supplicant profile without old toolbox."""
        try:
            # Audible acknowledgement makes a long press distinguishable from
            # a missed button. The network restart itself remains synchronous.
            if self.buzzer:
                self.buzzer.pattern([(1, 0.12)])
            subprocess.run(
                ["/sbin/wpa_cli", "-i", "wlan0", "reconfigure"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=5, check=False,
            )
            subprocess.run(
                ["/bin/systemctl", "restart", "dhcpcd.service"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=8, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    @staticmethod
    def _shutdown():
        try:
            subprocess.run(["/bin/systemctl", "poweroff"], check=False)
        except OSError:
            pass
