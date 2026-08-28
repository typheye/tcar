#!/usr/bin/env python3
"""Single-owner latest-frame camera capture."""

import threading
import time

import cv2


class VideoDevice:
    def __init__(self, device=-1, resolution=(640, 480), fps=30):
        self.device, self.resolution, self.fps = device, resolution, fps
        self.capture = None; self.frame = None; self.sequence = 0
        self.lock = threading.Lock(); self.running = False; self.thread = None
    def start(self):
        self.capture = cv2.VideoCapture(self.device)
        self.capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0]); self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1]); self.capture.set(cv2.CAP_PROP_FPS, self.fps)
        self.running = True; self.thread = threading.Thread(target=self._run, name="video-device", daemon=True); self.thread.start()
    def _run(self):
        while self.running:
            ok, frame = self.capture.read()
            if ok:
                with self.lock: self.frame = frame; self.sequence += 1
            else: time.sleep(0.02)
    def latest(self):
        with self.lock: return self.sequence, self.frame
    def stop(self):
        self.running = False
        if self.thread: self.thread.join(timeout=1.0)
        if self.capture: self.capture.release()

