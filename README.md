<div align="center">

# tCarKit · Win-PC

**Windows 桌面控制端 — Home、Performance 与 Vision**

[![Platform](https://img.shields.io/badge/Platform-Windows-blue.svg)]()
[![Language](https://img.shields.io/badge/Language-Python-blue.svg)]()
[![Status](https://img.shields.io/badge/Status-Active-brightgreen.svg)]()

</div>

Windows 控制端提供 Home、Performance 和 Vision 页面，通过路由器 `/test` 或 API 动态发现 Core host。视频和遥测连接失败时，界面应保持可操作并显示诊断信息。

## 页面

| 页面 | 功能 |
| --- | --- |
| Home | tCar 3D 姿态、障碍物和方向轴 |
| Performance | 4B CPU、内存、温度、延迟和运行时间 |
| Vision | 相机第一人称画面、指南针、小地图和电量 HUD |

## 数据链路

启动时通过 ESP32 `/test` 动态发现 Core host，再连接 4B HTTP/RPC/视频接口。网络或视频暂时不可用时，页面保留默认状态并显示诊断信息。

开发阶段不主动打包；配置和调试选项由应用自动保存。
