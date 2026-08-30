# 4B 开发指南

## 运行时分层

```text
tCarCore/init.py
  hardware/       物理设备单例与驱动
  server/core/    运动控制、生命周期、日志、遥测
  server/api/     外部 HTTP 与视频
  server/rpc/     内部低延迟 RPC
  toolbox/        systemd 与部署
  media/          只读校准和网络配置
```

## 硬件职责

| 模块 | 总线/接口 | 约束 |
| --- | --- | --- |
| MPU6050 | I2C | 启动校准，失败保留安全姿态 |
| HMC5883L | I2C | 磁力校准和航向只在驱动层补偿 |
| 电机 | 板载 I2C/PWM | 刹车必须将四轮同时置零 |
| 舵机 | 板载 PWM | 单例控制，回零分轴错峰 |
| 超声波 | GPIO/I2C 扩展 | LED 与测距共用驱动锁 |
| 摄像头 | V4L2/OpenCV | 采集线程与 API 解耦 |

## 配置

- `media/network.yaml`：WLAN 目标参数，仅供 helper 使用。
- `media/servo_config.yaml`：舵机出厂校准，只读。
- 运行时设置写入各服务自己的配置目录，不提交设备密钥。

## 验证

```bash
python -m py_compile init.py hardware/*.py server/**/*.py
systemctl is-active tcar-core.service wlan-helper.service set-eth-speed.service
journalctl -u tcar-core.service -b --no-pager
```
