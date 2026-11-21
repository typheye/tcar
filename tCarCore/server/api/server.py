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
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

from server.core.logd_manager import get_logger


class APIServer:
    def __init__(self, telemetry, video, control, username="tcar", password="admin123", setup=None):
        self.telemetry, self.video, self.control = telemetry, video, control
        self.username, self.password = username, password
        self.setup = setup
        self._tokens = {}
        self._token_lock = threading.Lock()
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

    def _authenticate(self, username, password):
        if self.setup:
            return self.setup.config.authenticate(username, password)
        return hmac.compare_digest(username.encode(), self.username.encode()) and hmac.compare_digest(password.encode(), self.password.encode())

    def _account_key(self):
        return self.setup.config.snapshot()["account"] if self.setup else (self.username, self.password)

    def _issue_token(self, account_key=None):
        token = secrets.token_urlsafe(32)
        with self._token_lock:
            now = time.monotonic()
            self._tokens = {k: v for k, v in self._tokens.items() if v[0] > now}
            if len(self._tokens) >= 64:
                self._tokens.pop(next(iter(self._tokens)))
            self._tokens[token] = (now + 3600, self._account_key() if account_key is None else account_key)
        return token

    def _authorized(self, header):
        if header.startswith("Bearer "):
            with self._token_lock:
                record = self._tokens.get(header[7:])
            return bool(record and record[0] > time.monotonic() and record[1] == self._account_key())
        return False

    def _handler(self):
        owner = self
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def log_message(self, *_args): pass
            def _json(self, status, value):
                payload = json.dumps(value, separators=(",", ":")).encode()
                self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(payload))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(payload)
            def _body(self):
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    self.close_connection = True
                    raise ValueError("invalid request size")
                value = json.loads(self.rfile.read(length))
                if not isinstance(value, dict): raise ValueError("expected JSON object")
                return value
            def _setup_authorized(self):
                if owner.setup is None:
                    self._json(503, {"error": "device setup unavailable"}); return False
                if not owner._authorized(self.headers.get("Authorization", "")):
                    self.close_connection = True
                    self._json(401, {"error": "authentication expired; reconnect"}); return False
                return True
            def do_POST(self):
                if self.path.startswith("/api/v1/setup/"):
                    if not self._setup_authorized(): return
                    try:
                        request = self._body()
                        actions = {
                            "/api/v1/setup/config": lambda: owner.setup.save(request),
                            "/api/v1/setup/begin": owner.setup.begin,
                            "/api/v1/setup/preview": lambda: owner.setup.preview(request),
                            "/api/v1/setup/end": lambda: owner.setup.end(request.get("session")),
                        }
                        action = actions.get(self.path)
                        if action is None:
                            self._json(404, {"error": "unknown setup operation"}); return
                        self._json(200, action())
                    except (ValueError, KeyError, TypeError) as error:
                        self._json(400, {"error": str(error)})
                    except RuntimeError as error:
                        self._json(409, {"error": str(error)})
                    except OSError:
                        self._json(503, {"error": "device I/O or configuration write failed"})
                    return
                if self.path != "/api/login": self.send_error(404); return
                try:
                    request = self._body()
                    username, password = str(request.get("username", "")), str(request.get("password", ""))
                except (ValueError, TypeError, json.JSONDecodeError): self._json(400, {"status": 0, "error": "invalid_request"}); return
                account_key = owner._account_key()
                if not owner._authenticate(username, password) or account_key != owner._account_key():
                    self._json(401, {"status": 0, "error": "invalid_credentials"}); return
                self._json(200, {"status": 1, "token": owner._issue_token(account_key)})
            def do_GET(self):
                if self.path == "/api/v1/setup/config":
                    if self._setup_authorized(): self._json(200, owner.setup.config.public())
                    return
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
                    sock.sendto(
                        (
                            f"{item['battery_voltage']:.3f},"
                            f"{item['battery_min_voltage']:.2f},"
                            f"{item['battery_max_voltage']:.2f},"
                            f"{item['battery_percent']:.1f}"
                        ).encode(), address,
                    ); continue
                if data == b"performance_status":
                    sock.sendto(json.dumps(self._performance(), separators=(",", ":")).encode(), address); continue
                if data == b"calibrate_inertial":
                    self.control._background("inertial calibration", self.control._calibrate_inertial)
                    sock.sendto(f"started:{self.control.status}".encode(), address); continue
                if data == b"calibrate_magnetometer":
                    self.control._background("magnetometer calibration", self.control._calibrate_magnetic)
                    sock.sendto(f"started:{self.control.status}".encode(), address); continue
                if data.startswith(b"trajectory_enable:"):
                    self.control.mpu.set_trajectory_enabled(data.endswith(b"1"))
                    sock.sendto(b"ok", address); continue
                if data == b"trajectory_reset":
                    self.control.mpu.reset_trajectory(); sock.sendto(b"ok", address); continue
                if data == b"sensor_sample":
                    sock.sendto(
                        json.dumps(
                            self.telemetry.sensor_sample(), separators=(",", ":")
                        ).encode(), address,
                    ); continue
                if data != b"get_data": continue
                item = self.telemetry.snapshot(); q = item["quaternion"]; a = item["accel"]; g = item["gyro"]
                mag = item["mag_heading"] if item["mag_heading"] is not None else float("nan")
                packet = struct.pack("!25f", item["pitch"], item["roll"], item["yaw"], *q, *a, *g,
                                     item["distance_mm"], mag, item["heading"], item["camera_pan"],
                                     float(item["infrared_mask"]), *item["position_mm"],
                                     float(item["trajectory_epoch"]), item["camera_heading"],
                                     1.0 if item["heading_absolute"] else 0.0,
                                     1.0 if item["trajectory_enabled"] else 0.0)
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
