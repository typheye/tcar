# tCarKit PC 开发指南

## 共享源码与平台层

Home、Vision、Performance、Sensors、OOBE 及所有设备通信使用同一套源码。
`platform_support.py` 负责系统差异：

- Linux 在导入 OpenGL 前根据 Qt 后端与 DISPLAY 选择 EGL/GLX，保留用户显式设置。
- Linux 用 gsettings 查询主题；不可用时回退浅色。
- Windows 用注册表查询主题，使用 DWM 深色标题栏和固定任务栏 AppUserModelID。
- 窗口显示事件过滤器保留在 QApplication 对象上，防止被 Python 回收。

登录框沿用信号驱动交接：主窗口创建和显示后才隐藏登录框，避免 GNOME 焦点
切换通知。QSettings 的组织与应用名仍为 tCar / tCarKit，两平台各用 Qt 原生存储。

## 环境与统一任务

`scripts/manage.py` 仅使用 Python 标准库启动，解析当前系统和命令。
`pc.sh`、`pc.cmd` 负责找到初始 Python；默认操作会自动进入 tcar Conda 环境。
Conda 支持 PATH、CONDA_EXE、已激活环境及常见安装目录，无固定用户路径。
Setup 创建或更新 environment.yml；Run/Build 不隐式升级依赖。

已有 venv 或 CI 的 Python 环境使用 `--current-env`：
`python scripts/manage.py test --current-env`。
依赖从 requirement.txt 安装，两个系统使用同一个依赖清单。
安装、清理只使用标准库，不依赖 Qt 或 Conda。

VS Code 的 Setup/Play/Build/Install/Clean/Test 使用默认 Bash 命令及 Windows
覆盖配置。兼容包装脚本不包含独立业务逻辑。

## 原生打包与发布

统一 `src/tcarkit/tcarkit.spec`；Windows 自动启用 ICO、版本资源，
Linux 不使用 Windows 专属打包参数。所有 OpenGL.platform 后端显式收集，
避免动态导入在打包后丢失。图标、STL 和 metadata.json 随程序打包。
Windows 版本资源由 metadata.json 生成，无需维护另一份版本号。

构建使用 build/<platform>/ 下的临时输出，只有完整生成可执行文件才原子替换
dist/tCarKit 或 dist/tCarKit.exe。构建失败不删除已有发布文件。
Clean 默认仅删 build 与本项目 Python 缓存；--all 额外删除 dist。
不允许清理指向其他目录的符号链接。

## 独立安装与桌面集成

Install 复制程序和资源到用户数据目录，启动项只指向安装位置。
Linux 为 XDG_DATA_HOME/tcarkit（缺省 ~/.local/share/tcarkit）；
Windows 为 LOCALAPPDATA/Programs/tCarKit。无需管理员权限。

Linux 应用菜单条目保留以下属性：

```ini
Terminal=false
StartupNotify=false
StartupWMClass=tCarKit
Categories=Utility;
```

StartupNotify=false 避免 GNOME 将启动中的窗口长时间标记为 STARTING。
Windows 使用 WScript.Shell 创建标准开始菜单/桌面 .lnk。
可执行文件采用同目录临时文件替换。Linux 桌面条目更新时原位写入，以便桌面
目录监视器识别内容变化；安装时刷新索引并校验条目（工具可用时）。普通路径的
Exec 不加引号，包含特殊字符时使用 env 加路径参数，并添加 TryExec。
安装清理确认属于 tCarKit 的旧版重复条目，不修改其他应用的启动项。
VS Code Install 默认包含 --desktop，创建应用菜单项与桌面快捷方式。
旧安装的可执行文件不受 Clean 影响。

## OOBE 与传感器

OOBE 设置保存于 4B /var/lib/tcar-core/device.json，客户端通过认证 API 编辑。
首次未完成初始化时自动打开，也可通过 File → Open → OOBE 打开。
实时云台校准显式启动，离开页面释放控制，断线由 4B 的 5 秒租约回收；
操作与接口见 raspi-4b/docs/oobe.md。

Sensors 的 CSV 导出保留原始记录，临时 X/Y 加速度零偏仅影响图表显示。
后台遥测不能随页面切换暂停。

## 验证与 CI

`python scripts/manage.py test --current-env` 覆盖后端选择、主题隔离、
Windows/Linux 打包选项、原子发布、构建失败保留旧版、安装路径独立和清理边界。
本机可通过 `doctor` 检查选中环境和目标产物。
.github/workflows/pc-build.yml 在 Ubuntu 与 Windows 上分别测试并原生打包；
推送 pc-app 或向 pc-app 提 PR 时触发，也可手动运行。
Linux 本机测试不能代替 Windows 原生窗口、打包和 EXE 启动验证。

## 迁移与 Git

此目录由 linux-pc 整体移动而来，.git 和原有提交历史完整保留，工作分支 pc-app。
旧 linux-pc / win-pc 目录及兼容链接已移除，开发、任务与安装均使用 pc-app。
不要把旧 Windows 业务页面反向覆盖到共享源码。
