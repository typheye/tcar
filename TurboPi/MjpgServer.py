#!/usr/bin/python

'''
    Author: Igor Maculan - n3wtron@gmail.com
    A Simple mjpg stream http server
'''

import sys

if sys.version_info.major == 2:
    print('Please run this program with python3!')
    sys.exit(0)

import cv2
import time
import queue
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer,ThreadingHTTPServer
from socketserver import ThreadingMixIn
from io import StringIO, BytesIO


img_show = None
jpg_show = None
frame_lock = threading.Lock()
quality = (int(cv2.IMWRITE_JPEG_QUALITY), 78)


def _process_camera_frame(frame):
    """Neutralize the camera's magenta cast without crushing highlights."""
    # Gray-world balance is intentionally limited so colored scenes stay
    # colored.  It mainly corrects the strong red/magenta bias seen on white.
    small = cv2.resize(frame, (160, 120), interpolation=cv2.INTER_AREA)
    means = small.reshape(-1, 3).mean(axis=0)
    target = max(1.0, float(means.mean()))
    gains = [max(0.88, min(1.12, target / max(1.0, float(v)))) for v in means]
    balanced = cv2.merge([
        cv2.convertScaleAbs(frame[:, :, index], alpha=gains[index])
        for index in range(3)
    ])

    # The sensor oversaturates reds.  Pull saturation back toward the phone
    # reference and apply a lightweight unsharp mask for fullscreen scaling.
    balanced = cv2.addWeighted(balanced, 0.72, frame, 0.28, 0)
    hsv = cv2.cvtColor(balanced, cv2.COLOR_BGR2HSV)
    hsv[:, :, 1] = cv2.convertScaleAbs(hsv[:, :, 1], alpha=0.80)
    corrected = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    blurred = cv2.GaussianBlur(corrected, (0, 0), 0.75)
    return cv2.addWeighted(corrected, 1.18, blurred, -0.18, 0)


def set_frame(frame):
    global img_show
    if frame is not None:
        with frame_lock:
            img_show = frame


def _encode_frames():
    global jpg_show
    while True:
        with frame_lock:
            frame = img_show
        if frame is not None:
            # Vision uses the stream as a full-screen first-person view.
            # Keep the camera's native frame instead of destroying detail.
            processed = _process_camera_frame(frame)
            ret, jpg = cv2.imencode('.jpg', processed, quality)
            if ret:
                jpg_show = jpg.tobytes()
        time.sleep(1.0 / 20.0)

class MJPG_Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global jpg_show
        if self.path == '/?action=snapshot':
            jpg_bytes = jpg_show
            if jpg_bytes is None:
                self.send_error(503, 'Camera frame not ready')
                return
            self.send_response(200)
            self.send_header('Content-type', 'image/jpeg')
            self.send_header('Content-length', str(len(jpg_bytes)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(jpg_bytes)
        elif self.path == '/?action=stream':
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            while True:
                try:
                    jpg_bytes = jpg_show
                    if jpg_bytes is not None:
                        self.wfile.write(b'--frame\r\n')
                        self.wfile.write(b'Content-Type: image/jpeg\r\n')
                        self.wfile.write(f'Content-Length: {len(jpg_bytes)}\r\n\r\n'.encode())
                        self.wfile.write(jpg_bytes)
                        self.wfile.write(b'\r\n')
                    time.sleep(1.0 / 20.0)
                except (BrokenPipeError, ConnectionResetError):
                    break
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""
    daemon_threads = True
    allow_reuse_address = True


def startMjpgServer():
    try:
        threading.Thread(target=_encode_frames, daemon=True).start()
        server = ThreadedHTTPServer(('', 8080), MJPG_Handler)
        print("server started")
        server.serve_forever()
    except KeyboardInterrupt:
        pass
