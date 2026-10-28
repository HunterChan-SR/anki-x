# anki-x

在终端里学习 Anki。保留 Anki 的记忆排程、词库和同步，提供开箱即用的键盘与鼠标界面。

支持 macOS、Windows 和 Linux。发行包自带运行环境，无需安装 Python、pip 或音频播放器。

## 安装

从 [Releases](https://github.com/HunterChan-SR/anki-x/releases) 下载与你的系统对应的压缩包，解压后运行安装入口：

| 系统 | 下载文件后缀 | 安装入口 |
| --- | --- | --- |
| macOS Apple Silicon | `macos-arm64.zip` | 双击 `Install anki-x.command` |
| macOS Intel | `macos-x64.zip` | 双击 `Install anki-x.command` |
| Windows x64 | `windows-x64.zip` | 双击 `Install anki-x.cmd` |
| Linux x64 | `linux-x64.zip` | 在解压目录执行 `sh install.sh` |

安装后打开新的终端运行：

```sh
anki-x
```

macOS 的用户应用目录、Windows 开始菜单和 Linux 应用菜单也会提供启动入口。可直接使用包内的 `Start anki-x` 入口体验便携版。

命令行安装（发布资产提供后可用）：

```sh
curl -fsSL https://raw.githubusercontent.com/HunterChan-SR/anki-x/codex/productization/install.sh -o /tmp/anki-x-install.sh
sh /tmp/anki-x-install.sh
```

Windows PowerShell：

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/HunterChan-SR/anki-x/codex/productization/install.ps1 -OutFile "$env:TEMP\anki-x-install.ps1"
& "$env:TEMP\anki-x-install.ps1"
```

安装器从本项目 Release 下载对应平台文件，校验 SHA-256，再安装到用户目录。无权限修改系统目录时也可使用便携包。当前为 `1.0.0rc1` 预发布版，平台验证和签名状态见对应 Release；不要把“可下载”当作操作系统签名认证。

## 第一次打开

1. anki-x 检查本机 Anki 与连接插件，已有配置会自动识别。
2. 没有 Anki 时，点击“下载并安装官方 Anki”；系统授权或首次账户提示在 Anki/系统窗口完成。
3. 缺少插件时，点击“安装 / 修复连接插件”。Anki 正在运行时需先正常退出；设置完成后可由 anki-x 启动。
4. 选择自己的牌组、导入 `.apkg`，或点击“体验词卡”验证完整学习流程。

体验词卡包含六个原创示例及英语发音，重复点击不会重复添加。不会随包分发你的个人词库。AnkiWeb 登录不是本地学习的前提。

已验证的 Anki 接入基线是 26.08、26.09.3。程序逐项检查必需 API，保留已有端口、密钥和插件用户文件；新安装只监听本机。自定义 Anki 数据目录或安装位置可在接入向导中选择。

Linux 首发范围为 x86_64/glibc 发行版，Anki 26.09.3 要求 glibc ≥ 2.35 和图形库；Ubuntu 22.04/24.04 可按系统包管理器补齐 `libxcb-xinerama0 libxcb-cursor0 libnss3 libxcb-icccm4 libxcb-keysyms1`。musl/Alpine、Windows ARM64 和 Linux ARM64 目前不作为已验收发行目标。macOS 需 13+；Windows 使用 Windows 10/11 x64。

## 学习

| 操作 | 按键 |
| --- | --- |
| 选择牌组 | ↑↓ / j k |
| 展开 / 收起 | → / ←，l / h，或空格 |
| 进入牌组 | Enter，或点击“开始学习” |
| 显示答案 | 空格 / Enter |
| 评分 | 1 忘记、2 吃力但想起、3 记得、4 轻松 |
| 重播 / 自动发音开关 | r / a |
| 撤销上一笔评分 | u |
| 详细释义 | d |
| 顶部标题开关 | t |
| 返回牌组 | Esc / b |
| 设置 / 帮助 | s / ? |
| 退出并记住位置 | q / Ctrl+C |

第一次启动打开主界面；后续恢复牌组展开状态、光标和有效的卡片正反面。账户分别记忆，过期卡片会重新读取 Anki 的可学队列。评分只有在 Anki 确认写入后才显示成功；没有收到结果的请求不会盲目重复提交。

## 常用命令

```sh
anki-x home                 # 强制返回主界面
anki-x setup                # 接入向导
anki-x review --deck "英语"
anki-x decks
anki-x stats
anki-x doctor               # 即使连接失败也能诊断
anki-x doctor --export      # 导出不含密钥/词卡正文的诊断
anki-x sync
anki-x update
anki-x rollback
anki-x uninstall            # 保留词库和设置
anki-x paths
```

## 升级、数据与恢复

安装使用独立版本目录，更新前验证新程序，保留上一版本以供 `rollback`。配置、界面位置和未确认操作记录位于各系统的用户目录，安装目录不会承载学习数据。`anki-x paths` 可查看实际位置。

0.2.x 源码版本会自动备份并迁移 `config.json` 与 `.state`。如果旧目录不再能自动定位，可首次启动时设置 `ANKI_X_LEGACY_HOME` 指向旧项目目录。迁移期间旧版必须正常退出。新旧配置均保留备份，不改写 Anki collection。

断线后打开界面按“检查未完成操作”。没有拿到操作编号时，先在 Anki 核对结果，再解除未确认状态；这不会重新提交评分。高级覆盖可使用 `ANKI_X_HOME`、`ANKI_X_STATE_DIR`、`ANKI_CONNECT_URL` 和已有的 `ANKI_API_KEY`。应用不上传卡片正文或诊断信息。

## 开发与验收

```sh
uv sync --frozen
uv run anki-x
uv run pytest -q
uv run python tools/build_release.py
uv run python tools/smoke_distribution.py
```

CI 在 macOS Apple Silicon/Intel、Windows x64、Linux x64 分别测试、构建和验证自包含安装。原生 Anki 测试使用 `anki==26.9.3`；首次接入测试另需 `aqt==26.9.3`，使用独立数据目录与唯一单实例标识，不连接个人账户。

```sh
python tools/smoke_pinned_scheduler.py
python tools/smoke_onboarding.py
```

跨平台 UI 测试覆盖首次向导、树形牌组、返回、退出恢复和设置。安装检查在空用户目录中执行打包后的二进制及安装后的命令入口。音频包含空输出设备自动验证，本机另验证真实声音设备。

## 许可与范围

anki-x 自有代码采用 [MIT](LICENSE)。第三方组件保留自己的许可证，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。随包 AnkiConnect 为官方固定提交，附 GPL 许可证及对应源码；Anki Desktop 从官方源独立下载安装。

当前重点支持文字、基础 Cloze 与词汇音频。图片遮挡、复杂 JavaScript 互动、视频和 GUI 自定义排程脚本请使用桌面 Anki。遇到问题可导出诊断信息并通过 [Issues](https://github.com/HunterChan-SR/anki-x/issues) 反馈。
