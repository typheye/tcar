# Zero2W GUI 安装指南

## 概述
本指南将帮助您在 Raspberry Pi Zero 2 W 上安装并配置图形用户界面(GUI)应用，并将其设置为系统服务实现开机自启。

## 系统要求
- Raspberry Pi Zero 2 W
- Raspberry Pi OS（Raspbian）已安装
- 稳定的网络连接

## 安装流程

### 1. 系统更新与升级
```bash
sudo apt update
sudo apt upgrade -y
```

### 2. 安装依赖包
安装 Python 相关库和字体：
```bash
sudo apt install python3-numpy python3-pil python3-smbus -y
sudo apt-get install ttf-wqy-zenhei ttf-wqy-microhei -y
sudo apt install fonts-freefont-ttf -y
```

### 3. 应用准备
确保您的 GUI 应用位于正确路径：
- 主程序：`/home/pi/gui/main.py`
- 确保该文件存在并具有可执行权限：
```bash
chmod +x /home/pi/gui/main.py
```

### 4. 创建系统服务
创建服务配置文件：
```bash
sudo nano /etc/systemd/system/gui-app.service
```

在编辑器中添加以下内容：
```ini
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
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

按 `Ctrl+X`，然后按 `Y`，最后按 `Enter` 保存文件。

### 5. 配置服务权限
```bash
sudo chmod 644 /etc/systemd/system/gui-app.service
```

### 6. 启用并启动服务
```bash
# 重新加载 systemd 配置
sudo systemctl daemon-reload

# 启用开机自启
sudo systemctl enable gui-app.service

# 立即启动服务
sudo systemctl start gui-app.service
```

## 服务管理命令

### 检查服务状态
```bash
sudo systemctl status gui-app.service
```

### 停止服务
```bash
sudo systemctl stop gui-app.service
```

### 重启服务
```bash
sudo systemctl restart gui-app.service
```

### 查看服务日志
```bash
sudo journalctl -u gui-app.service -f
```

### 禁用开机自启
```bash
sudo systemctl disable gui-app.service
```

## 验证安装

1. 检查服务是否正常运行：
   ```bash
   systemctl is-active gui-app.service
   ```
   应该返回 `active`

2. 检查服务是否启用：
   ```bash
   systemctl is-enabled gui-app.service
   ```
   应该返回 `enabled`

3. 重启设备验证开机自启：
   ```bash
   sudo reboot
   ```

## 故障排除

### 常见问题

1. **服务启动失败**
   - 检查 Python 脚本路径是否正确
   - 确认 `/home/pi/gui/main.py` 文件存在
   - 查看详细错误日志：`sudo journalctl -u gui-app.service`

2. **权限问题**
   - 确保服务文件权限正确：`ls -l /etc/systemd/system/gui-app.service`
   - 确保应用目录权限正确：`chown -R pi:pi /home/pi/gui`

3. **依赖缺失**
   - 重新运行依赖安装命令
   - 检查 Python 库是否正确安装：`python3 -c "import numpy; import PIL; import smbus"`

### 日志位置
- 系统服务日志：`/var/log/syslog`
- 应用特定日志：`sudo journalctl -u gui-app.service`

## 注意事项
1. 确保您的 GUI 应用兼容 Raspberry Pi Zero 2 W 的硬件性能
2. 建议在安装前备份重要数据
3. 如果使用自定义显示设备，可能需要额外配置

---

**提示**：安装过程中如遇问题，请联系typheye@typheye.com。