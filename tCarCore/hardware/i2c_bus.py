#!/usr/bin/env python3
"""One serialized I2C gateway shared by every tCar Core driver."""

import threading
import time
from contextlib import contextmanager

try:
    from smbus2 import SMBus, i2c_msg
except ImportError:  # permits development-host imports and static checks
    SMBus = None
    i2c_msg = None


class I2CBusManager:
    _instances = {}
    _instances_lock = threading.Lock()

    def __new__(cls, bus_number=1):
        with cls._instances_lock:
            instance = cls._instances.get(bus_number)
            if instance is None:
                instance = super().__new__(cls)
                cls._instances[bus_number] = instance
            return instance

    def __init__(self, bus_number=1):
        if getattr(self, "_initialized", False):
            return
        self.bus_number = int(bus_number)
        self.lock = threading.RLock()
        self._bus = None
        self._suspend_reasons = set()
        self._initialized = True

    def open(self):
        with self.lock:
            if self._bus is None:
                if SMBus is None:
                    raise RuntimeError("smbus2 is not installed")
                self._bus = SMBus(self.bus_number)
            return self

    def close(self):
        with self.lock:
            if self._bus is not None:
                self._bus.close()
                self._bus = None

    @property
    def suspended(self):
        with self.lock:
            return bool(self._suspend_reasons)

    def suspend(self, reason):
        with self.lock:
            self._suspend_reasons.add(str(reason))

    def resume(self, reason):
        with self.lock:
            self._suspend_reasons.discard(str(reason))

    def _require_bus(self):
        if self._bus is None:
            self.open()
        return self._bus

    @contextmanager
    def transaction(self, allow_suspended=False):
        with self.lock:
            if self._suspend_reasons and not allow_suspended:
                raise RuntimeError(
                    "I2C bus suspended: " + ", ".join(sorted(self._suspend_reasons))
                )
            yield self._require_bus()

    def retry(self, operation, attempts=2, delay=0.01,
              allow_suspended=False):
        last_error = None
        for attempt in range(max(1, int(attempts))):
            try:
                with self.transaction(allow_suspended=allow_suspended) as bus:
                    return operation(bus)
            except (OSError, IOError) as error:
                last_error = error
                if attempt + 1 < attempts:
                    time.sleep(delay)
        raise last_error

    def write_byte_data(self, address, register, value, **kwargs):
        return self.retry(
            lambda bus: bus.write_byte_data(address, register, value), **kwargs
        )

    def read_byte_data(self, address, register, **kwargs):
        return self.retry(
            lambda bus: bus.read_byte_data(address, register), **kwargs
        )

    def read_block(self, address, register, length, **kwargs):
        return self.retry(
            lambda bus: bus.read_i2c_block_data(address, register, length),
            **kwargs,
        )

    def write_block(self, address, register, values, **kwargs):
        return self.retry(
            lambda bus: bus.write_i2c_block_data(address, register, list(values)),
            **kwargs,
        )

    def write_then_read(self, address, write_data, read_length, **kwargs):
        def operation(bus):
            write = i2c_msg.write(address, list(write_data))
            bus.i2c_rdwr(write)
            read = i2c_msg.read(address, int(read_length))
            bus.i2c_rdwr(read)
            return bytes(list(read))
        return self.retry(operation, **kwargs)

    def write(self, address, data, **kwargs):
        def operation(bus):
            bus.i2c_rdwr(i2c_msg.write(address, list(data)))
        return self.retry(operation, **kwargs)


shared_i2c = I2CBusManager(1)
