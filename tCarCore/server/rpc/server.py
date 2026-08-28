#!/usr/bin/env python3
"""Compact JSON-RPC server for trusted in-car Ethernet clients."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from server.core.logd_manager import get_logger


class RPCServer:
    def __init__(self, telemetry, motors, servos, sonar):
        self.telemetry, self.motors, self.servos, self.sonar = telemetry, motors, servos, sonar
        self.log = get_logger("RPC"); self.http = None; self.thread = None
    def start(self):
        self.http = ThreadingHTTPServer(("0.0.0.0", 9030), self._handler())
        self.thread = threading.Thread(target=self.http.serve_forever, name="rpc-http", daemon=True); self.thread.start(); self.log.info("JSON-RPC :9030 ready")
    def stop(self):
        if self.http: self.http.shutdown(); self.http.server_close()
        if self.thread: self.thread.join(timeout=1.0)
    def _call(self, method, params):
        if method == "Heartbeat": return True
        if method == "GetBatteryVoltage": return self.telemetry.snapshot()["battery_voltage"] * 1000.0
        if method == "GetSonarDistance": return self.telemetry.snapshot()["distance_mm"]
        if method == "SetPWMServo":
            duration, count, *values = params
            for index in range(int(count)): self.servos.set_pulse(int(values[index*2]), int(values[index*2+1]), int(duration))
            return True
        if method == "SetBrushMotor":
            commands = [0, 0, 0, 0]
            for index in range(0, len(params), 2): commands[int(params[index])-1] = int(params[index+1])
            self.motors.authorize(); return self.motors.set_all(commands)
        if method == "EmergencyStop": return self.motors.brake()
        raise ValueError(f"unknown RPC method: {method}")
    def _handler(self):
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args): pass
            def do_POST(self):
                try:
                    request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                    result = owner._call(request.get("method"), request.get("params", [])); response = {"jsonrpc": "2.0", "result": result, "id": request.get("id")}
                except Exception as error: response = {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(error)}, "id": None}
                payload = json.dumps(response).encode(); self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)
        return Handler

