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
import numpy as np
import time
import queue
import threading
import json
import hmac
import os
from http.server import BaseHTTPRequestHandler, HTTPServer,ThreadingHTTPServer
from socketserver import ThreadingMixIn
from io import StringIO, BytesIO


img_show = None
jpg_show = None
jpg_show_time = None
img_sequence = 0
jpg_sequence = 0
frame_lock = threading.Lock()
frame_condition = threading.Condition(frame_lock)
jpg_condition = threading.Condition()
quality = (int(cv2.IMWRITE_JPEG_QUALITY), 74)
paused_client_ips = set()
AUTH_USERNAME = os.environ.get('TCAR_USERNAME', 'tcar')
AUTH_PASSWORD = os.environ.get('TCAR_PASSWORD', 'admin123')


def set_paused_clients(client_ips):
    global paused_client_ips
    paused_client_ips = set(client_ips)
    with frame_condition:
        frame_condition.notify_all()
    with jpg_condition:
        jpg_condition.notify_all()


def _client_is_paused(client_ip):
    return client_ip in paused_client_ips


def _process_camera_frame(frame):
    """Neutralize the camera's magenta cast without crushing highlights."""
    # Gray-world balance is intentionally limited so colored scenes stay
    # colored.  It mainly corrects the strong red/magenta bias seen on white.
    small = cv2.resize(frame, (160, 120), interpolation=cv2.INTER_AREA)
    means = small.reshape(-1, 3).mean(axis=0)
    target = max(1.0, float(means.mean()))
    gains = [max(0.88, min(1.12, target / max(1.0, float(v)))) for v in means]
    # Fold the old balance/source blend into one native OpenCV operation.
    # This avoids three channel copies, a merge and a second full-frame pass.
    effective = [0.72 * gain + 0.28 for gain in gains]
    matrix = np.diag(effective).astype(np.float32)
    return cv2.transform(frame, matrix)


def set_frame(frame):
    global img_show, img_sequence
    if frame is not None:
        with frame_condition:
            if frame is img_show:
                return
            img_show = frame
            img_sequence += 1
            frame_condition.notify()


def _encode_frames():
    global jpg_show, jpg_show_time, jpg_sequence
    encoded_input_sequence = 0
    while True:
        with frame_condition:
            frame_condition.wait_for(lambda: img_sequence > encoded_input_sequence)
            frame = img_show
            encoded_input_sequence = img_sequence
        # Keep the camera's native frame instead of destroying detail.
        processed = _process_camera_frame(frame)
        ret, jpg = cv2.imencode('.jpg', processed, quality)
        if ret:
            with jpg_condition:
                jpg_show = jpg.tobytes()
                jpg_show_time = time.time()
                jpg_sequence = encoded_input_sequence
                jpg_condition.notify_all()

class MJPG_Handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != '/api/login':
            self.send_error(404)
            return
        try:
            content_length = int(self.headers.get('Content-Length', '0'))
            if content_length <= 0 or content_length > 4096:
                raise ValueError('invalid request size')
            payload = json.loads(self.rfile.read(content_length).decode('utf-8'))
            if not isinstance(payload, dict):
                raise ValueError('request body must be an object')
            username = str(payload.get('username', ''))
            password = str(payload.get('password', ''))
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, {'status': 0, 'error': 'invalid_request'})
            return
        authenticated = (
            hmac.compare_digest(username, AUTH_USERNAME)
            and hmac.compare_digest(password, AUTH_PASSWORD)
        )
        if not authenticated:
            self._send_json(401, {'status': 0, 'error': 'invalid_credentials'})
            return
        self._send_json(200, {'status': 1})

    def do_GET(self):
        global jpg_show, jpg_show_time, jpg_sequence
        client_ip = self.client_address[0]
        if _client_is_paused(client_ip):
            self.send_error(503, 'Desktop services paused')
            return
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
            sent_sequence = 0
            while True:
                try:
                    with jpg_condition:
                        if _client_is_paused(client_ip):
                            jpg_condition.wait_for(
                                lambda: not _client_is_paused(client_ip),
                                timeout=1.0,
                            )
                            continue
                        jpg_condition.wait_for(
                            lambda: (_client_is_paused(client_ip)
                                     or jpg_sequence > sent_sequence),
                            timeout=1.0,
                        )
                        if _client_is_paused(client_ip):
                            continue
                        if jpg_sequence <= sent_sequence:
                            continue
                        jpg_bytes = jpg_show
                        frame_time = jpg_show_time
                        sent_sequence = jpg_sequence
                    self.wfile.write(b'--frame\r\n')
                    self.wfile.write(b'Content-Type: image/jpeg\r\n')
                    self.wfile.write(f'X-Frame-Sequence: {sent_sequence}\r\n'.encode())
                    if frame_time is not None:
                        self.wfile.write(f'X-Frame-Time: {frame_time:.6f}\r\n'.encode())
                    self.wfile.write(f'Content-Length: {len(jpg_bytes)}\r\n\r\n'.encode())
                    self.wfile.write(jpg_bytes)
                    self.wfile.write(b'\r\n')
                    self.wfile.flush()
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
