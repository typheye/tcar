#!/usr/bin/env python3
"""Compare tCar Core snapshots with the legacy TurboPi UDP packet."""

import json
import socket
import struct
import time


class SensorComparator:
    def __init__(self, telemetry, legacy=("127.0.0.1", 8888), output=None):
        self.telemetry = telemetry
        self.legacy = legacy
        self.output = output

    def sample(self, count=100, interval=0.05):
        records = []
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.5)
        try:
            for _ in range(count):
                sock.sendto(b"get_data", self.legacy)
                packet, _ = sock.recvfrom(1024)
                values = struct.unpack("!17f", packet)
                core = self.telemetry.snapshot()
                records.append({
                    "time": time.time(),
                    "legacy": {"pitch": values[0], "roll": values[1],
                               "yaw": values[2], "mag": values[14]},
                    "core": {"pitch": core["pitch"], "roll": core["roll"],
                             "yaw": core["yaw"], "mag": core["mag_heading"]},
                })
                time.sleep(interval)
        finally:
            sock.close()
        if self.output:
            with open(self.output, "w", encoding="utf-8") as handle:
                json.dump(records, handle, indent=2, allow_nan=True)
        return records

