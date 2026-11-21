"""Versioned device settings, owned and persisted exclusively by Core host."""

import copy
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import secrets
import tempfile
import threading


def password_record(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200000)
    return {"salt": salt, "digest": digest.hex()}


class DeviceConfig:
    def __init__(self, servos, path=None):
        self.path = Path(path or os.environ.get(
            "TCAR_DEVICE_CONFIG", "/var/lib/tcar-core/device.json"
        ))
        self.lock = threading.RLock()
        self.data = {
            "schema_version": 1, "revision": 0, "initialized": False,
            "device_name": "tCar",
            "servos": {str(i): {"min_us": servos.limits[i][0],
                                "default_us": servos.factory[i],
                                "max_us": servos.limits[i][1]} for i in (1, 2)},
            "battery": {"empty_voltage": 6.4, "full_voltage": 8.4,
                        "full_runtime_minutes": 129.5},
            "account": {"username": "tcar", "password_hash": password_record("admin123")},
        }
        if self.path.exists():
            with self.path.open(encoding="utf-8") as handle:
                saved = json.load(handle)
            if saved.get("schema_version") != 1:
                raise ValueError("unsupported device configuration version")
            self.validate(saved)
            secret = saved["account"]["password_hash"]
            if len(bytes.fromhex(secret["salt"])) != 16 or len(bytes.fromhex(secret["digest"])) != 32:
                raise ValueError("invalid password hash")
            if type(saved["revision"]) is not int or saved["revision"] < 0:
                raise ValueError("invalid device configuration revision")
            self.data = saved

    @staticmethod
    def validate(data):
        name = data["device_name"]
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 64:
            raise ValueError("device name must contain 1..64 characters")
        if type(data["initialized"]) is not bool:
            raise ValueError("initialized must be a boolean")
        for i in ("1", "2"):
            servo = data["servos"][i]
            low, center, high = (servo[k] for k in ("min_us", "default_us", "max_us"))
            if any(type(v) is not int for v in (low, center, high)) or not 500 <= low <= center <= high <= 2500 or low == high:
                raise ValueError(f"servo {i}: require 500 <= min <= default <= max <= 2500, min < max")
        battery = data["battery"]
        values = [battery[k] for k in ("empty_voltage", "full_voltage", "full_runtime_minutes")]
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError("battery values must be finite numbers")
        empty, full, runtime = values
        if not 5.8 <= empty < full <= 8.8 or full - empty < 0.2 - 1e-9:
            raise ValueError("2S battery requires 5.8 <= empty < full <= 8.8 V, at least 0.2 V apart")
        if not 1 <= runtime <= 10080:
            raise ValueError("full runtime must be 1..10080 minutes")
        username = data["account"]["username"]
        if not isinstance(username, str) or not 1 <= len(username.strip()) <= 64:
            raise ValueError("username must contain 1..64 characters")

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.data)

    def public(self):
        data = self.snapshot()
        data["account"] = {"username": data["account"]["username"]}
        return data

    def authenticate(self, username, password):
        account = self.snapshot()["account"]
        secret = account["password_hash"]
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(secret["salt"]), 200000).hex()
        return hmac.compare_digest(username.encode(), account["username"].encode()) and hmac.compare_digest(digest, secret["digest"])

    def prepare(self, request):
        data = self.snapshot()
        if type(request.get("revision")) is not int or request["revision"] != data["revision"]:
            raise RuntimeError("configuration changed; reload before saving")
        for key in ("device_name", "initialized", "servos", "battery"):
            data[key] = copy.deepcopy(request[key])
        account = request["account"]
        data["account"]["username"] = account["username"]
        password = account.get("password", "")
        if not isinstance(password, str) or len(password) > 256 or (password and len(password) < 8):
            raise ValueError("new password must contain 8..256 characters")
        if password:
            data["account"]["password_hash"] = password_record(password)
        data["revision"] += 1
        self.validate(data)
        data["device_name"] = data["device_name"].strip()
        data["account"]["username"] = data["account"]["username"].strip()
        return data

    def commit(self, data):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, temporary = tempfile.mkstemp(prefix=".device-", dir=self.path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            self.data = copy.deepcopy(data)
