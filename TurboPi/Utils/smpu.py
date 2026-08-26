#!/usr/bin/python3
# coding=utf8
# 闁哄倸娲ｅ▎銏ゅ触? smpu.py

import smbus
import math
import socket
import time
import struct
import sys
import os
import json
sys.path.append('/home/pi/TurboPi/')
from smbus2 import SMBus, i2c_msg


def wrap_angle(angle):
    """Wrap degrees to [-180, 180)."""
    return (angle + 180.0) % 360.0 - 180.0

# ============ 閻℃帒鎳庨敍鎰枖閵忋垼顫?============
class Sonar:
    def __init__(self):
        self.i2c_addr = 0x77
        self.i2c = 1
        self.max_distance = 5000

    def getDistance(self):
        """Read sonar distance in mm."""
        dist = 5000
        try:
            with SMBus(self.i2c) as bus:
                write = i2c_msg.write(self.i2c_addr, [0x00,])
                bus.i2c_rdwr(write)
                time.sleep(0.02)
                
                read = i2c_msg.read(self.i2c_addr, 2)
                bus.i2c_rdwr(read)
                
                data = list(read)
                if len(data) >= 2:
                    dist = (data[0] << 8) | data[1]
                    if dist < 30 or dist > 5000:
                        dist = 5000
        except Exception as e:
            print(f"Sonar error: {e}")
            dist = 5000
        return dist


# ============ GY-271 Magnetometer ============
class Magnetometer:
    QMC5883L_ADDR = 0x0D
    HMC5883L_ADDR = 0x1E
    COORDINATE_AXIS_MAP = [0, 1, 2]
    COORDINATE_AXIS_SIGN = [1.0, -1.0, -1.0]

    def __init__(self, bus, cal_file=None):
        self.bus = bus
        self.address = None
        self.kind = None
        self.available = False
        self.cal_file = cal_file or os.path.join(os.path.dirname(__file__), "mag_calibration.json")
        self.offset = [0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0, 1.0]
        self.axis_map = list(self.COORDINATE_AXIS_MAP)
        self.axis_sign = list(self.COORDINATE_AXIS_SIGN)
        self.yaw_sign = 1.0
        self.yaw_zero = 0.0
        self.weight = 0.001
        self.field_radius = 80.0
        self.last_heading = None
        self._load_calibration()
        self._detect_and_init()

    def _load_calibration(self):
        try:
            with open(self.cal_file, "r") as f:
                cfg = json.load(f)
            self.offset = [float(v) for v in cfg.get("offset", self.offset)]
            self.scale = [float(v) for v in cfg.get("scale", self.scale)]
            self.axis_map = list(self.COORDINATE_AXIS_MAP)
            self.axis_sign = list(self.COORDINATE_AXIS_SIGN)
            self.yaw_sign = float(cfg.get("yaw_sign", self.yaw_sign))
            self.weight = min(float(cfg.get("weight", self.weight)), self.weight)
            self.field_radius = float(cfg.get("field_radius", self.field_radius))
            if self._calibration_is_bad():
                self.offset = [0.0, 0.0, 0.0]
                self.scale = [1.0, 1.0, 1.0]
                print("Mag calibration ignored: saturated/invalid calibration values")
                return
            print(f"Mag calibration loaded: {self.cal_file}")
        except Exception:
            print("Mag calibration not found, using raw magnetometer scale")

    def _calibration_is_bad(self):
        if any(abs(v) >= 4080.0 for v in self.offset):
            return True
        if any(v <= 0.0 or v > 3.0 for v in self.scale):
            return True
        if self.field_radius < 20.0:
            return True
        return False

    def _probe(self, address):
        try:
            self.bus.read_byte_data(address, 0x00)
            return True
        except Exception:
            return False

    def _detect_and_init(self):
        if self._probe(self.QMC5883L_ADDR):
            self.address = self.QMC5883L_ADDR
            self.kind = "QMC5883L"
            self._init_qmc5883l()
        elif self._probe(self.HMC5883L_ADDR):
            self.address = self.HMC5883L_ADDR
            self.kind = "HMC5883L"
            self._init_hmc5883l()
        else:
            print("Magnetometer not found at 0x0D or 0x1E")
            return
        self.available = True
        print(f"Magnetometer detected: {self.kind} at 0x{self.address:02X}")

    def _init_qmc5883l(self):
        self.bus.write_byte_data(self.address, 0x0B, 0x01)
        self.bus.write_byte_data(self.address, 0x09, 0x1D)  # continuous, 200Hz, 8G, OSR512
        time.sleep(0.02)

    def _init_hmc5883l(self):
        self.bus.write_byte_data(self.address, 0x00, 0x70)
        self.bus.write_byte_data(self.address, 0x01, 0xE0)  # 8.1G range, avoid -4096 overflow near the car
        self.bus.write_byte_data(self.address, 0x02, 0x00)
        time.sleep(0.02)

    def _read_i16_le(self, data, i):
        value = data[i] | (data[i + 1] << 8)
        if value >= 0x8000:
            value -= 0x10000
        return value

    def _read_i16_be(self, data, i):
        value = (data[i] << 8) | data[i + 1]
        if value >= 0x8000:
            value -= 0x10000
        return value

    def read_raw(self):
        if not self.available:
            return None
        try:
            if self.kind == "QMC5883L":
                data = self.bus.read_i2c_block_data(self.address, 0x00, 6)
                return [self._read_i16_le(data, 0), self._read_i16_le(data, 2), self._read_i16_le(data, 4)]
            data = self.bus.read_i2c_block_data(self.address, 0x03, 6)
            return [self._read_i16_be(data, 0), self._read_i16_be(data, 4), self._read_i16_be(data, 2)]
        except Exception as e:
            print(f"Mag read error: {e}")
            return None

    def read_calibrated(self):
        raw = self.read_raw()
        if raw is None:
            return None
        if self.is_saturated(raw):
            return None
        mapped = [raw[self.axis_map[i]] * self.axis_sign[i] for i in range(3)]
        return [(mapped[i] - self.offset[i]) * self.scale[i] for i in range(3)]

    def is_saturated(self, raw):
        return any(v <= -4090 or v >= 4090 for v in raw)

    def diagnostic(self, current_yaw=None):
        if not self.available:
            return None
        raw = self.read_raw()
        if raw is None:
            return None
        saturated = self.is_saturated(raw)
        mapped = [raw[self.axis_map[i]] * self.axis_sign[i] for i in range(3)]
        cal = [(mapped[i] - self.offset[i]) * self.scale[i] for i in range(3)]
        heading = None
        rel_yaw = None
        yaw_error = None
        mx, my, _ = cal
        if not saturated and abs(mx) + abs(my) >= 1e-6:
            heading = wrap_angle(math.degrees(math.atan2(my, mx)))
            rel_yaw = wrap_angle((heading - self.yaw_zero) * self.yaw_sign)
            if current_yaw is not None:
                yaw_error = wrap_angle(rel_yaw - current_yaw)
        return {
            "raw": raw,
            "mapped": mapped,
            "cal": cal,
            "heading": heading,
            "relative_yaw": rel_yaw,
            "yaw_error": yaw_error,
            "kind": self.kind,
            "saturated": saturated,
            "strength": math.sqrt(mx * mx + my * my),
        }

    def heading(self):
        mag = self.read_calibrated()
        if mag is None:
            return None
        mx, my, _ = mag
        if abs(mx) + abs(my) < 1e-6:
            return None
        heading = math.degrees(math.atan2(my, mx))
        self.last_heading = wrap_angle(heading)
        return self.last_heading

    def zero_yaw(self, samples=40):
        if not self.available:
            return False
        values = []
        for _ in range(samples):
            heading = self.heading()
            if heading is not None:
                values.append(math.radians(heading))
            time.sleep(0.01)
        if not values:
            print("Mag yaw zero skipped: no heading")
            return False
        sx = sum(math.cos(v) for v in values)
        sy = sum(math.sin(v) for v in values)
        self.yaw_zero = math.degrees(math.atan2(sy, sx))
        print(f"  Mag yaw zero calibrated: {self.yaw_zero:.1f} deg")
        return True

    def relative_yaw(self):
        heading = self.heading()
        if heading is None:
            return None
        return wrap_angle((heading - self.yaw_zero) * self.yaw_sign)

    def calibrate_hard_soft_iron(self, seconds=30):
        if not self.available:
            print("Mag calibration failed: magnetometer not found")
            return False
        print(f"Rotate the whole car slowly for {seconds} seconds...")
        mins = [float("inf"), float("inf"), float("inf")]
        maxs = [float("-inf"), float("-inf"), float("-inf")]
        count = 0
        saturated_count = 0
        deadline = time.time() + seconds
        while time.time() < deadline:
            raw = self.read_raw()
            if raw:
                if self.is_saturated(raw):
                    saturated_count += 1
                    time.sleep(0.03)
                    continue
                mapped = [raw[self.axis_map[i]] * self.axis_sign[i] for i in range(3)]
                for i in range(3):
                    mins[i] = min(mins[i], mapped[i])
                    maxs[i] = max(maxs[i], mapped[i])
                count += 1
            time.sleep(0.03)
        if count < 20:
            print(f"Mag calibration failed: too few valid samples, saturated={saturated_count}")
            return False
        if saturated_count > count * 0.2:
            print(f"Mag calibration failed: too many saturated samples, valid={count}, saturated={saturated_count}")
            return False
        radii = [(maxs[i] - mins[i]) * 0.5 for i in range(3)]
        if radii[0] < 20.0 or radii[1] < 20.0:
            print(f"Mag calibration failed: x/y radius too small {radii}")
            return False
        avg_radius = (radii[0] + radii[1]) * 0.5
        self.field_radius = avg_radius
        self.offset = [(maxs[i] + mins[i]) * 0.5 for i in range(3)]
        self.scale = [
            avg_radius / radii[0],
            avg_radius / radii[1],
            1.0,
        ]
        cfg = {
            "kind": self.kind,
            "address": self.address,
            "offset": self.offset,
            "scale": self.scale,
            "axis_map": self.axis_map,
            "axis_sign": self.axis_sign,
            "yaw_sign": self.yaw_sign,
            "weight": self.weight,
            "field_radius": self.field_radius,
        }
        with open(self.cal_file, "w") as f:
            json.dump(cfg, f, indent=2)
        print(f"Mag calibration saved: {self.cal_file}")
        print(f"  valid samples: {count}, saturated skipped: {saturated_count}")
        print(f"  offset: {self.offset}")
        print(f"  scale:  {self.scale}")
        print(f"  field_radius: {self.field_radius:.1f}")
        return True



# ============ Quaternion attitude estimator ============
class AttitudeEstimator:
    def __init__(self, sample_freq=100):
        self.dt = 1.0 / sample_freq
        self.last_update = None
        self.q = [1.0, 0.0, 0.0, 0.0]
        self.zero_q = [1.0, 0.0, 0.0, 0.0]
        self.pitch = 0.0
        self.roll = 0.0
        self.yaw = 0.0
        self.kp = 0.0

    def _normalize_quat(self, q):
        norm = math.sqrt(sum(v * v for v in q))
        if norm <= 0.0:
            return [1.0, 0.0, 0.0, 0.0]
        return [v / norm for v in q]

    def _quat_mul(self, a, b):
        aw, ax, ay, az = a
        bw, bx, by, bz = b
        return [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ]

    def _quat_conj(self, q):
        return [q[0], -q[1], -q[2], -q[3]]

    def _relative_quat(self):
        return self._normalize_quat(self._quat_mul(self._quat_conj(self.zero_q), self.q))

    def _euler_from_quat(self, q):
        qw, qx, qy, qz = q
        sinr_cosp = 2.0 * (qw * qx + qy * qz)
        cosr_cosp = 1.0 - 2.0 * (qx * qx + qy * qy)
        roll_x = math.atan2(sinr_cosp, cosr_cosp)

        sinp = 2.0 * (qw * qy - qz * qx)
        if abs(sinp) >= 1.0:
            pitch_y = math.copysign(math.pi / 2.0, sinp)
        else:
            pitch_y = math.asin(sinp)

        siny_cosp = 2.0 * (qw * qz + qx * qy)
        cosy_cosp = 1.0 - 2.0 * (qy * qy + qz * qz)
        yaw_z = math.atan2(siny_cosp, cosy_cosp)
        return (math.degrees(pitch_y), math.degrees(roll_x), math.degrees(yaw_z))

    def update(self, gx, gy, gz, ax, ay, az):
        now = time.monotonic()
        if self.last_update is None:
            dt = self.dt
        else:
            dt = now - self.last_update
            if dt <= 0.0 or dt > 0.1:
                dt = self.dt
        self.last_update = now

        gx_rad = math.radians(gx)
        gy_rad = math.radians(gy)
        gz_rad = math.radians(gz)

        norm = math.sqrt(ax * ax + ay * ay + az * az)
        if self.kp > 0.0 and norm > 0.001:
            qw, qx, qy, qz = self.q
            vx = 2.0 * (qx * qz - qw * qy)
            vy = 2.0 * (qw * qx + qy * qz)
            vz = qw * qw - qx * qx - qy * qy + qz * qz
            ax_n = ax / norm
            ay_n = ay / norm
            az_n = az / norm
            if abs(norm - 1.0) < 0.25:
                ex = ay_n * vz - az_n * vy
                ey = az_n * vx - ax_n * vz
                ez = ax_n * vy - ay_n * vx
                gx_rad += self.kp * ex
                gy_rad += self.kp * ey
                gz_rad += self.kp * ez

        q_dot = self._quat_mul(self.q, [0.0, gx_rad, gy_rad, gz_rad])
        half_dt = 0.5 * dt
        self.q = self._normalize_quat([
            self.q[0] + q_dot[0] * half_dt,
            self.q[1] + q_dot[1] * half_dt,
            self.q[2] + q_dot[2] * half_dt,
            self.q[3] + q_dot[3] * half_dt,
        ])
        self.pitch, self.roll, self.yaw = self._euler_from_quat(self._relative_quat())

    def calibrate_zero(self, samples=100):
        print("Calibrating attitude zero... keep the MPU6050 still")
        if samples > 0:
            time.sleep(samples * 0.01)
        self.q = [1.0, 0.0, 0.0, 0.0]
        self.zero_q = [1.0, 0.0, 0.0, 0.0]
        self.last_update = None
        self.pitch, self.roll, self.yaw = self._euler_from_quat(self._relative_quat())
        print("  Attitude zero calibrated")

    def get_angles(self):
        self.pitch, self.roll, self.yaw = self._euler_from_quat(self._relative_quat())
        return (-self.pitch, self.roll, -self.yaw)

    def get_quaternion(self):
        q = self._relative_quat()
        return [q[0], q[1], -q[2], -q[3]]


# ============ MPU6050 DMP/FIFO ============
class MPU6050DMP:
    """Minimal MPU6050 DMP/FIFO quaternion reader.

    MPU6050 DMP requires a firmware blob. This project uses the 3062-byte
    libdriver firmware extracted to TurboPi/Utils/dmp_firmware.bin.
    If the blob is absent, this driver stays disabled and the software
    quaternion estimator is used.
    """

    REG_BANK_SEL = 0x6D
    REG_MEM_START_ADDR = 0x6E
    REG_MEM_R_W = 0x6F
    REG_USER_CTRL = 0x6A
    REG_PWR_MGMT_1 = 0x6B
    REG_PWR_MGMT_2 = 0x6C
    REG_INT_ENABLE = 0x38
    REG_INT_STATUS = 0x3A
    REG_FIFO_COUNTH = 0x72
    REG_FIFO_R_W = 0x74
    REG_FIFO_EN = 0x23
    REG_SMPLRT_DIV = 0x19
    REG_CONFIG = 0x1A
    REG_GYRO_CONFIG = 0x1B
    REG_ACCEL_CONFIG = 0x1C
    REG_PROGRAM_START = 0x70

    DMP_SAMPLE_RATE = 200
    DMP_FIFO_RATE = 50
    DMP_GYRO_SF = int(46850825 * 200 / DMP_SAMPLE_RATE)

    DMP_D_0_22 = 512 + 22
    DMP_D_0_104 = 104
    DMP_D_EXT_GYRO_BIAS_X = 61 * 16
    DMP_D_EXT_GYRO_BIAS_Y = 61 * 16 + 4
    DMP_D_EXT_GYRO_BIAS_Z = 61 * 16 + 8
    DMP_FCFG_1 = 1062
    DMP_FCFG_2 = 1066
    DMP_FCFG_3 = 1088
    DMP_FCFG_7 = 1073
    DMP_CFG_MOTION_BIAS = 1208
    DMP_CFG_ORIENT_INT = 1853
    DMP_CFG_20 = 2224
    DMP_CFG_FIFO_ON_EVENT = 2690
    DMP_CFG_LP_QUAT = 2712
    DMP_CFG_8 = 2718
    DMP_CFG_15 = 2727
    DMP_CFG_27 = 2742
    DMP_CFG_6 = 2753

    PACKET_SIZE = 16
    QUAT_SCALE = 1073741824.0

    def __init__(self, bus, address=0x68):
        self.bus = bus
        self.address = address
        self.enabled = False
        self.packet_size = self.PACKET_SIZE
        self.firmware_path = os.path.join(os.path.dirname(__file__), "dmp_firmware.bin")

    def _write_byte(self, reg, value):
        self.bus.write_byte_data(self.address, reg, value & 0xFF)

    def _read_byte(self, reg):
        return self.bus.read_byte_data(self.address, reg)

    def _read_block(self, reg, length):
        return self.bus.read_i2c_block_data(self.address, reg, length)

    def _write_block(self, reg, data):
        self.bus.write_i2c_block_data(self.address, reg, [v & 0xFF for v in data])

    def _set_bit(self, reg, bit, enabled):
        value = self._read_byte(reg)
        if enabled:
            value |= (1 << bit)
        else:
            value &= ~(1 << bit)
        self._write_byte(reg, value)

    def _set_memory_bank(self, bank):
        self._write_byte(self.REG_BANK_SEL, bank & 0x1F)

    def _set_memory_start(self, address):
        self._write_byte(self.REG_MEM_START_ADDR, address & 0xFF)

    def _write_memory_block(self, data, bank=0, address=0, chunk_size=16):
        i = 0
        while i < len(data):
            self._set_memory_bank(bank)
            self._set_memory_start(address)
            chunk = data[i:i + min(chunk_size, 256 - address, len(data) - i)]
            for value in chunk:
                self._write_byte(self.REG_MEM_R_W, value)
            i += len(chunk)
            address += len(chunk)
            if address >= 256:
                address = 0
                bank += 1
        return True

    def _write_dmp_mem(self, address, data):
        bank = address // 256
        offset = address % 256
        return self._write_memory_block(data, bank, offset)

    def _write_dmp_u16(self, address, value):
        self._write_dmp_mem(address, [(value >> 8) & 0xFF, value & 0xFF])

    def _write_dmp_u32(self, address, value):
        self._write_dmp_mem(address, [
            (value >> 24) & 0xFF,
            (value >> 16) & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF,
        ])

    def _write_dmp_i32(self, address, value):
        value = int(value)
        if value < 0:
            value += 0x100000000
        self._write_dmp_u32(address, value)

    def _configure_quaternion_feature(self):
        # Minimal libdriver feature mask: 6X quaternion + gyro calibration.
        self._write_dmp_u32(self.DMP_D_0_104, self.DMP_GYRO_SF)
        self._write_dmp_mem(self.DMP_CFG_15, [0xA3] * 10)
        self._write_dmp_mem(self.DMP_CFG_27, [0xD8])
        self._write_dmp_mem(self.DMP_CFG_MOTION_BIAS,
                            [0xB8, 0xAA, 0xB3, 0x8D, 0xB4, 0x98, 0x0D, 0x35, 0x5D])
        self._write_dmp_mem(self.DMP_CFG_20, [0xD8])
        self._write_dmp_mem(self.DMP_CFG_ORIENT_INT, [0xD8])
        self._write_dmp_mem(self.DMP_CFG_LP_QUAT, [0x8B, 0x8B, 0x8B, 0x8B])
        self._write_dmp_mem(self.DMP_CFG_8, [0x20, 0x28, 0x30, 0x38])

    def _set_orientation_identity(self):
        # libdriver mpu6050_dmp_set_orientation() for identity matrix:
        # {1,0,0, 0,1,0, 0,0,1}
        self._write_dmp_mem(self.DMP_FCFG_1, [0x4C, 0xCD, 0x6C])
        self._write_dmp_mem(self.DMP_FCFG_2, [0x0C, 0xC9, 0x2C])
        self._write_dmp_mem(self.DMP_FCFG_3, [0x36, 0x56, 0x76])
        self._write_dmp_mem(self.DMP_FCFG_7, [0x26, 0x46, 0x66])

    def _set_fifo_rate(self, rate):
        rate = max(1, min(self.DMP_SAMPLE_RATE, int(rate)))
        divider = int(self.DMP_SAMPLE_RATE / rate) - 1
        regs_end = [0xFE, 0xF2, 0xAB, 0xC4, 0xAA, 0xF1,
                    0xDF, 0xDF, 0xBB, 0xAF, 0xDF, 0xDF]
        self._write_dmp_u16(self.DMP_D_0_22, divider)
        self._write_dmp_mem(self.DMP_CFG_6, regs_end)

    def _read_firmware(self):
        if not os.path.exists(self.firmware_path):
            return None
        with open(self.firmware_path, "rb") as f:
            data = list(f.read())
        if len(data) < 3000:
            raise RuntimeError("DMP firmware blob is too small")
        return data

    def _write_dmp_gyro_bias(self, gyro_offset):
        if not gyro_offset:
            return
        addresses = [
            self.DMP_D_EXT_GYRO_BIAS_X,
            self.DMP_D_EXT_GYRO_BIAS_Y,
            self.DMP_D_EXT_GYRO_BIAS_Z,
        ]
        for address, raw_offset in zip(addresses, gyro_offset):
            bias_q16 = int((float(raw_offset) / 65.5) * 65536.0)
            dmp_bias = int((bias_q16 * self.DMP_GYRO_SF) >> 30)
            self._write_dmp_i32(address, dmp_bias)

    def begin(self, gyro_offset=None):
        firmware = self._read_firmware()
        if not firmware:
            print("DMP firmware not found, using software quaternion")
            return False

        print("Initializing MPU6050 DMP/FIFO...")
        self._write_byte(self.REG_PWR_MGMT_1, 0x80)
        time.sleep(0.1)
        self._write_byte(self.REG_PWR_MGMT_1, 0x01)
        self._write_byte(self.REG_PWR_MGMT_2, 0x00)
        time.sleep(0.02)

        self._write_byte(self.REG_SMPLRT_DIV, int(1000 / self.DMP_SAMPLE_RATE) - 1)
        self._write_byte(self.REG_CONFIG, 0x03)
        self._write_byte(self.REG_GYRO_CONFIG, 0x18)
        self._write_byte(self.REG_ACCEL_CONFIG, 0x00)
        self._write_byte(self.REG_FIFO_EN, 0x00)
        self._write_byte(self.REG_USER_CTRL, 0x00)

        self._set_bit(self.REG_USER_CTRL, 2, True)   # FIFO reset
        self._set_bit(self.REG_USER_CTRL, 3, True)   # DMP reset
        time.sleep(0.02)

        self._write_memory_block(firmware)

        self._write_block(self.REG_PROGRAM_START, [0x04, 0x00])
        self._set_orientation_identity()
        self._configure_quaternion_feature()
        self._write_dmp_gyro_bias(gyro_offset)
        self._set_fifo_rate(self.DMP_FIFO_RATE)

        self._write_byte(self.REG_FIFO_EN, 0x00)
        self._set_bit(self.REG_USER_CTRL, 2, True)
        time.sleep(0.01)
        self._write_byte(self.REG_USER_CTRL, 0xC0)    # FIFO enable + DMP enable
        self._write_byte(self.REG_INT_ENABLE, 0x02)
        self.enabled = True
        print("  DMP/FIFO enabled")
        return True

    def _fifo_count(self):
        data = self._read_block(self.REG_FIFO_COUNTH, 2)
        return (data[0] << 8) | data[1]

    def reset_fifo(self):
        self._set_bit(self.REG_USER_CTRL, 2, True)

    def _read_fifo_packet(self, length):
        packet = []
        while len(packet) < length:
            chunk_len = min(32, length - len(packet))
            packet.extend(self._read_block(self.REG_FIFO_R_W, chunk_len))
        return packet

    def read_quaternion(self):
        if not self.enabled:
            return None

        count = self._fifo_count()
        if count >= 1024:
            self.reset_fifo()
            return None
        if count < self.packet_size:
            return None

        while count >= self.packet_size * 2:
            self._read_fifo_packet(self.packet_size)
            count -= self.packet_size

        packet = self._read_fifo_packet(self.packet_size)
        qw = self._to_int32(packet[0:4]) / self.QUAT_SCALE
        qx = self._to_int32(packet[4:8]) / self.QUAT_SCALE
        qy = self._to_int32(packet[8:12]) / self.QUAT_SCALE
        qz = self._to_int32(packet[12:16]) / self.QUAT_SCALE
        norm = math.sqrt(qw * qw + qx * qx + qy * qy + qz * qz)
        if norm < 0.75 or norm > 1.25:
            self.reset_fifo()
            return None
        return [qw / norm, qx / norm, qy / norm, qz / norm]

    def _to_int32(self, data):
        value = (data[0] << 24) | (data[1] << 16) | (data[2] << 8) | data[3]
        if value & 0x80000000:
            value -= 0x100000000
        return value


# ============ MPU6050 ============
class MPU6050:
    def __init__(self, address=0x68, bus=1):
        self.bus = smbus.SMBus(bus)
        self.address = address
        self.gyro_offset = [0.0, 0.0, 0.0]
        self.mag = Magnetometer(self.bus)
        self.last_mag_debug = None
        self.mag_yaw_correction = 0.0
        self.mag_last_fuse_time = 0.0
        self.mag_prev_yaw = None
        self.mag_stable_since = 0.0
        self.dmp = None
        self.use_dmp = False
        self.dmp_zero_q = [1.0, 0.0, 0.0, 0.0]
        self.last_dmp_attitude = None
        
        self._init_mpu6050()
        self.calibrate_gyro()
        self.estimator = AttitudeEstimator(sample_freq=100)
        
        # 闁稿繐鐗愮换宥囨偘鐏炶偐顏辨繛鍫濈仛濡炲倿姊荤壕瀣靛敤濠殿喗瀵ч埀顑胯兌鑿欓悗?
        print("Waiting for attitude to stabilize...")
        for i in range(50):
            ax, ay, az, gx, gy, gz = self.read_all()
            ax_g = ax / 16384.0
            ay_g = ay / 16384.0
            az_g = az / 16384.0
            gx_dps = gx / 65.5
            gy_dps = gy / 65.5
            gz_dps = gz / 65.5
            self.estimator.update(gx_dps, gy_dps, gz_dps, ax_g, ay_g, az_g)
            time.sleep(0.01)
        
        # 闁哄秮鈧啿娅欑憸鐗堝浮濞?
        self.calibrate_attitude_zero()
        self._init_dmp()
        self.calibrate_mag_zero()

    def _write_byte(self, reg, val):
        try:
            self.bus.write_byte_data(self.address, reg, val)
            return True
        except:
            return False

    def _read_word_array(self, reg, length):
        try:
            return self.bus.read_i2c_block_data(self.address, reg, length)
        except:
            return [0] * length

    def _init_mpu6050(self):
        """闁告帗绻傞～鎰板礌閺堟瓍U6050"""
        print("Initializing MPU6050...")
        
        self._write_byte(0x6B, 0x00)
        time.sleep(0.1)
        self._write_byte(0x6B, 0x01)
        time.sleep(0.1)
        self._write_byte(0x19, 0x09)
        self._write_byte(0x1A, 0x06)
        self._write_byte(0x1B, 0x08)
        self._write_byte(0x1C, 0x00)
        self._write_byte(0x23, 0x00)
        self._write_byte(0x38, 0x00)
        
        time.sleep(0.1)
        print("  MPU6050 initialized")

    def calibrate_gyro(self, samples=200):
        """Calibrate gyro offset."""
        print("Calibrating gyro... keep still")
        gyro_sum = [0.0, 0.0, 0.0]
        
        for i in range(samples):
            data = self._read_word_array(0x43, 6)
            if len(data) >= 6:
                for j in range(3):
                    val = (data[j*2] << 8) + data[j*2+1]
                    if val >= 0x8000:
                        val -= 0x10000
                    gyro_sum[j] += val
            time.sleep(0.005)
        
        self.gyro_offset = [s / samples for s in gyro_sum]
        print(f"  Gyro offset: ({self.gyro_offset[0]:.2f}, {self.gyro_offset[1]:.2f}, {self.gyro_offset[2]:.2f})")

    def calibrate_attitude_zero(self, samples=100):
        """Warm the filter with live samples, then set current pose as zero."""
        print("Zeroing attitude... keep still")
        for _ in range(samples):
            ax, ay, az, gx, gy, gz = self.read_all()
            self.estimator.update(
                gx / 65.5,
                gy / 65.5,
                gz / 65.5,
                ax / 16384.0,
                ay / 16384.0,
                az / 16384.0,
            )
            time.sleep(0.01)
        self.estimator.calibrate_zero(samples=0)

    def _quat_conj(self, q):
        return [q[0], -q[1], -q[2], -q[3]]

    def _quat_mul(self, a, b):
        return self.estimator._quat_mul(a, b)

    def _normalize_quat(self, q):
        return self.estimator._normalize_quat(q)

    def _quat_from_euler(self, pitch, roll, yaw):
        p = math.radians(pitch) * 0.5
        r = math.radians(roll) * 0.5
        y = math.radians(yaw) * 0.5
        cp, sp = math.cos(p), math.sin(p)
        cr, sr = math.cos(r), math.sin(r)
        cy, sy = math.cos(y), math.sin(y)
        return self._normalize_quat([
            cr * cp * cy + sr * sp * sy,
            sr * cp * cy - cr * sp * sy,
            cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy,
        ])

    def _output_quat_from_angles(self, pitch, roll, yaw):
        internal_q = self._quat_from_euler(-pitch, roll, -yaw)
        return [internal_q[0], internal_q[1], -internal_q[2], -internal_q[3]]

    def calibrate_mag_zero(self):
        if self.mag.available:
            print("Zeroing magnetometer yaw... keep current heading")
            if self.mag.zero_yaw():
                self.mag_yaw_correction = 0.0

    def _fuse_mag_yaw(self, pitch, roll, yaw, qw, qx, qy, qz, gz_dps=0.0):
        if not self.mag.available:
            return (pitch, roll, yaw, qw, qx, qy, qz)
        corrected_yaw = wrap_angle(yaw + self.mag_yaw_correction)
        self.last_mag_debug = self.mag.diagnostic(corrected_yaw)
        if not self.last_mag_debug or self.last_mag_debug.get("saturated"):
            if self.last_mag_debug:
                self.last_mag_debug["used"] = False
                self.last_mag_debug["reject"] = "sat"
            qw, qx, qy, qz = self._output_quat_from_angles(pitch, roll, corrected_yaw)
            return (pitch, roll, corrected_yaw, qw, qx, qy, qz)
        mag_yaw = self.last_mag_debug.get("relative_yaw")
        if mag_yaw is None:
            self.last_mag_debug["used"] = False
            self.last_mag_debug["reject"] = "no-yaw"
            qw, qx, qy, qz = self._output_quat_from_angles(pitch, roll, corrected_yaw)
            return (pitch, roll, corrected_yaw, qw, qx, qy, qz)
        strength = self.last_mag_debug.get("strength", 0.0)
        min_strength = max(35.0, self.mag.field_radius * 0.65)
        max_strength = max(min_strength + 1.0, self.mag.field_radius * 1.45)
        now = time.time()
        if self.mag_prev_yaw is None:
            mag_delta = 0.0
        else:
            mag_delta = abs(wrap_angle(mag_yaw - self.mag_prev_yaw))
        self.mag_prev_yaw = mag_yaw
        if mag_delta <= 8.0:
            if self.mag_stable_since <= 0.0:
                self.mag_stable_since = now
        else:
            self.mag_stable_since = now
        mag_stable_time = now - self.mag_stable_since
        err = wrap_angle(mag_yaw - corrected_yaw)
        reject = None
        if strength < min_strength:
            reject = "weak"
        elif strength > max_strength:
            reject = "strong"
        elif abs(gz_dps) >= 2.0:
            reject = "turn"
        elif abs(pitch) >= 20.0 or abs(roll) >= 20.0:
            reject = "tilt"
        elif mag_stable_time < 0.5:
            reject = "settle"
        elif now - self.mag_last_fuse_time < 0.1:
            reject = "wait"
        if reject is None:
            max_step = 0.8
            step = max(-max_step, min(max_step, err * 0.04))
            if abs(err) < 1.0:
                step = err * self.mag.weight
            self.mag_yaw_correction = wrap_angle(self.mag_yaw_correction + step)
            self.mag_last_fuse_time = now
            self.last_mag_debug["used"] = True
            self.last_mag_debug["reject"] = "ok"
            self.last_mag_debug["step"] = step
        else:
            self.last_mag_debug["used"] = False
            self.last_mag_debug["reject"] = reject
            self.last_mag_debug["step"] = 0.0
        self.last_mag_debug["stable"] = mag_stable_time
        self.last_mag_debug["delta"] = mag_delta
        corrected_yaw = wrap_angle(yaw + self.mag_yaw_correction)
        qw, qx, qy, qz = self._output_quat_from_angles(pitch, roll, corrected_yaw)
        return (pitch, roll, corrected_yaw, qw, qx, qy, qz)

    def mag_debug_text(self):
        dbg = self.last_mag_debug
        if not dbg:
            return "Mag: unavailable"
        raw = dbg["raw"]
        mapped = dbg["mapped"]
        cal = dbg["cal"]
        heading = dbg["heading"]
        rel_yaw = dbg["relative_yaw"]
        yaw_error = dbg["yaw_error"]
        strength = dbg.get("strength", 0.0)
        used = "Y" if dbg.get("used") else "N"
        reject = dbg.get("reject", "?")
        step = dbg.get("step", 0.0)
        stable = dbg.get("stable", 0.0)
        delta = dbg.get("delta", 0.0)
        def fmt(values):
            return f"{values[0]:7.1f},{values[1]:7.1f},{values[2]:7.1f}"
        def fmt_angle(value):
            return "   None" if value is None else f"{value:7.1f}"
        return (
            f"Mag {dbg['kind']}{' SAT' if dbg.get('saturated') else '   '} "
            f"raw[{fmt(raw)}] map[{fmt(mapped)}] cal[{fmt(cal)}] "
            f"head:{fmt_angle(heading)} magYaw:{fmt_angle(rel_yaw)} "
            f"err:{fmt_angle(yaw_error)} corr:{self.mag_yaw_correction:7.1f} "
            f"str:{strength:6.1f} use:{used} {reject} "
            f"step:{step:5.2f} st:{stable:4.1f}s d:{delta:4.1f}"
        )

    def _init_dmp(self):
        self.dmp = MPU6050DMP(self.bus, self.address)
        try:
            self.use_dmp = self.dmp.begin(self.gyro_offset)
            if self.use_dmp:
                self.calibrate_dmp_zero()
                self.use_dmp = self._validate_dmp_stationary()
                if not self.use_dmp:
                    self._restore_software_filter()
        except Exception as e:
            print(f"DMP init failed, using software quaternion: {e}")
            self.use_dmp = False
            self._restore_software_filter()

    def _restore_software_filter(self):
        print("Restoring software attitude filter...")
        self._init_mpu6050()
        self.calibrate_gyro()
        self.estimator = AttitudeEstimator(sample_freq=100)
        self.calibrate_attitude_zero()

    def calibrate_dmp_zero(self, samples=80):
        """Set current DMP quaternion as zero orientation."""
        print("Zeroing DMP attitude... keep still")
        self.dmp.reset_fifo()
        time.sleep(0.1)
        last_q = None
        deadline = time.time() + max(2.0, samples * 0.03)
        while time.time() < deadline and samples > 0:
            q = self.dmp.read_quaternion()
            if q:
                last_q = q
                samples -= 1
            time.sleep(0.005)
        if last_q:
            self.dmp_zero_q = list(last_q)
            print("  DMP attitude zero calibrated")
        else:
            print("  DMP zero skipped: no FIFO quaternion")

    def _validate_dmp_stationary(self, seconds=2.0, limit_deg=12.0):
        """Reject DMP if it drifts hard immediately after zeroing."""
        print("Checking DMP stability... keep still")
        deadline = time.time() + seconds
        max_abs = 0.0
        got = 0
        while time.time() < deadline:
            q = self.dmp.read_quaternion()
            if q:
                rel_q = self._relative_dmp_quaternion(q)
                pitch, roll, yaw = self.estimator._euler_from_quat(rel_q)
                pitch, roll, yaw, _ = self._apply_output_axis_signs(pitch, roll, yaw, rel_q)
                max_abs = max(max_abs, abs(pitch), abs(roll), abs(yaw))
                got += 1
            time.sleep(0.01)
        if got < 5:
            print("  DMP stability check failed: no FIFO quaternion, using software quaternion")
            return False
        if max_abs > limit_deg:
            print(f"  DMP stability check failed: drift {max_abs:.1f} deg, using software quaternion")
            return False
        print(f"  DMP stability OK: max drift {max_abs:.1f} deg")
        return True

    def _relative_dmp_quaternion(self, q):
        return self._normalize_quat(self._quat_mul(self._quat_conj(self.dmp_zero_q), q))

    def _apply_output_axis_signs(self, pitch, roll, yaw, q):
        return (
            -pitch,
            roll,
            -yaw,
            [q[0], q[1], -q[2], -q[3]],
        )

    def read_all(self):
        """Read raw accel and gyro data."""
        # 闁告梻濞€閳ь剛鍠庣€?
        accel = self._read_word_array(0x3B, 6)
        ax = (accel[0] << 8) + accel[1]
        ay = (accel[2] << 8) + accel[3]
        az = (accel[4] << 8) + accel[5]
        if ax >= 0x8000: ax -= 0x10000
        if ay >= 0x8000: ay -= 0x10000
        if az >= 0x8000: az -= 0x10000
        
        # 闂傚嫧鍋撻柧鏄忔〃閸?
        gyro = self._read_word_array(0x43, 6)
        gx = (gyro[0] << 8) + gyro[1]
        gy = (gyro[2] << 8) + gyro[3]
        gz = (gyro[4] << 8) + gyro[5]
        if gx >= 0x8000: gx -= 0x10000
        if gy >= 0x8000: gy -= 0x10000
        if gz >= 0x8000: gz -= 0x10000
        
        gx -= self.gyro_offset[0]
        gy -= self.gyro_offset[1]
        gz -= self.gyro_offset[2]
        
        return (ax, ay, az, gx, gy, gz)

    def get_angles(self):
        """Return zero-relative attitude and raw sensor data."""
        ax, ay, az, gx, gy, gz = self.read_all()

        if self.use_dmp:
            dmp_q = self.dmp.read_quaternion()
            if dmp_q:
                rel_q = self._relative_dmp_quaternion(dmp_q)
                pitch, roll, yaw = self.estimator._euler_from_quat(rel_q)
                pitch, roll, yaw, out_q = self._apply_output_axis_signs(pitch, roll, yaw, rel_q)
                qw, qx, qy, qz = out_q
                pitch, roll, yaw, qw, qx, qy, qz = self._fuse_mag_yaw(pitch, roll, yaw, qw, qx, qy, qz, gz / 65.5)
                self.last_dmp_attitude = (pitch, roll, yaw, qw, qx, qy, qz)
                return (pitch, roll, yaw, qw, qx, qy, qz, ax, ay, az, gx, gy, gz)
            if self.last_dmp_attitude:
                pitch, roll, yaw, qw, qx, qy, qz = self.last_dmp_attitude
                return (pitch, roll, yaw, qw, qx, qy, qz, ax, ay, az, gx, gy, gz)
        
        ax_g = ax / 16384.0
        ay_g = ay / 16384.0
        az_g = az / 16384.0
        
        gx_dps = gx / 65.5
        gy_dps = gy / 65.5
        gz_dps = gz / 65.5
        
        self.estimator.update(gx_dps, gy_dps, gz_dps, ax_g, ay_g, az_g)
        
        pitch, roll, yaw = self.estimator._euler_from_quat(self.estimator._relative_quat())
        pitch, roll, yaw, out_q = self._apply_output_axis_signs(
            pitch,
            roll,
            yaw,
            self.estimator._relative_quat(),
        )
        qw, qx, qy, qz = out_q
        pitch, roll, yaw, qw, qx, qy, qz = self._fuse_mag_yaw(pitch, roll, yaw, qw, qx, qy, qz, gz_dps)
        return (pitch, roll, yaw, qw, qx, qy, qz, ax, ay, az, gx, gy, gz)
        
        # 闁稿繑濞婇弫顓熺┍椤旂⒈妲? 缂傚倵鏅滈弬浣烘偘閵夈儰缂?(闁哄啫顑堝ù?0閹烘娊宕ｅΟ鍝勵嚙270閹?闁?缂傚倵鏅滈弬?1/3)
        # 濠碘€冲€归悘澶愬籍鐎ｎ厽绁?0閹烘娊宕ｅΟ鍝勵嚙270閹烘娊鏁嶇仦钘夌仧缂傚倵鏅滈弬?= 90/270 = 1/3
        scale = 1.0 / 3.0 * 10
        pitch *= scale
        roll *= scale
        yaw *= scale
        
        return (pitch, roll, yaw, ax, ay, az, gx, gy, gz)


# ============ UDP闁哄牆绉存慨鐔煎闯?============
class SensorServer:
    def __init__(self, ip='192.168.66.5', port=8888):
        self.ip = ip
        self.port = port
        self.mpu = MPU6050()
        self.sonar = Sonar()
        self.running = True
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((ip, port))
        self.sock.settimeout(0.1)
        
        print(f"\nServer started: {ip}:{port}")
        print("Sending attitude, quaternion, accel, gyro, and sonar distance")

    def run(self):
        client_addr = None
        last_time = time.time()
        frame_count = 0
        
        print("\nStart sending data (Ctrl+C to stop)")
        print("-" * 60)
        
        try:
            while self.running:
                try:
                    data, addr = self.sock.recvfrom(1024)
                    if data == b'get_data':
                        client_addr = addr
                except socket.timeout:
                    pass
                
                if client_addr:
                    pitch, roll, yaw, qw, qx, qy, qz, ax, ay, az, gx, gy, gz = self.mpu.get_angles()
                    distance = self.sonar.getDistance()
                    
                    data = struct.pack('!14f', 
                        pitch, roll, yaw,
                        qw, qx, qy, qz,
                        ax, ay, az,
                        gx, gy, gz,
                        float(distance)
                    )
                    self.sock.sendto(data, client_addr)
                    
                    frame_count += 1
                    if frame_count % 10 == 0:
                        print(f"Pitch: {pitch:6.1f} deg  Roll: {roll:6.1f} deg  Yaw: {yaw:8.1f} deg  Distance: {distance:5.0f} mm")
                        print(self.mpu.mag_debug_text())
                
                dt = time.time() - last_time
                sleep_time = 0.01 - dt
                if sleep_time > 0:
                    time.sleep(sleep_time)
                last_time = time.time()
                
        except KeyboardInterrupt:
            print("\nServer stopped")
        finally:
            self.sock.close()


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--mag-cal":
        seconds = 30
        if len(sys.argv) >= 3:
            try:
                seconds = int(sys.argv[2])
            except ValueError:
                pass
        bus = smbus.SMBus(1)
        mag = Magnetometer(bus)
        mag.calibrate_hard_soft_iron(seconds)
    else:
        server = SensorServer()
        server.run()
