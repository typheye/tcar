"""Hardware-free coverage for persistent setup, calibration and public APIs."""

from http.server import ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import stat
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tCarCore"))
from hardware.battery_monitor import BatteryMonitor
from hardware.servo import ServoController
from server.core.control import ControlService
from server.core.device_config import DeviceConfig
from server.core.device_setup import DeviceSetup
from server.rpc.server import RPCServer

# These tests never access a camera; permit running the HTTP settings tests
# on development hosts which lack the optional OpenCV video dependency.
if importlib.util.find_spec("cv2") is None:
    with patch.dict(sys.modules, {"cv2": types.ModuleType("cv2")}):
        from server.api.server import APIServer
else:
    from server.api.server import APIServer


class DeviceSetupTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state" / "device.json"
        ServoController._instance = None
        self.bus = Mock()
        self.servos = ServoController(bus=self.bus)
        self.battery = BatteryMonitor(bus=self.bus)
        self.control = ControlService(Mock(), self.servos, Mock(), Mock(), Mock(), Mock())
        self.config = DeviceConfig(self.servos, self.path)
        self.setup = DeviceSetup(self.config, self.control, self.battery)
        self.addCleanup(self.setup.stop)

    def candidate(self):
        data = self.config.public()
        data["device_name"] = "测试车"
        data["initialized"] = True
        data["servos"]["2"] = {"min_us": 700, "default_us": 1520, "max_us": 2250}
        data["battery"] = {"empty_voltage": 6.3, "full_voltage": 8.3, "full_runtime_minutes": 180}
        return data

    def test_save_restart_and_no_public_secrets(self):
        result = self.setup.save(self.candidate())
        self.assertEqual(result["revision"], 1)
        self.assertTrue(result["initialized"])
        self.assertEqual(self.servos.limits[2], (700, 2250))
        self.assertEqual(self.servos.factory[2], 1520)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        reloaded = DeviceConfig(self.servos, self.path)
        self.assertEqual(reloaded.public(), result)
        self.assertTrue(reloaded.authenticate("tcar", "admin123"))
        self.assertNotIn("password", json.dumps(result))
        self.assertNotIn("admin123", self.path.read_text())
        self.assertFalse(self.control.busy)

    def test_invalid_values_do_not_apply(self):
        for mutate in (
            lambda d: d["servos"]["2"].update(default_us=2600),
            lambda d: d["battery"].update(full_voltage=6.0),
            lambda d: d["battery"].update(full_runtime_minutes=float("nan")),
            lambda d: d.update(device_name=4),
            lambda d: d["account"].update(password="short"),
        ):
            data = self.candidate()
            mutate(data)
            with self.assertRaises(ValueError): self.setup.save(data)
            self.assertEqual(self.config.public()["revision"], 0)
            self.assertFalse(self.path.exists())

    def test_stale_revision_and_failed_disk_write(self):
        old_limits = dict(self.servos.limits)
        with patch.object(self.config, "commit", side_effect=OSError("disk full")):
            with self.assertRaises(OSError): self.setup.save(self.candidate())
        self.assertEqual(self.servos.limits, old_limits)
        self.assertEqual(self.battery.maximum_voltage, 8.4)
        self.assertFalse(self.control.busy)
        data = self.candidate()
        self.setup.save(data)
        with self.assertRaises(RuntimeError): self.setup.save(data)

    def test_calibration_exclusion_and_rate_limit(self):
        token = self.setup.begin()["session"]
        current = self.servos.get_pulse(2)
        self.setup.last_move[2] -= 1
        self.setup.preview({"session": token, "servo_id": 2, "pulse_us": 2500})
        self.assertEqual(self.servos.get_pulse(2), current + 40)
        with self.assertRaises(RuntimeError): self.servos.set_pulse(2, 1500)
        with self.assertRaises(RuntimeError): self.servos.set_velocity(2, 1)
        with self.assertRaises(RuntimeError): self.servos.reset()
        rpc = RPCServer(Mock(), self.control.motors, self.servos, Mock(), self.control)
        with self.assertRaises(RuntimeError): rpc._call("SetBrushMotor", [1, 50])
        with self.assertRaises(RuntimeError): self.setup.end("wrong-session")
        self.servos.calibration_pulse(2, 2400)
        self.setup.end(token)
        self.assertEqual(self.servos.get_pulse(2), self.servos.limits[2][1])
        self.assertFalse(self.control.busy)

    def test_save_calibration_and_updated_angle_zero(self):
        token = self.setup.begin()["session"]
        self.servos.calibration_pulse(2, 1520)
        data = self.candidate()
        data["session"] = token
        self.setup.save(data)
        self.assertAlmostEqual(self.servos.horizontal_angle(), 0)
        self.assertIsNone(self.setup.session)
        self.servos.set_pulse(2, 2500)
        self.assertEqual(self.servos.get_pulse(2), 2250)

    def test_watchdog_releases_without_http_traffic(self):
        self.setup.begin()
        self.setup.expires = time.monotonic() - 1
        self.setup.start()
        deadline = time.monotonic() + 1.5
        while self.setup.session and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertIsNone(self.setup.session)
        self.assertFalse(self.control.busy)
        self.assertFalse(self.servos.calibrating)

    def test_emergency_stop_cancels_calibration(self):
        token = self.setup.begin()["session"]
        rpc = RPCServer(Mock(), self.control.motors, self.servos, Mock(), self.control)
        rpc._call("EmergencyStop", [])
        with self.assertRaises(RuntimeError): self.setup.preview({"session": token})
        self.assertFalse(self.control.busy)

    def test_hardware_failure_is_reported_and_releases_control(self):
        token = self.setup.begin()["session"]
        self.bus.write.side_effect = OSError("I2C unavailable")
        with patch.object(self.setup.log, "exception"):
            with self.assertRaisesRegex(RuntimeError, "gimbal restore failed"):
                self.setup.end(token)
        self.assertFalse(self.control.busy)
        self.assertFalse(self.servos.calibrating)
        self.assertIsNone(self.setup.session)

    def test_battery_runtime_rpc_and_revision(self):
        self.setup.save(self.candidate())
        self.battery._accept(7.3)
        battery = self.battery.snapshot()
        self.assertAlmostEqual(battery["percent"], 50)
        self.assertAlmostEqual(battery["remaining_minutes"], 90)
        telemetry = Mock()
        telemetry.snapshot.return_value = {
            "battery_voltage": battery["voltage"], "battery_percent": battery["percent"],
            "battery_min_voltage": battery["minimum_voltage"], "battery_max_voltage": battery["maximum_voltage"],
            "battery_full_runtime_minutes": battery["full_runtime_minutes"],
            "battery_remaining_minutes": battery["remaining_minutes"],
        }
        rpc = RPCServer(telemetry, Mock(), self.servos, Mock(), self.control, self.config)
        result = rpc._call("GetBatteryStatus", [])[1]
        self.assertAlmostEqual(result["remaining_minutes"], 90)
        self.assertEqual(result["config_revision"], 1)
        self.assertEqual(rpc._call("GetDeviceConfig", [])[1], self.config.public())

    def test_password_change_invalidates_old_token(self):
        api = APIServer(Mock(), Mock(), self.control, setup=self.setup)
        token = api._issue_token()
        self.assertTrue(api._authorized("Bearer " + token))
        data = self.candidate()
        data["account"] = {"username": "车主", "password": "new-secret-password"}
        self.setup.save(data)
        self.assertFalse(api._authorized("Bearer " + token))
        self.assertFalse(api._authenticate("tcar", "admin123"))
        self.assertTrue(api._authenticate("车主", "new-secret-password"))

    def test_http_auth_save_and_validation(self):
        api = APIServer(Mock(), Mock(), self.control, setup=self.setup)
        server = ThreadingHTTPServer(("127.0.0.1", 0), api._handler())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"

        def request(path, body=None, token=None):
            headers = {"Content-Type": "application/json"}
            if token: headers["Authorization"] = "Bearer " + token
            req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
            with urllib.request.urlopen(req, timeout=2) as response:
                return json.load(response)

        with self.assertRaises(urllib.error.HTTPError) as caught:
            request("/api/v1/setup/config")
        self.assertEqual(caught.exception.code, 401)
        caught.exception.close()
        token = request("/api/login", {"username": "tcar", "password": "admin123"})["token"]
        self.assertEqual(request("/api/v1/setup/config", token=token), self.config.public())
        saved = request("/api/v1/setup/config", self.candidate(), token)
        self.assertEqual(saved["revision"], 1)
        stale = self.candidate()
        stale["revision"] = 0
        with self.assertRaises(urllib.error.HTTPError) as caught:
            request("/api/v1/setup/config", stale, token)
        self.assertEqual(caught.exception.code, 409)
        caught.exception.close()


if __name__ == "__main__":
    unittest.main()
