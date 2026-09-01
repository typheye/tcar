#!/usr/bin/env python3
"""tCar Core process entry point and sole hardware lifecycle owner."""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from hardware.i2c_bus import shared_i2c
from hardware.battery_monitor import BatteryMonitor
from hardware.board_key import BoardKeys
from hardware.board_rgb import BoardRGB
from hardware.buzzer import Buzzer
from hardware.motor import MotorController
from hardware.mpu6050 import MPU6050
from hardware.ps_controller import PSController
from hardware.hmc5883l import HMC5883L
from hardware.fourInfrared import FourInfrared
from hardware.servo import ServoController
from hardware.sonar import Sonar
from hardware.video_device import VideoDevice
from server.api.server import APIServer
from server.core.control import ControlService
from server.core.lifecycle import Lifecycle
from server.core.logd_manager import INFO, get_logger, install_print_capture, set_level
from server.core.telemetry import Telemetry
from server.rpc.server import RPCServer


def main():
    set_level(INFO)
    install_print_capture()
    log = get_logger("tCarCore")
    lifecycle = Lifecycle()
    lifecycle.install_signal_handlers()
    lifecycle.add("I2C bus", shared_i2c)

    # Drivers are created once here and injected everywhere else. No service
    # is allowed to instantiate a second owner for the same physical device.
    buzzer = lifecycle.add("buzzer", Buzzer())
    rgb = lifecycle.add("board RGB", BoardRGB())
    keys = lifecycle.add("board keys", BoardKeys(buzzer))
    motors = lifecycle.add("motors", MotorController())
    servos = lifecycle.add("servos", ServoController())
    sonar = lifecycle.add("sonar", Sonar())
    infrared = lifecycle.add("four infrared", FourInfrared())
    battery = lifecycle.add("battery", BatteryMonitor())
    mpu = lifecycle.add("MPU6050", MPU6050())
    mpu.set_motion_provider(motors.motion_snapshot)
    magnetometer = lifecycle.add("HMC5883L", HMC5883L())
    video = lifecycle.add("video", VideoDevice())

    control = lifecycle.add(
        "core control",
        ControlService(motors, servos, mpu, magnetometer, buzzer, sonar),
    )
    telemetry = lifecycle.add(
        "telemetry", Telemetry(mpu, magnetometer, sonar, battery, servos, infrared)
    )
    controller = lifecycle.add("PS controller", PSController(control.handle_input))
    lifecycle.add("internal RPC", RPCServer(telemetry, motors, servos, sonar, control))
    api = lifecycle.add("external API", APIServer(telemetry, video, control))
    control.desktop_toggle = api.toggle_paused
    try:
        lifecycle.start()
        log.info("tCar Core initialized")
        # Startup acknowledgement is intentionally emitted only after every
        # calibration and service has completed successfully.
        buzzer.pattern([(1, .08)])
        lifecycle.wait()
        return 0
    except Exception:
        log.exception("fatal startup error")
        return 1
    finally:
        lifecycle.stop()
        log.info("tCar Core stopped")


if __name__ == "__main__":
    raise SystemExit(main())
