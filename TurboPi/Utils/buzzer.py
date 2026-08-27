import time
import threading
import HiwonderSDK.Board as Board


_sound_lock = threading.Lock()


def _pulse(duration):
    Board.setBuzzer(0)
    Board.setBuzzer(1)
    time.sleep(duration)
    Board.setBuzzer(0)


def init(timer=0.08):
    with _sound_lock:
        _pulse(timer)

def keydown_PSControler():
    with _sound_lock:
        _pulse(0.01)

def keydown_combination_PSControler():
    with _sound_lock:
        _pulse(0.05)


def calibration_started():
    """Three crisp beeps after a sensor-calibration request is accepted."""
    with _sound_lock:
        for index in range(3):
            _pulse(0.07)
            if index < 2:
                time.sleep(0.10)


def calibration_finished():
    """Two half-second tones when calibration completes."""
    with _sound_lock:
        _pulse(0.5)
        time.sleep(0.2)
        _pulse(0.5)


def desktop_services_paused():
    with _sound_lock:
        _pulse(0.5)


def desktop_services_resumed():
    with _sound_lock:
        _pulse(0.1)
        time.sleep(0.2)
        _pulse(0.1)
