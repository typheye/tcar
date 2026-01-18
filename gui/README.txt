sudo apt update
sudo apt upgrade
sudo apt install python3-numpy
sudo apt install python3-pil
sudo apt install python3-smbus
sudo apt-get install ttf-wqy-zenhei ttf-wqy-microhei
sudo apt install fonts-freefont-ttf
sudo /usr/bin/python3 /home/pi/gui/main.py

scp -r E:\DataFiles\raszeropi2w\gui pi@192.168.137.63:
sudo systemctl stop gui-app.service
sudo systemctl start gui-app.service

sudo nano /etc/systemd/system/gui-app.service

```
[Unit]
Description=GUI Application Service
After=multi-user.target
Wants=multi-user.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/gui
ExecStart=/usr/bin/python3 /home/pi/gui/main.py
Restart=on-failure
RestartSec=5
# 对于无桌面环境，移除图形相关的环境变量
Environment=PYTHONUNBUFFERED=1

# 如果需要硬件访问，确保用户有权限
# 标准输出重定向到系统日志
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

# 设置正确的权限
sudo chmod 644 /etc/systemd/system/gui-app.service

# 重新加载systemd配置
sudo systemctl daemon-reload

# 启用服务（开机自启）
sudo systemctl enable gui-app.service

# 立即启动服务
sudo systemctl start gui-app.service