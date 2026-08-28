#!/usr/bin/env python3
from hardware.i2c_bus import shared_i2c


class FourInfrared:
    def __init__(self, bus=shared_i2c, address=0x78):
        self.bus, self.address = bus, address

    def read(self):
        value = self.bus.read_byte_data(self.address, 0x01)
        return tuple(bool(value & mask) for mask in (1, 2, 4, 8))

