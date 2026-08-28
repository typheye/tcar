#!/usr/bin/env python3
"""Ordered startup and reverse-order shutdown for all core components."""

import signal
import threading

from server.core.logd_manager import get_logger


class Lifecycle:
    def __init__(self):
        self.log = get_logger("Lifecycle")
        self.stop_event = threading.Event()
        self.components = []
        self.started_components = []
        self._stopped = False

    def add(self, name, component):
        self.components.append((name, component))
        return component

    def install_signal_handlers(self):
        signal.signal(signal.SIGINT, self._signal)
        signal.signal(signal.SIGTERM, self._signal)

    def _signal(self, signum, _frame):
        self.log.info("received signal %s", signum)
        self.stop_event.set()

    def start(self):
        for name, component in self.components:
            starter = getattr(component, "start", None)
            if starter:
                self.log.info("starting %s", name)
                starter()
            self.started_components.append((name, component))

    def wait(self):
        self.stop_event.wait()

    def stop(self):
        if self._stopped:
            return
        self._stopped = True
        for name, component in reversed(self.started_components):
            stopper = getattr(component, "stop", None) or getattr(component, "close", None)
            if not stopper:
                continue
            try:
                self.log.info("stopping %s", name)
                stopper()
            except Exception:
                self.log.exception("failed to stop %s", name)
        self.started_components.clear()
