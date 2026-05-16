# Systemd 服务配置

以下服务文件存放于 `/etc/systemd/system/`

---

## set-eth-speed.service

设置网口速度以匹配。

```ini
[Unit]
Description=Force Ethernet to 100M Full Duplex
After=sys-subsystem-net-devices-eth0.device
Before=network.target
Requires=sys-subsystem-net-devices-eth0.device

[Service]
Type=oneshot
ExecStart=/bin/bash -c '\
    COUNTER=0; \
    while [ $COUNTER -lt 30 ]; do \
        if [ -f /sys/class/net/eth0/carrier ] && [ $(cat /sys/class/net/eth0/carrier) -eq 1 ]; then \
            /usr/sbin/ethtool -s eth0 speed 100 duplex full autoneg off; \
            echo "Ethernet set to 100M Full Duplex"; \
            exit 0; \
        fi; \
        sleep 1; \
        COUNTER=$((COUNTER+1)); \
    done; \
    echo "Timeout: No Ethernet cable detected"'
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
