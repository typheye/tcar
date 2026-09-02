<div align="center">

# tCar · ESP32 Router

**车载 SoftAP、DHCP、NAT 与设备发现固件**

[![Platform](https://img.shields.io/badge/Platform-ESP32--S3-orange.svg)]()
[![Language](https://img.shields.io/badge/Language-C-blue.svg)]()
[![Status](https://img.shields.io/badge/Status-Active-brightgreen.svg)]()

</div>

ESP32 固件提供 `Typheye Car 0000` SoftAP、DHCP、可选 STA/NAT、设备发现 `/test`、管理 API 和嵌入式 Web UI。

## 接口

| 路径 | 作用 |
| --- | --- |
| `/test` | 简洁设备发现和 Core host 地址 |
| `/api/state` | 完整路由器、配置和设备状态 |
| `/api/scan` | APSTA 后台全信道 WLAN 扫描 |
| `/api/wifi` | 保存 STA profile |

修改后使用 ESP-IDF 构建；必须在确认串口日志后再刷写。扫描会在信道之间返回 AP 主信道，以降低对车内连接的影响。
