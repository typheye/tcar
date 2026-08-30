# Zero2W 开发指南

## 运行链路

```text
Car/init.py -> camera/status services -> router/API -> Win-PC
```

Zero2W 是 Car Device，不拥有 4B 的运动控制硬件；摄像头帧传输必须使用独立采集线程，不能阻塞状态接口。

## 服务

`Car/toolbox/setup.sh` 安装 `tcar.service` 和 `set-eth-speed.service`。服务日志统一进入 systemd journal。

```bash
systemctl status tcar.service set-eth-speed.service
journalctl -u tcar.service -f
```

## 网络故障

确认 `eth0` 与 WLAN 地址分别存在，再检查路由器设备表；不要在副机上写死 Core host 地址。
