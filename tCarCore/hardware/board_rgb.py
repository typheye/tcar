#!/usr/bin/env python3
try:
    from rpi_ws281x import PixelStrip, Color
except ImportError:
    PixelStrip = Color = None


class BoardRGB:
    def __init__(self): self.strip = None
    def start(self):
        if PixelStrip:
            self.strip = PixelStrip(2, 12, 800000, 10, False, 120, 0); self.strip.begin(); self.clear()
    def set(self, index, red, green, blue):
        if self.strip: self.strip.setPixelColor(index, Color(red, green, blue)); self.strip.show()
    def clear(self):
        if self.strip:
            for index in range(2): self.strip.setPixelColor(index, Color(0, 0, 0))
            self.strip.show()
    def stop(self): self.clear()

