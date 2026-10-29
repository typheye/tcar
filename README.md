<div align="center">

# tCar · Core Host

**Raspberry Pi 4B 车载核心控制中心**

[![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%204B-red.svg)]()
[![Language](https://img.shields.io/badge/Language-Python%203.10-blue.svg)]()
[![Status](https://img.shields.io/badge/Status-Active-brightgreen.svg)]()

</div>

4B 是 tCar Core host，负责运动控制、MPU6050/HMC5883L、超声波、电池、舵机、RGB、手柄、视频和 RPC/API。

入口：`tCarCore/init.py`。安装服务文件位于 `tCarCore/toolbox/systemd/`，统一部署脚本为 `tCarCore/toolbox/setup.sh`。

## PS2 遥控

`Select + Mode` 切换 Trajectory Space：开启时单响，关闭时双响；提示音遵循
`Select + Y` 控制的静音状态。该模式每次启动 tCar Core 时默认关闭；切换以
按键边沿触发，长按不会连续切换。

## 部署与调试

Linux 使用 `scripts/with-raspi4b.sh`，Windows 使用
`scripts/with-raspi4b.bat`。两者支持相同的 `--reset`、`--ssh`、`--log`、
`--reboot` 和 `--format` 操作；VS Code 任务会按当前系统自动选择。

## 快速索引

| 路径 | 内容 |
| --- | --- |
| `tCarCore/init.py` | 唯一启动入口和生命周期装配 |
| `tCarCore/hardware/` | I2C、MPU、磁力计、电机、舵机、视频等驱动 |
| `tCarCore/server/core/` | 控制、遥测、生命周期和日志 |
| `tCarCore/server/api/server.py` | HTTP API :8080、视频和控制 |
| `tCarCore/server/rpc/server.py` | 内部 RPC :9030 |
| `tCarCore/toolbox/` | systemd unit、WLAN helper 和部署脚本 |
| `tCarCore/media/` | 舵机校准、网络参数和运行资源 |

## 服务

`tcar-core.service` 不依赖网络成功与否启动；`wlan-helper.service` 独立管理接口级 wpa_supplicant；`set-eth-speed.service` 配置有线链路。查看 [docs](docs/)。
