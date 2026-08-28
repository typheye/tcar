#!/usr/bin/env python3
from hardware.i2c_bus import shared_i2c


class ASR:
    ADDRESS = 0x34
    RESULT = 0x64
    SPEAK = 0x6E

    def __init__(self, bus=shared_i2c): self.bus = bus
    def recognition(self): return self.bus.read_block(self.ADDRESS, self.RESULT, 1)[0]
    def speak(self, category, phrase_id): self.bus.write_block(self.ADDRESS, self.SPEAK, [category, phrase_id])

