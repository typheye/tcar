#!/usr/bin/env python3
"""Compact JSON-RPC server for trusted in-car Ethernet clients."""

import json
import os
import socket
import threading
import time
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
        if method == "Heartbeat": return [True, (), "Heartbeat"]
        if method == "LoadFunc": return [True, (), "LoadFunc"]
        if method == "GetBatteryVoltage": return [True, self.telemetry.snapshot()["battery_voltage"] * 1000.0, "GetBatteryVoltage"]
        if method == "GetSonarDistance": return [True, self.telemetry.snapshot()["distance_mm"], "GetSonarDistance"]
        if method == "SetPWMServo":
            duration, count, *values = params
            for index in range(int(count)): self.servos.set_pulse(int(values[index*2]), int(values[index*2+1]), int(duration))
            return [True, (), "SetPWMServo"]
        if method == "SetServoVelocity":
            servo_id, speed = params
            self.servos.set_velocity(int(servo_id), float(speed))
            return [True, self.servos.get_pulse(int(servo_id)), "SetServoVelocity"]
        if method == "ResetPWMServo":
            self.servos.reset()
            return [True, (), "ResetPWMServo"]
        if method == "GetPWMServoPosition":
            servo_id = int(params[0])
            return [True, self.servos.get_pulse(servo_id), "GetPWMServoPosition"]
        if method == "SetBrushMotor":
            commands = [0, 0, 0, 0]
            for index in range(0, len(params), 2): commands[int(params[index])-1] = int(params[index+1])
            self.motors.authorize(); self.motors.set_all(commands)
            return [True, (), "SetBrushMotor"]
        if method == "EmergencyStop":
            self.motors.brake(); return [True, (), "EmergencyStop"]
        if method == "GetSystemInfo":
            return [True, self._system_info(), "GetSystemInfo"]
        if method == "HardwareSelfTest":
            return [True, self._hardware_self_test(), "HardwareSelfTest"]
        raise ValueError(f"unknown RPC method: {method}")

    @staticmethod
    def _system_info():
        addresses = []
        preferred = None
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.connect(("192.168.66.1", 80)); preferred = probe.getsockname()[0]; probe.close()
        except OSError: pass
        try:
            import psutil
            addresses = [item.address for values in psutil.net_if_addrs().values()
                         for item in values if item.family == socket.AF_INET
                         and not item.address.startswith("127.")]
        except ImportError:
            if preferred: addresses = [preferred]
        temperature = 0.0
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r", encoding="utf-8") as handle:
                temperature = float(handle.read().strip()) / 1000.0
        except (OSError, ValueError): pass
        return {"ip": preferred or (addresses[0] if addresses else "unknown"),
                "addresses": addresses, "temperature_c": temperature,
                "hostname": socket.gethostname()}

    def _hardware_self_test(self):
        report = {"battery": False, "sonar": False, "servos": False,
                  "motors": False, "timestamp": time.time()}
        item = self.telemetry.snapshot()
        report["battery"] = item["battery_voltage"] > 5.0
        report["sonar"] = 30.0 <= item["distance_mm"] <= 5000.0
        centers = {servo_id: self.servos.factory[servo_id] for servo_id in (1, 2)}
        try:
            # Match the original self-test, but keep the movements smaller and
            # serialize them through tCarCore's sole servo owner.
            for servo_id in (1, 2):
                self.servos.set_pulse(servo_id, centers[servo_id] + 180, 250); time.sleep(.28)
                self.servos.set_pulse(servo_id, centers[servo_id] - 180, 250); time.sleep(.28)
                self.servos.set_pulse(servo_id, centers[servo_id], 250); time.sleep(.30)
            report["servos"] = True
            for motor_id in range(4):
                speeds = [0, 0, 0, 0]; speeds[motor_id] = 30
                self.motors.authorize(); self.motors.set_all(speeds); time.sleep(.25)
                self.motors.brake(); time.sleep(.12)
            report["motors"] = True
        finally:
            self.motors.brake(); self.servos.reset()
        report["ok"] = all(report[key] for key in ("battery", "sonar", "servos", "motors"))
        return report
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
