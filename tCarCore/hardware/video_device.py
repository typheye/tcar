#!/usr/bin/env python3
"""Single-owner latest-frame camera capture with safe V4L2 recovery."""

import os
import threading
import time

import cv2

from server.core.logd_manager import get_logger


class VideoDevice:
    def __init__(self, device=0, resolution=(640, 480), fps=30,
                 reopen_interval=1.0):
        self.device, self.resolution, self.fps = device, resolution, fps
        self.reopen_interval = float(reopen_interval)
        self.log = get_logger("Video")
        self.capture = None; self.frame = None; self.sequence = 0
        self.lock = threading.Lock(); self.open_lock = threading.Lock()
        self.running = False; self.thread = None
        self.last_open_attempt = 0.0; self.missing_logged = False

    def start(self):
        self.running = True
        self._open_capture()
        self.thread = threading.Thread(
            target=self._run, name="video-device", daemon=True
        )
        self.thread.start()

    def _open_capture(self):
        with self.open_lock:
            if self.capture is not None:
                return True
            now = time.monotonic()
            if now - self.last_open_attempt < self.reopen_interval:
                return False
            self.last_open_attempt = now
            node = f"/dev/video{int(self.device)}"
            if not os.path.exists(node):
                if not self.missing_logged:
                    self.missing_logged = True
                    self.log.warning(
                        "camera %s not present; waiting for hotplug", node
                    )
                return False
            if self.missing_logged:
                self.missing_logged = False
                self.log.info("camera %s detected", node)
            try:
                # Pin the V4L2 backend. Letting OpenCV auto-detect can fall
                # back to FFmpeg/GStreamer for an absent device and crash
                # inside libavformat on OpenCV 4.5.1.
                capture = cv2.VideoCapture(int(self.device), cv2.CAP_V4L2)
                if not capture.isOpened():
                    capture.release()
                    self.log.warning(
                        "camera %s unavailable; retrying", self.device
                    )
                    return False
                capture.set(
                    cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV")
                )
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
                capture.set(cv2.CAP_PROP_FPS, self.fps)
            except Exception:
                self.log.exception("camera open failed")
                return False
            self.capture = capture
            self.log.info("camera %s ready", self.device)
            return True

    def _run(self):
        while self.running:
            capture = self.capture
            if capture is None:
                self._open_capture()
                time.sleep(0.25)
                continue
            ok, frame = capture.read()
            if ok:
                with self.lock:
                    self.frame = frame
                    self.sequence += 1
                continue
            self.log.warning("camera %s read failed; reopening", self.device)
            with self.open_lock:
                if self.capture is capture:
                    self.capture = None
                    capture.release()
            time.sleep(0.5)

    def latest(self):
        with self.lock:
            return self.sequence, self.frame

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        with self.open_lock:
            capture, self.capture = self.capture, None
        if capture:
            capture.release()
