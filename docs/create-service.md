# Systemd 服务配置

以下服务文件存放于 `/etc/systemd/system/`

---

## set-eth-speed.service

设置网口速度以匹配。

```ini
[Unit]
Description=Set Ethernet Speed to 100M Full Duplex
After=network.target
Before=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/sbin/ethtool -s eth0 speed 100 duplex full autoneg off
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

### 安装启用

```bash
sudo nano /etc/systemd/system/set-eth-speed.service
sudo systemctl daemon-reload
sudo systemctl enable set-eth-speed.service
sudo systemctl start set-eth-speed.service
```

### 验证状态

```bash
sudo systemctl status set-eth-speed.service
```

## tcar.service

设置网口速度以匹配。

```ini
[Unit]
Description=tCar Service
After=multi-user.target
Wants=multi-user.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/tCar
ExecStart=/usr/bin/python3 /home/pi/tCar/init.py
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 安装启用

```bash
sudo nano /etc/systemd/system/tcar.service
sudo systemctl daemon-reload
sudo systemctl enable tcar.service
sudo systemctl start tcar.service
```

### 验证状态

```bash
sudo systemctl status tcar.service
```
