# Zero2W 开发指南

## 设备 OOBE 配置

设备配置由 4B 统一保存，Linux tCarKit 的 OOBE 页面负责编辑。
Zero2W 的云台命令通过 4B 执行，自动使用最新的最小、最大及默认脉宽；
4B 校准会话期间会拒绝普通云台命令。
`GetBatteryStatus` 增加 `remaining_minutes`、`full_runtime_minutes` 和
`config_revision`，本机 GUI 直接显示 4B 的参考剩余续航（分钟转换为小时）。
旧版 4B 缺少剩余时间字段时保留本地功耗估算。RPC `GetDeviceConfig` 可读取
4B 的公开设备配置，不包含密码哈希。

## 运行链路

```text
tCar/init.py -> camera/status services -> router/API -> desktop clients
```

Zero2W 是 Car Device，不拥有 4B 的运动控制硬件；摄像头帧传输必须使用独立采集线程，不能阻塞状态接口。

## 服务

Linux 使用 `scripts/with-raspiz2w.sh`，Windows 使用
`scripts/with-raspiz2w.bat`，均支持 `--reset`、`--ssh`、`--log`、`--reboot`、
`--format` 和 `--help`。VS Code 任务自动选择对应平台命令。
脚本从 ESP32 `/test` 设备表中的 `Car device` 发现副机，将本地 `tCar/`
上传到 `/home/pi/tCar`，管理 `tcar.service`。本地缓存清理由
`bash scripts/clean.sh` 完成，上传会自动排除 `__pycache__` 和 `.pyc`。

`tCar/toolbox/setup.sh` 安装 `tcar.service` 和 `set-eth-speed.service`。服务日志统一进入 systemd journal。

```bash
systemctl status tcar.service set-eth-speed.service
journalctl -u tcar.service -f
```

## 网络故障

确认 `eth0` 与 WLAN 地址分别存在，再检查路由器设备表；不要在副机上写死 Core host 地址。
