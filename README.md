<div align="center">

# tCar

**智能视觉小车控制系统 — 车载核心、路由器与桌面控制中心**

[![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%20%7C%20ESP32%20%7C%20Windows-informational.svg)]()
[![Language](https://img.shields.io/badge/Language-Python%20%7C%20C%20%7C%20Shell-blue.svg)]()
[![Status](https://img.shields.io/badge/Status-Active-brightgreen.svg)]()

</div>

tCar 是一套局域网遥控车系统，按设备职责拆分为 4B 车载核心、Zero2W 车载副机、ESP32 路由器和 Windows 控制端。

## 项目结构

| 目录 | 作用 |
| --- | --- |
| `raspi-4b/` | 主控、传感器、电机、舵机、手柄、视频和 API/RPC |
| `raspi-z2w/` | Car Device 副机、摄像头转发和中枢界面数据 |
| `esp32-code/` | SoftAP、DHCP、NAT、设备发现和管理页面 |
| `win-pc/` | tCarKit 桌面控制端、Home/Performance/Vision |
| `aosp-app/` | Android 客户端实验代码 |
| `main/` | 公共资料和早期原型 |

## 网络拓扑

ESP32 提供 `Typheye Car 0000`（`192.168.66.1`）。Car Device、Core host 和控制端通过 AP 接入；Core host 地址由路由器设备表动态发现，不应在客户端写死。

## 部署原则

- 4B 核心必须脱离网络也能完成硬件初始化。
- 4B 自定义服务仅包括 `tcar-core.service`、`wlan-helper.service`、`set-eth-speed.service`。
- Zero2W 附加服务通过 `raspi-z2w/Car/toolbox/setup.sh` 安装。
- 不创建 `__init__.py`；代码目录使用显式路径启动。
- 修改后先做语法/静态检查，再部署；不自动刷写固件。

## 文档

- [4B 文档](raspi-4b/README.md)
- [Zero2W 文档](raspi-z2w/README.md)
- [Windows 控制端](win-pc/README.md)
- [ESP32 路由器](esp32-code/README.md)
