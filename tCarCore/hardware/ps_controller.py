#!/usr/bin/env python3
"""Pure PS controller input source; it never touches vehicle hardware."""

import os
import threading
import time

try: import pygame
except ImportError: pygame = None


BUTTONS = ("y", "b", "a", "x", "l1", "r1", "l2", "r2",
           "select", "start", "l3", "r3")


class PSController:
    def __init__(self, callback, poll_hz=50):
        self.callback = callback
        self.interval = 1.0 / poll_hz
        self.running = False; self.thread = None; self.joystick = None
        self.previous = None

    def start(self):
        if pygame is None: return
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        pygame.init(); pygame.joystick.init()
        self.running = True
        self.thread = threading.Thread(target=self._run, name="ps-controller", daemon=True); self.thread.start()

    def stop(self):
        self.running = False
        if self.thread: self.thread.join(timeout=1.0)
        if pygame: pygame.joystick.quit(); pygame.quit()

    def _connect(self):
        if pygame.joystick.get_count() < 1: return False
        self.joystick = pygame.joystick.Joystick(0); self.joystick.init(); return True

    def _run(self):
        while self.running:
            pygame.event.pump()
            if self.joystick is None and not self._connect(): time.sleep(1.0); continue
            try:
                state = {"axes": tuple(self.joystick.get_axis(i) for i in range(min(4, self.joystick.get_numaxes()))),
                         "buttons": {name: bool(self.joystick.get_button(i)) for i, name in enumerate(BUTTONS) if i < self.joystick.get_numbuttons()},
                         "hat": self.joystick.get_hat(0) if self.joystick.get_numhats() else (0, 0),
                         "timestamp": time.monotonic()}
                self.callback(state)
                self.previous = state
            except pygame.error: self.joystick = None
            time.sleep(self.interval)
