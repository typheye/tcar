# tCar Core 服务安装

服务运行于 `tcar-core_env`，代码目录为 `/home/pi/tCarCore`。日志直接写入 systemd journal，不在项目目录内保存 unit 文件。

## 安装服务

```bash
sudo tee /etc/systemd/system/tcar-core.service >/dev/null <<'EOF'
[Unit]
Description=tCar Core Service
After=local-fs.target systemd-udev-settle.service

[Service]
Type=simple
User=root
WorkingDirectory=/home/pi/tCarCore
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/home/pi/miniforge3/envs/tcar-core_env/bin/python /home/pi/tCarCore/init.py
Restart=on-failure
RestartSec=3
TimeoutStopSec=10
KillSignal=SIGTERM
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tcar-core

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable tcar-core.service
```

## tCar Tool WLAN 守护服务

```ini
[Unit]
Description=tCar Tool WLAN watchdog
After=wpa_supplicant.service

[Service]
Type=simple
User=root
ExecStart=/bin/sh /home/pi/tCarTool/network_watchdog.sh
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
```

启用 `tcar-tool.service` 后，tCar Core 不再依赖网络状态即可启动。

## WLAN 自动连接

设备使用系统 `wpa_supplicant + dhcpcd`，不依赖旧工具箱。为避免 dhcpcd
hook 在开机竞态下未拉起无线接口，可额外安装一个接口级单元：

```bash
sudo tee /etc/systemd/system/tcar-wlan.service >/dev/null <<'EOF'
[Unit]
Description=tCar WLAN connection
Requires=sys-subsystem-net-devices-wlan0.device
After=sys-subsystem-net-devices-wlan0.device wpa_supplicant.service dhcpcd.service
Wants=dhcpcd.service

[Service]
Type=simple
ExecStart=/sbin/wpa_supplicant -c/etc/wpa_supplicant/wpa_supplicant.conf -Dnl80211,wext -iwlan0
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable tcar-wlan.service
sudo systemctl restart tcar-wlan.service
sudo systemctl restart dhcpcd.service
```

按键长按网络重启仍保留，tCar Core 会调用 `wpa_cli reconfigure` 和
`systemctl restart dhcpcd.service`，并发出短提示音。

## 切换到 tCar Core

当前设备正式使用 tCar Core。旧 TurboPi 服务和设备端旧代码应移除，避免两个
进程同时占用 GPIO/I2C/PWM。`hw_wifi.service` 等网络服务不属于车辆控制核心，
不要停用。

```bash
sudo systemctl disable --now turbopi.service hw_find.service
sudo systemctl enable --now tcar-core.service
sudo rm -f /etc/systemd/system/turbopi.service
sudo systemctl daemon-reload
systemctl status tcar-core.service
```

## 查看日志

```bash
journalctl -u tcar-core.service -f
```

最近 200 行：

```bash
journalctl -u tcar-core.service -n 200 --no-pager
```

## 回退到 TurboPi

```bash
sudo systemctl disable --now tcar-core.service
sudo systemctl enable --now turbopi.service
```
