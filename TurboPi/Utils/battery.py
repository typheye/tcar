#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
电池/供电电压监测脚本 - 适用于 SSH 远程调用

调用方式:
    ssh -q -t pi@192.168.166.100 "sudo python3 /home/pi/TurboPi/Utils/battery.py"
    ssh -q -t pi@192.168.166.100 "sudo python3 /home/pi/TurboPi/Utils/battery.py --debug"

重要输出约定:
    1. JSON 输出中不出现 null / None。
    2. 电压、电量、单节电压等浮点值无效时输出 0.0。
    3. 样本数、raw 值等整数值无效时输出 0。
    4. 状态类字段使用明确字符串，例如 usb_power、battery_2s、unknown。
"""

import argparse
import json
import statistics
import sys
import time

sys.path.append("/home/pi/TurboPi/")

try:
    import HiwonderSDK.Board as Board
except Exception as e:
    Board = None
    BOARD_IMPORT_ERROR = str(e)
else:
    BOARD_IMPORT_ERROR = ""


class BatteryConfig:
    # 2S 18650 Li-ion 总电压参考范围
    # 满电理论 8.4V，考虑负载和板载误差，8.2V 以上按 100% 处理
    FULL_VOLTAGE = 8.2
    EMPTY_VOLTAGE = 6.2
    CRITICAL_VOLTAGE = 6.0

    # 物理可信范围
    # USB 供电时可能读到 4.x~5.x；2S 电池正常不应超过 8.5V
    USB_MIN_VOLTAGE = 4.2
    USB_MAX_VOLTAGE = 5.95
    BATTERY_MIN_VOLTAGE = 5.8
    BATTERY_MAX_VOLTAGE = 8.6

    # 采样参数
    SAMPLING_INTERVAL = 0.02
    SAMPLE_COUNT = 30
    MIN_VALID_SAMPLES = 5

    # 抗异常参数
    # 大于该值直接视作坏样本。你的实测中 654xx 会变成 65V，应直接丢弃。
    HARD_MAX_VALID_VOLTAGE = 10.0
    HARD_MIN_VALID_VOLTAGE = 3.0

    # 围绕中位数做二次过滤，抵抗 USB 抖动和偶发尖峰
    # USB 样本波动较大，所以窗口不能太窄。
    OUTLIER_WINDOW_VOLTAGE = 0.8


def sanitize_for_json(value):
    """递归清理返回对象，保证 JSON 中绝不出现 null。

    注意:
        Python 内部仍可以用 None 表示无效值；
        输出前统一转换，避免上游程序收到 null。
    """
    if value is None:
        return 0
    if isinstance(value, dict):
        return {str(k): sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_for_json(v) for v in value]
    if isinstance(value, tuple):
        return [sanitize_for_json(v) for v in value]
    return value


class BatteryMonitor:
    def __init__(self, debug=False):
        self.config = BatteryConfig()
        self.debug = debug

    def _debug(self, message):
        if self.debug:
            print(message, file=sys.stderr)

    def read_raw_mv(self):
        """读取 Board.getBattery() 原始值。

        正常情况下该值近似是 mV，例如:
            USB: 4360~5849
            2S 电池: 7966~8118

        偶发 654xx 属于坏样本，应在后续过滤。
        """
        if Board is None:
            raise RuntimeError(f"无法导入 HiwonderSDK.Board: {BOARD_IMPORT_ERROR}")

        raw = Board.getBattery()
        if raw is None:
            return None

        try:
            return int(raw)
        except Exception:
            return None

    def raw_to_voltage(self, raw_mv):
        """将原始 mV 转换为 V。"""
        return raw_mv / 1000.0

    def is_physically_valid(self, voltage):
        """判断是否在物理可信范围内。"""
        return (
            voltage is not None
            and self.config.HARD_MIN_VALID_VOLTAGE
            <= voltage
            <= self.config.HARD_MAX_VALID_VOLTAGE
        )

    def collect_samples(self):
        """采集样本，并丢弃物理不可能的读数。"""
        valid_samples = []
        rejected_samples = []

        for _ in range(self.config.SAMPLE_COUNT):
            raw = self.read_raw_mv()
            voltage = None if raw is None else self.raw_to_voltage(raw)

            sample = {
                "raw": 0 if raw is None else raw,
                "voltage": 0.0 if voltage is None else voltage,
            }

            if raw is None:
                sample["reason"] = "raw_none"
                rejected_samples.append(sample)
            elif not self.is_physically_valid(voltage):
                sample["reason"] = "out_of_physical_range"
                rejected_samples.append(sample)
            else:
                valid_samples.append(sample)

            time.sleep(self.config.SAMPLING_INTERVAL)

        return valid_samples, rejected_samples

    def filter_samples(self, valid_samples):
        """使用中位数和窗口过滤进一步去除尖峰，然后返回稳定电压。"""
        if len(valid_samples) < self.config.MIN_VALID_SAMPLES:
            return None, [], None

        voltages = [s["voltage"] for s in valid_samples]
        median_voltage = statistics.median(voltages)

        # 围绕中位数保留样本；窗口较宽，避免 USB 供电时被过度过滤。
        filtered = [
            s
            for s in valid_samples
            if abs(s["voltage"] - median_voltage) <= self.config.OUTLIER_WINDOW_VOLTAGE
        ]

        # 如果过滤后样本过少，退回使用全部有效样本。
        if len(filtered) < self.config.MIN_VALID_SAMPLES:
            filtered = valid_samples

        filtered_voltages = [s["voltage"] for s in filtered]

        # 使用“截尾均值”：如果样本足够多，去掉最高/最低各 10%，再求平均。
        sorted_voltages = sorted(filtered_voltages)
        if len(sorted_voltages) >= 10:
            cut = max(1, int(len(sorted_voltages) * 0.1))
            trimmed = sorted_voltages[cut:-cut]
        else:
            trimmed = sorted_voltages

        stable_voltage = statistics.mean(trimmed)

        return stable_voltage, filtered, median_voltage

    def detect_power_source(self, voltage):
        """区分 USB 5V 供电、2S 电池供电或未知状态。"""
        if voltage is None:
            return "unknown"

        if self.config.USB_MIN_VOLTAGE <= voltage <= self.config.USB_MAX_VOLTAGE:
            return "usb_5v"

        if (
            self.config.BATTERY_MIN_VOLTAGE
            <= voltage
            <= self.config.BATTERY_MAX_VOLTAGE
        ):
            return "battery_2s"

        return "unknown"

    def calculate_battery_percent(self, voltage, power_source):
        """只在 2S 电池供电时计算电量百分比。

        USB 供电或未知供电时返回 0.0，不返回 None。
        """
        if power_source != "battery_2s":
            return 0.0

        if voltage <= self.config.EMPTY_VOLTAGE:
            return 0.0
        if voltage >= self.config.FULL_VOLTAGE:
            return 100.0

        voltage_range = self.config.FULL_VOLTAGE - self.config.EMPTY_VOLTAGE
        percent = ((voltage - self.config.EMPTY_VOLTAGE) / voltage_range) * 100.0
        return max(0.0, min(100.0, percent))

    def get_status(self, voltage, percent, power_source):
        if power_source == "usb_5v":
            return "usb_power"

        if power_source != "battery_2s":
            return "unknown"

        if voltage <= self.config.CRITICAL_VOLTAGE or percent < 10:
            return "critical"
        if percent < 30:
            return "warning"
        if percent < 80:
            return "normal"
        return "full"

    def get_detailed_info(
        self,
        voltage,
        percent,
        power_source,
        valid_samples,
        rejected_samples,
        median_voltage,
    ):
        raw_values = [s["raw"] for s in valid_samples if s["raw"] > 0]

        if power_source == "battery_2s":
            single_voltage = voltage / 2.0
            battery_type = "2S_18650_Li-ion"

            if percent < 20:
                warning_msg = "电量过低，请及时充电"
            elif percent < 30:
                warning_msg = "电量较低，建议充电"
            else:
                warning_msg = "运行正常"

        elif power_source == "usb_5v":
            single_voltage = 0.0
            battery_type = "USB_5V"
            warning_msg = (
                "当前为 USB/5V 供电，不按 2S 电池估算电量，battery 固定输出 0.0"
            )

        else:
            single_voltage = 0.0
            battery_type = "unknown"
            warning_msg = (
                "电压不在 USB 或 2S 电池的可信范围内，请检查供电/接线/ADC 读数"
            )

        return {
            "single_voltage": round(single_voltage, 2),
            "warning": warning_msg,
            "battery_type": battery_type,
            "raw_min": min(raw_values) if raw_values else 0,
            "raw_max": max(raw_values) if raw_values else 0,
            "raw_median": (
                int(round(median_voltage * 1000)) if median_voltage is not None else 0
            ),
            "valid_samples": len(valid_samples),
            "rejected_samples": len(rejected_samples),
        }

    def measure(self):
        start_time = time.time()

        try:
            valid_samples, rejected_samples = self.collect_samples()
            voltage, filtered_samples, median_voltage = self.filter_samples(
                valid_samples
            )

            if voltage is None:
                return {
                    "success": False,
                    "error": "测量失败：有效样本不足",
                    "voltage": 0.0,
                    "battery": 0.0,
                    "status": "unknown",
                    "power_source": "unknown",
                    "samples": len(valid_samples) + len(rejected_samples),
                    "valid_samples": len(valid_samples),
                    "rejected_samples": len(rejected_samples),
                    "measurement_time": round(time.time() - start_time, 3),
                    "detailed": {
                        "single_voltage": 0.0,
                        "warning": "未采集到足够有效电压样本，请检查 I2C/供电/Board.getBattery()",
                        "battery_type": "unknown",
                        "raw_min": 0,
                        "raw_max": 0,
                        "raw_median": 0,
                        "valid_samples": len(valid_samples),
                        "rejected_samples": len(rejected_samples),
                        "rejected_examples": rejected_samples[:5],
                    },
                }

            power_source = self.detect_power_source(voltage)
            battery_percent = self.calculate_battery_percent(voltage, power_source)
            status = self.get_status(voltage, battery_percent, power_source)

            detailed_info = self.get_detailed_info(
                voltage=voltage,
                percent=battery_percent,
                power_source=power_source,
                valid_samples=filtered_samples,
                rejected_samples=rejected_samples,
                median_voltage=median_voltage,
            )

            result = {
                "success": True,
                "voltage": round(voltage, 2),
                "battery": round(battery_percent, 1),
                "status": status,
                "power_source": power_source,
                "samples": len(valid_samples) + len(rejected_samples),
                "valid_samples": len(filtered_samples),
                "rejected_samples": len(rejected_samples),
                "measurement_time": round(time.time() - start_time, 3),
                "detailed": detailed_info,
            }

            if self.debug:
                result["debug"] = {
                    "board_file": (
                        getattr(Board, "__file__", "unknown")
                        if Board is not None
                        else ""
                    ),
                    "valid_raw_values": [s["raw"] for s in valid_samples],
                    "filtered_raw_values": [s["raw"] for s in filtered_samples],
                    "rejected_samples": rejected_samples,
                }

            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "voltage": 0.0,
                "battery": 0.0,
                "status": "unknown",
                "power_source": "unknown",
                "samples": 0,
                "valid_samples": 0,
                "rejected_samples": 0,
                "measurement_time": round(time.time() - start_time, 3),
                "detailed": {
                    "single_voltage": 0.0,
                    "warning": "测量异常",
                    "battery_type": "unknown",
                    "raw_min": 0,
                    "raw_max": 0,
                    "raw_median": 0,
                    "valid_samples": 0,
                    "rejected_samples": 0,
                },
            }


def main():
    parser = argparse.ArgumentParser(description="TurboPi battery/power monitor")
    parser.add_argument("--debug", action="store_true", help="输出调试信息")
    args = parser.parse_args()

    monitor = BatteryMonitor(debug=args.debug)
    result = monitor.measure()

    # 最终输出前再做一层递归兜底，保证 JSON 中不会出现 null。
    safe_result = sanitize_for_json(result)
    print(json.dumps(safe_result, ensure_ascii=False))

    # 只有确认是 2S 电池供电且电量严重不足时才返回非 0。
    # USB 供电时 battery 固定为 0.0，但 power_source 是 usb_5v，不触发低电量退出。
    if (
        safe_result.get("success")
        and safe_result.get("power_source") == "battery_2s"
        and float(safe_result.get("battery", 0.0)) < 15.0
    ):
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        result = {
            "success": False,
            "error": "测量被中断",
            "voltage": 0.0,
            "battery": 0.0,
            "status": "unknown",
            "power_source": "unknown",
            "samples": 0,
            "valid_samples": 0,
            "rejected_samples": 0,
            "measurement_time": 0.0,
            "detailed": {
                "single_voltage": 0.0,
                "warning": "测量被中断",
                "battery_type": "unknown",
                "raw_min": 0,
                "raw_max": 0,
                "raw_median": 0,
                "valid_samples": 0,
                "rejected_samples": 0,
            },
        }
        print(json.dumps(result, ensure_ascii=False))
