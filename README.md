<div align="center">

# tCarKit · PC App

**Linux / Windows 共用桌面控制端 — Home、Vision、Performance、Sensors、OOBE**

</div>

以原 linux-pc 为最新功能基线，共享所有业务页面、设备协议和资源。
Windows 的主题、标题栏、任务栏集成与 Linux 的 OpenGL/窗口集成由
`src/tcarkit/platform_support.py` 统一调度。需要 Python 3.11，推荐 Conda。

## 一套命令，按宿主平台构建

从 pc-app 根目录执行：

| 操作 | Linux | Windows（CMD / PowerShell） |
| --- | --- | --- |
| 创建或更新环境 | `bash scripts/pc.sh setup` | `scripts\pc.cmd setup` |
| 开发运行 | `bash scripts/pc.sh run` | `scripts\pc.cmd run` |
| 原生打包 | `bash scripts/pc.sh build` | `scripts\pc.cmd build` |
| 安装并注册启动项 | `bash scripts/pc.sh install` | `scripts\pc.cmd install` |
| 清理构建缓存 | `bash scripts/pc.sh clean` | `scripts\pc.cmd clean` |
| 回归检查 | `bash scripts/pc.sh test` | `scripts\pc.cmd test` |

PowerShell 中使用 `./scripts/pc.cmd`。也可以直接运行
`python scripts/manage.py <操作>`。默认自动选择已有的 `tcar` Conda 环境，
首次运行需先执行 Setup；Setup 仅安装依赖，之后再运行或构建。
已有 Python/venv 环境可安装 `requirement.txt` 后加 `--current-env`，
例如 `python scripts/manage.py build --current-env`。支持带空格的项目目录。

VS Code 提供相同的 Setup / Play / Build / Install / Clean / Test 任务，
按操作系统切换包装脚本，不含任何固定用户名或 Python 路径。
旧 `build.sh`、`build.ps1`、`setup-conda.sh/.bat`、`clean.sh/.bat` 保留为薄包装。

Linux 产物为 `dist/tCarKit`，Windows 为 `dist/tCarKit.exe`。
PyInstaller 在目标系统本机构建，Windows 的图标和版本资源自动启用；
版本来源统一为 `src/tcarkit/metadata.json`。
GitHub Actions 在 `pc-app` 分支使用 Linux/Windows runner 分别测试和构建。

## 安装与启动项

`build --install` 可构建后安装；`install --desktop` 可额外创建桌面快捷方式。

- Linux：程序和图标安装至 `${XDG_DATA_HOME:-~/.local/share}/tcarkit/`；
  应用菜单为对应 `applications/tcarkit.desktop`，已有桌面快捷方式自动更新。
- Windows：安装至 `%LOCALAPPDATA%\Programs\tCarKit\`，创建开始菜单快捷方式；
  `--desktop` 或已有快捷方式时更新桌面快捷方式。更新前请关闭已运行的 EXE。

构建先在临时目录完成，成功后才替换 dist；失败会保留上一版。
Clean 默认保留 dist 和已安装程序，`clean --all` 才额外删除 dist。
安装位置独立于源码和构建目录，移动项目或清理缓存不会使启动项消失。

## 页面

| 页面 | 功能 |
| --- | --- |
| Home | 3D 姿态、方向轴、轨迹与超声障碍物 |
| Vision | 视频、指南针、小地图与电量 HUD |
| Performance | 4B 资源、运行时间与延迟 |
| Sensors | 传感器表格、图表、采样、CSV 导出与临时显示零偏 |
| OOBE | 设备信息、电池、账号与两轴云台实时校准；由 4B 保存并执行 |

通过 ESP32 `http://192.168.66.1/test` 自动发现 Core host。
配置和调试偏好沿用 `QSettings("tCar", "tCarKit")`，无需迁移已有用户设置。

## 仓库迁移

pc-app 沿用 linux-pc 的完整 Git 历史，开发分支为 `pc-app`。
迁移机器保留 `linux-pc -> pc-app` 目录兼容链接；旧 win-pc 仓库保留作历史参考，
后续两端功能只在 pc-app 维护。此次未推送远程或删除旧 Windows 历史。

更多约束见 [开发指南](docs/developer-guide.md)。
