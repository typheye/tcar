#!/usr/bin/env python3
"""Discover and cache the current Core host address from the car router."""

import json
import threading
import time
from urllib.request import urlopen

ROUTER_STATUS_URL = "http://192.168.66.1/test"
_lock = threading.RLock()
_cached_ip = None
_cached_at = 0.0


def get_core_host(force=False, timeout=1.0):
    global _cached_ip, _cached_at
    now = time.monotonic()
    with _lock:
        if not force and _cached_ip and now - _cached_at < 10.0:
            return _cached_ip
        with urlopen(ROUTER_STATUS_URL, timeout=timeout) as response:
            payload = json.load(response)
        for device in payload.get("devices", []):
            if device.get("name") == "Core host" and device.get("status", True):
                address = str(device.get("ip", "")).strip()
                if address:
                    _cached_ip, _cached_at = address, now
                    return address
        raise RuntimeError("Core host is absent from the car router")


def core_url(port, path=""):
    return f"http://{get_core_host()}:{int(port)}{path}"

