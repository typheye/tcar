# tCar Core 服务安装

服务运行于 `tcar-core_env`，代码目录为 `/home/pi/tCarCore`。日志直接写入 systemd journal，不在项目目录内保存 unit 文件。

## 安装服务

```bash
sudo tee /etc/systemd/system/tcar-core.service >/dev/null <<'EOF'
[Unit]
Description=tCar Core Service
After=local-fs.target systemd-udev-settle.service network-online.target
Wants=network-online.target

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
