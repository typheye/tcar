# 设备初始化与云台校准（OOBE）

4B 是设备配置的唯一保存与执行端。Linux tCarKit 的 `File → Open → OOBE`
编辑配置，Zero 2 W 通过 4B RPC 使用相同的电池数据和舵机控制逻辑。

## 保存位置与启动

运行配置保存在 `/var/lib/tcar-core/device.json`，与代码部署目录分离。
systemd unit 使用 `StateDirectory=tcar-core` 创建数据目录。开发运行可设置
`TCAR_DEVICE_CONFIG=/absolute/path/device.json`，选择可写的测试文件。

首次没有文件时，继承 `media/servo_config.yaml` 的默认脉宽和现有限位，电池
默认 6.4–8.4 V，参考满电续航 129.5 分钟，应用账号为 `tcar` / `admin123`。
这些是初始化缺省值；第一次保存后以设备配置为准。损坏或未知版本的文件会
明确报错并阻止启动，避免静默覆盖校准结果。

配置带 `schema_version` 和递增 `revision`。保存时校验旧版本号，拒绝覆盖
其他客户端已经更新的配置；需要重新读取再保存。写入采用同目录临时文件、
fsync 和原子替换，文件权限 0600。密码仅保存 PBKDF2-SHA256 加盐哈希。

## 重新校准水平舵机 2

1. 打开 OOBE，点击 `Start calibration`。4B 停止底盘运动、停止云台速度命令，
   暂时独占云台。手柄和 Zero 2 W 的云台命令被屏蔽。
2. 缓慢拖动 **Servo 2 — pan** 的滑块，也可用数字框的箭头按 1 µs 微调。
   `Commanded` 是已发送的目标脉宽；设备没有实际轴位置反馈。
3. 对准机械中心后点击 `Set default here`；分别找到安全行程两端并点击
   `Set min here`、`Set max here`。不要移动到机械卡死位置。
4. 可用 `Go to default` 验证中心。滑块在校准模式允许越过旧的软件限位，
   绝对范围始终为 500–2500 µs，服务器限制每次步进 ≤40 µs、速度 ≤400 µs/s。
5. 点击 `Save and apply to 4B` 保存，或 `Stop / release control` 结束预览。
   离开标签页或退出程序会结束会话；断线后最多 5 秒超时回收，R2 也能取消。
   未保存的限位和默认值不会写入设备；越过已保存限位的预览位置会缓慢收回。

最小值、默认值、最大值必须满足 `500 ≤ min ≤ default ≤ max ≤ 2500`，且
`min < max`。默认值作为启动回中、R3 回中、自检返回点以及 2 号舵机水平角的
零点；手柄、RPC、Zero 2 W 与自检统一遵守限位。

## 电池与账号

支持 2S 电池的空电、满电电压（5.8–8.8 V，至少相差 0.2 V）及满电参考续航
（分钟）。4B 按配置计算并滤波电量；改阈值时立即重新计算当前电量。
`remaining_minutes = full_runtime_minutes × percent / 100` 为参考估算。
Zero 2 W 优先使用该字段，仅连接旧版 4B 时才使用旧的本地功耗估算。

账号用于 tCar 应用登录，与 Linux/SSH 账号无关。新密码留空保留原密码，
修改时至少 8 个字符。保存后新账号立即生效，旧登录令牌失效；tCarKit 同步
本机原有的记住账号设置，OOBE 后续请求使用新账号重新登录。
首次设置完成后勾选 `Device setup complete` 并保存，后续连接不再自动打开 OOBE。

## API

`POST /api/login` 保留原来的 `status`，增加有效期一小时的 `token`。
下列接口均要求 `Authorization: Bearer <token>`：

| 请求 | 用途 |
| --- | --- |
| `GET /api/v1/setup/config` | 读取配置，不返回密码哈希或会话密钥 |
| `POST /api/v1/setup/config` | 提交配置及当前 revision，可带 calibration session |
| `POST /api/v1/setup/begin`，正文 `{}` | 获取独占 session 与当前命令位置 |
| `POST /api/v1/setup/preview` | 提交 session、servo_id（1/2）、pulse_us；仅 session 则续租 |
| `POST /api/v1/setup/end` | 提交 session 释放控制 |

内部 RPC 增加 `GetDeviceConfig`。`GetBatteryStatus` 保留所有旧字段，并增加
`full_runtime_minutes`、`remaining_minutes` 和 `config_revision`。
HTTP telemetry 增加 `battery_full_runtime_minutes`、`battery_remaining_minutes`。
现有 25 浮点 UDP 遥测及 4 字段 battery_status 的布局保持兼容。

## 验证

在安装 PyYAML 的 Python 环境，从 raspi-4b 仓库根目录运行：

```sh
python -m unittest discover -s tests -v
```

测试以模拟 I2C 总线运行，覆盖配置恢复、错误写入回滚、版本冲突、密码与令牌、
HTTP 配置接口、舵机限位与校准速度、超时与急停释放、电池与 RPC。测试不会操作实车。
