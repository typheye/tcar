<div align="center">

# tCarKit · PC App

**tCar 桌面控制端 · Linux / Windows**

[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows-blue.svg)]()
[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)]()

</div>

tCarKit 是 tCar 的跨平台桌面客户端。Linux 和 Windows 共用同一套界面、
设备通信和数据处理代码，通过 ESP32 路由器自动发现 Raspberry Pi 4B Core host，
提供车辆状态监控、视频、传感器记录和设备初始化配置。

## 页面功能

| 页面 | 功能 |
| --- | --- |
| Home | 车辆 3D 姿态、方向轴、轨迹和超声障碍物 |
| Vision | 实时视频、指南针、小地图和电量 HUD |
| Performance | 4B 资源状态、运行时间和通信延迟 |
| Sensors | 传感器表格、曲线图表、采样频率设置和 CSV 导出 |
| OOBE | 设备名称、两轴云台实时校准、电池参数和应用账号 |

OOBE 的设备配置由 4B 保存并执行，Zero 2 W 使用 4B 提供的数据和控制结果。
图表中的临时加速度零偏仅用于显示，CSV 保留原始记录。

## 环境准备

需要 Python 3.11。推荐使用 Conda，并确保其命令可用。

在 pc-app 项目根目录执行对应系统的命令：

| 操作 | Linux | Windows CMD |
| --- | --- | --- |
| 创建或更新环境 | `bash scripts/pc.sh setup` | `scripts\pc.cmd setup` |
| 开发运行 | `bash scripts/pc.sh run` | `scripts\pc.cmd run` |
| 构建程序 | `bash scripts/pc.sh build` | `scripts\pc.cmd build` |
| 安装并创建桌面快捷方式 | `bash scripts/pc.sh install --desktop` | `scripts\pc.cmd install --desktop` |
| 清理构建缓存 | `bash scripts/pc.sh clean` | `scripts\pc.cmd clean` |
| 运行回归检查 | `bash scripts/pc.sh test` | `scripts\pc.cmd test` |
| 检查运行环境 | `bash scripts/pc.sh doctor` | `scripts\pc.cmd doctor` |

PowerShell 使用 `./scripts/pc.cmd`，例如：

```powershell
./scripts/pc.cmd setup
./scripts/pc.cmd run
```

Setup 创建或更新名为 `tcar` 的 Conda 环境，运行和构建命令会自动选择该环境。
Setup 不自动构建；日常运行和构建也不自动升级依赖。

已有 Python / venv 环境可使用：

```bash
python -m pip install -r requirement.txt
python scripts/manage.py run --current-env
python scripts/manage.py build --current-env
```

## VS Code 操作按钮

项目提供 Setup、Play、Build、Install、Clean、Test 六个任务。
任务根据当前系统自动选择 Bash 或 Windows CMD 包装脚本。

配合 `quzhen.tasks-button` 扩展，可在状态栏显示操作按钮。
所有任务保留 `label`、`icon.id` 和 `tooltip`；不要在调整命令时删除图标属性。
Build 为默认构建任务，Install 会创建应用菜单项及桌面快捷方式。

## 构建与安装

两个系统使用统一依赖和打包配置，在各自系统上生成原生程序：

| 构建平台 | 输出文件 | 默认安装位置 |
| --- | --- | --- |
| Linux | `dist/tCarKit` | `~/.local/share/tcarkit/` |
| Windows | `dist/tCarKit.exe` | `%LOCALAPPDATA%\Programs\tCarKit\` |

Linux 设置了 XDG_DATA_HOME 时，安装位置使用其下的 tcarkit 目录。
Windows 自动附加图标和版本资源，版本号统一取自
`src/tcarkit/metadata.json`。当前方案不提供 Linux 到 Windows 的交叉编译。

首次安装先执行 Build，再执行 Install，也可使用 `build --install --desktop`。
Install 只安装已有构建，不会隐式重新构建。

- Linux：注册应用菜单启动项，可创建可信桌面快捷方式；重复安装更新已有条目，
  清理可识别为 tCarKit 的旧版重复启动项。
- Windows：创建开始菜单快捷方式，`--desktop` 额外创建桌面快捷方式。
  更新前请关闭正在运行的已安装程序。
- 程序和启动项所需资源安装到独立目录，不依赖源码目录是否仍存在。
- 构建失败保留上一版 dist；Clean 默认保留 dist 和已安装程序。
- `clean --all` 额外删除 dist，仍保留已安装程序。

Linux 菜单未立即刷新时，先确认 Install 输出成功且程序已安装，
再尝试重新打开应用菜单。不要把构建输出目录当作长期安装目录。

## 连接与配置

电脑需能访问 ESP32 路由器 `http://192.168.66.1/test`。
客户端从设备表发现 Core host，再进行账号验证并连接视频和遥测接口。
4B 的 OOBE 功能要求部署支持配置接口的 tCarCore。

客户端偏好继续使用 `QSettings("tCar", "tCarKit")`，
由 Qt 在各平台使用原生存储位置。设备校准和电池等配置保存于 4B。

## 项目结构

```text
pc-app/
├── src/tcarkit/
│   ├── app.py                应用入口
│   ├── platform_support.py   Linux / Windows 系统适配
│   ├── ui/                   共享业务页面
│   ├── depends/              数据接收与 3D 渲染
│   ├── assets/               图标与车辆模型
│   ├── metadata.json         应用版本信息
│   └── tcarkit.spec          统一打包配置
├── scripts/                  统一管理命令与平台包装
├── tests/                    回归检查
├── .vscode/tasks.json        跨平台任务与按钮
├── .github/workflows/        双平台 CI
├── environment.yml
└── requirement.txt
```

所有桌面端功能统一在 pc-app 中维护，不依赖旧的 linux-pc / win-pc 目录。
GitHub Actions 的双平台工作流分别执行 Linux 和 Windows 测试及原生构建。
详细设计见 [开发指南](docs/developer-guide.md)。
