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
quality = (int(cv2.IMWRITE_JPEG_QUALITY), 55)


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
            # The viewer is 240x180; 320x240 avoids wasting Pi CPU and Wi-Fi.
            preview = cv2.resize(frame, (320, 240), interpolation=cv2.INTER_AREA)
            ret, jpg = cv2.imencode('.jpg', preview, quality)
            if ret:
                jpg_show = jpg.tobytes()
        time.sleep(1.0 / 15.0)

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
                    time.sleep(1.0 / 15.0)
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
