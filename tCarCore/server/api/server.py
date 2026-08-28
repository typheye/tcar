#!/usr/bin/env python3
"""Authenticated external API, legacy UDP telemetry and latest-frame MJPEG."""

import base64
import hmac
import json
import math
import socket
import struct
import threading
import time
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

from server.core.logd_manager import get_logger


class APIServer:
    def __init__(self, telemetry, video, control, username="tcar", password="admin123"):
        self.telemetry, self.video, self.control = telemetry, video, control
        self.username, self.password = username, password
        self.log = get_logger("API")
        self.running = False; self.http = None; self.threads = []
        self.paused = False

    def toggle_paused(self):
        self.paused = not self.paused
        return self.paused

    def start(self):
        self.running = True
        self.http = ThreadingHTTPServer(("0.0.0.0", 8080), self._handler())
        self.threads = [threading.Thread(target=self.http.serve_forever, name="api-http", daemon=True),
                        threading.Thread(target=self._udp, name="api-udp", daemon=True)]
        for thread in self.threads: thread.start()
        self.log.info("HTTP :8080 and telemetry UDP :8888 ready")

    def stop(self):
        self.running = False
        if self.http: self.http.shutdown(); self.http.server_close()
        for thread in self.threads: thread.join(timeout=1.0)

    def _handler(self):
        owner = self
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def log_message(self, *_args): pass
            def _json(self, status, value):
                payload = json.dumps(value, separators=(",", ":")).encode()
                self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(payload))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(payload)
            def do_POST(self):
                if self.path != "/api/login": self.send_error(404); return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 4096: raise ValueError("invalid request size")
                    request = json.loads(self.rfile.read(length))
                    username, password = str(request.get("username", "")), str(request.get("password", ""))
                except (ValueError, TypeError, json.JSONDecodeError): self._json(400, {"status": 0, "error": "invalid_request"}); return
                if not (hmac.compare_digest(username, owner.username) and hmac.compare_digest(password, owner.password)):
                    self._json(401, {"status": 0, "error": "invalid_credentials"}); return
                self._json(200, {"status": 1})
            def do_GET(self):
                if owner.paused:
                    self.send_error(503, "Desktop services paused"); return
                if self.path == "/api/v1/telemetry":
                    payload = json.dumps(owner.telemetry.snapshot(), separators=(",", ":"), allow_nan=False).encode()
                    self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload); return
                if self.path.startswith("/?action=snapshot") or self.path == "/snapshot.jpg":
                    _, frame = owner.video.latest()
                    if frame is None: self.send_error(503); return
                    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
                    payload = encoded.tobytes() if ok else b""
                    self.send_response(200); self.send_header("Content-Type", "image/jpeg"); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload); return
                if self.path.startswith("/?action=stream") or self.path == "/stream.mjpg":
                    self.send_response(200); self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame"); self.end_headers()
                    sequence = -1
                    try:
                        while owner.running and not owner.paused:
                            current, frame = owner.video.latest()
                            if frame is None or current == sequence: time.sleep(.005); continue
                            sequence = current; ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 78])
                            if not ok: continue
                            payload = encoded.tobytes(); self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(payload)).encode() + b"\r\n\r\n" + payload + b"\r\n"); self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError): pass
                    return
                self.send_error(404)
        return Handler

    def _udp(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); sock.bind(("0.0.0.0", 8888)); sock.settimeout(.2)
        try:
            while self.running:
                try: data, address = sock.recvfrom(1024)
                except socket.timeout: continue
                if self.paused and address[0] not in ("127.0.0.1", "::1"):
                    continue
                if data == b"calibration_status":
                    sock.sendto(self.control.status.encode(), address); continue
                if data == b"battery_status":
                    item = self.telemetry.snapshot()
                    sock.sendto(f"{item['battery_voltage']:.2f},{item['battery_percent']:.1f}".encode(), address); continue
                if data == b"performance_status":
                    sock.sendto(json.dumps(self._performance(), separators=(",", ":")).encode(), address); continue
                if data == b"calibrate_inertial":
                    self.control._background("inertial calibration", self.control._calibrate_inertial)
                    sock.sendto(f"started:{self.control.status}".encode(), address); continue
                if data == b"calibrate_magnetometer":
                    self.control._background("magnetometer calibration", self.control._calibrate_magnetic)
                    sock.sendto(f"started:{self.control.status}".encode(), address); continue
                if data != b"get_data": continue
                item = self.telemetry.snapshot(); q = item["quaternion"]; a = item["accel"]; g = item["gyro"]
                mag = item["mag_heading"] if item["mag_heading"] is not None else float("nan")
                packet = struct.pack("!17f", item["pitch"], item["roll"], item["yaw"], *q, *a, *g,
                                     item["distance_mm"], mag, item["heading"], item["camera_pan"])
                sock.sendto(packet, address)
        finally: sock.close()

    @staticmethod
    def _performance():
        load = os.getloadavg()[0] / max(1, os.cpu_count() or 1) * 100.0
        memory = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                key, value = line.split(":", 1); memory[key] = int(value.split()[0])
        total = max(1, memory.get("MemTotal", 1)); available = memory.get("MemAvailable", 0)
        with open("/proc/uptime", "r", encoding="utf-8") as handle: uptime = float(handle.read().split()[0])
        network = 0
        with open("/proc/net/dev", "r", encoding="utf-8") as handle:
            for line in handle.readlines()[2:]:
                name, values = line.split(":", 1)
                if name.strip() != "lo":
                    fields = values.split(); network += int(fields[0]) + int(fields[8])
        return {"uptime": uptime, "cpu": max(0.0, min(100.0, load)),
                "cores": os.cpu_count() or 1, "memory": (total - available) / total * 100.0,
                "network_bytes": network, "hostname": socket.gethostname(),
                "platform": os.uname().release, "python": os.sys.version.split()[0]}
