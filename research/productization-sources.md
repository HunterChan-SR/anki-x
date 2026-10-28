# anki-x 产品化：Anki / AnkiConnect 一手资料核查

核查日期：2026-10-26（Asia/Shanghai）。本文件记录实现所需事实与据此提出的建议，不代表三端成品已经通过验收。

核查基线：Anki 官方 tag `26.09.3`；AnkiConnect 官方提交 `62fc13d107c2b02130e503749e9933495c6456fb`。后者已从本地只读 checkout 核对 HEAD 和 origin；所有产品结论仅使用官方文档、官方发布物或固定版本源码。本轮没有启动、修改或操作用户 Anki，也没有修改 anki-x 产品代码。

## 决策摘要

1. **客户端自包含打包可行，Anki 仍是独立的桌面依赖。** Anki 26.09.3 官方同时发布 macOS Apple/Intel DMG、Windows x64/ARM64 MSI、Linux x86_64/AArch64 tar.zst；安装器应按 OS/CPU 选定文件并校验 SHA-256。Windows 不是旧版 `.exe` 下载格式。见[官方附件列表](https://github.com/ankitects/anki/releases/expanded_assets/26.09.3)。
2. **旧版 Anki Launcher 的 AnkiProgramFiles 教程不能当作 26.09.3 安装契约。** 手册明确将那套程序目录下载/升级机制限定为 25.07–25.09.4；当前应依赖发布包及实际安装目录探测。见[程序文件说明](https://docs.ankiweb.net/manual/files#program-files)。
3. **固定 AnkiConnect 提交要求 Anki >= 26.08，维护者列出的测试矩阵是 26.08 / 26.09.3。** 不应由 `apiMajor == 1` 推导所有新版本兼容。见[固定提交 README](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/README.md)、[加载时版本检查](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/plugin/__init__.py)。
4. **没有自动端口发现或避让。** 插件只绑定配置的 IPv4 地址/端口；端口冲突后显示错误。CLI 应读取已有设置并验证身份，必要时在正常关闭 Anki 后协调新端口。见[web.py](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/plugin/web.py)、[插件启动](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/plugin/__init__.py)。
5. **保留配置的关键是 `meta.json.config`，不能只覆盖 `config.json`。** Anki 先读默认配置，再合并用户覆盖值；安装升级还需保留 `user_files` 和其他元数据。见[Anki 插件管理源码](https://github.com/ankitects/anki/blob/26.09.3/qt/aqt/addons.py#L713-L737)。
6. **隔离测试必须同时隔离目录和单实例 IPC 身份。** 使用临时 `-b` 目录，加唯一 `ANKI_SINGLE_INSTANCE_KEY`；单用 `-b` 可能复用同一用户已运行的 Anki。见[Anki IPC](https://github.com/ankitects/anki/blob/26.09.3/qt/aqt/__init__.py#L329-L388) 和[AnkiConnect 官方 GUI 测试](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/tools/smoke_gui.py)。

## 官方 Anki 26.09.3 下载与系统要求

下表链接及 SHA-256 来自[官方不可变 release](https://github.com/ankitects/anki/releases/tag/26.09.3) 的[附件列表](https://github.com/ankitects/anki/releases/expanded_assets/26.09.3)，非猜测的 URL。版本字符串在发布文件名中为 `26.09.3`，Python 包中规范化为 `26.9.3`。

| 平台 | 官方安装包 | 官方 SHA-256 |
| --- | --- | --- |
| macOS Apple Silicon | [anki-26.09.3-mac-apple.dmg](https://github.com/ankitects/anki/releases/download/26.09.3/anki-26.09.3-mac-apple.dmg) | `b36fe8f6c015a602feaf3ef38f5967c27c8964ee30a5c74ca2532225cf602345` |
| macOS Intel | [anki-26.09.3-mac-intel.dmg](https://github.com/ankitects/anki/releases/download/26.09.3/anki-26.09.3-mac-intel.dmg) | `7b123efecab1395d03fdf4e5df4df16efc72c9629c38b50ef8cad692d310bd77` |
| Windows x64 | [anki-26.09.3-win-x64.msi](https://github.com/ankitects/anki/releases/download/26.09.3/anki-26.09.3-win-x64.msi) | `8a45823d1c31017cebb7d3af4493d69b6ae3c185345fcb2390ede4af01e0a950` |
| Windows ARM64 | [anki-26.09.3-win-arm64.msi](https://github.com/ankitects/anki/releases/download/26.09.3/anki-26.09.3-win-arm64.msi) | `445d5973ec92e8ed4fb09d606aed084e2aaeeaba853b53b5608a6f6cae66ee2a` |
| Linux x86_64 | [anki-26.09.3-linux-x86_64.tar.zst](https://github.com/ankitects/anki/releases/download/26.09.3/anki-26.09.3-linux-x86_64.tar.zst) | `d70e01971a7aa190b189927573ee643f2525ff840eafaecc7a8f8cde505650b3` |
| Linux AArch64 | [anki-26.09.3-linux-aarch64.tar.zst](https://github.com/ankitects/anki/releases/download/26.09.3/anki-26.09.3-linux-aarch64.tar.zst) | `0b586efdb0e3582bee3b9d08b9fa57df681fb97a8066d76a6743e1bc3fc331eb` |

安装与最低运行环境：

- **macOS：13+，Apple Silicon 与 Intel 分包。** 官方安装方法为打开 DMG，将 Anki 拖到 Applications 或桌面；Homebrew 是可选方式，不应成为新用户必装依赖。见[下载页](https://apps.ankiweb.net/#downloads)、[macOS 安装手册](https://docs.ankiweb.net/manual/platform/mac/installing)。
- **Windows：x64 需要 Windows 10 1703+ 或 Windows 11；ARM64 需要 Windows 11。** 见[Windows 安装手册](https://docs.ankiweb.net/manual/platform/windows/installing)。MSI 可用 `msiexec.exe /i <path> /passive /norestart` 显示安装进度且不自动重启；这是 Windows Installer 标准参数，不表示已验证 Anki MSI 的所有 UI/权限场景。见[Microsoft msiexec 文档](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/msiexec)。
- **Linux：x86_64 glibc >= 2.35，AArch64 glibc >= 2.39；官方构建不支持 musl。** 官方包还依赖图形/系统库，Debian/Ubuntu 列出的前置包为 `libxcb-xinerama0 libxcb-cursor0 libnss3 libxcb-icccm4 libxcb-keysyms1`，解压需要支持 zstd。安装步骤为解压后执行 `sudo ./install.sh`。见[Linux 安装手册](https://docs.ankiweb.net/manual/platform/linux/installing)。

建议：首发支持范围明确到 OS + CPU + 最低版本，不把“Linux”理解为所有发行版。安装器可覆盖用户明确选定的平台；没有同架构构建/测试证据的包不能仅改文件名交付。

## 程序、用户数据和插件路径

默认位置如下；用户可以选择安装位置或用自定义数据目录，因此它们是探测候选，不是唯一位置。[官方文件手册](https://docs.ankiweb.net/manual/files#user-data)

| 平台 | 程序默认位置 | 用户数据基目录 |
| --- | --- | --- |
| Windows | `%LOCALAPPDATA%\Programs\Anki` | `%APPDATA%\Anki2` |
| macOS | `/Applications/Anki.app` | `~/Library/Application Support/Anki2` |
| Linux | `/usr/local/share/anki` | `$XDG_DATA_HOME/Anki2`，未设置时 `~/.local/share/Anki2` |
| Linux 第三方 Flatpak | 应经 Flatpak 启动/探测 | `~/.var/app/net.ankiweb.Anki/data/Anki2` |

Anki 26.09.3 数据基目录优先级为命令行 `-b` > 环境变量 `ANKI_BASE` > 平台默认路径。插件目录为 `<基目录>/addons21`，并非某个 profile 的子目录。官方 AnkiConnect package 为 `2055492159`，所以默认安装目标为 `<基目录>/addons21/2055492159`；同一基目录内各 profile 共用此插件及其配置。见[ProfileManager](https://github.com/ankitects/anki/blob/26.09.3/qt/aqt/profiles.py#L314-L315)、[基目录选择](https://github.com/ankitects/anki/blob/26.09.3/qt/aqt/profiles.py#L357-L381)、[插件 manifest](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/plugin/manifest.json)。

建议：允许首次向导选择/确认自定义数据目录；识别 Flatpak 作为单独接入情形，不直接假定宿主进程、沙箱路径和官方包行为相同。CLI 的偏好和日志使用 anki-x 自己的用户目录，避免混入 Anki collection 或随程序升级覆盖。

## 启动与隔离测试

官方参数：`-b/--base` 指定数据目录；`-p/--profile` 指定账户名称；`-l/--lang` 指定界面语言；`-v/--version` 打印版本；`--safemode` 禁用插件和自动同步。命令行还接受待导入文件或待安装插件。见[参数解析源码](https://github.com/ankitects/anki/blob/26.09.3/qt/aqt/__init__.py#L482-L504)。

不提供 `-p` 时会加载上次账户；传入不存在的账户名会打开账户选择页。macOS 文档支持 `open /Applications/Anki.app --args -b <directory>`。见[启动选项](https://docs.ankiweb.net/manual/files#startup-options)。

**隔离验收参考（属于建议，不是本轮执行记录）：**

1. 创建全新临时目录，只包含测试牌组，无同步凭据。
2. 在启动进程的环境设置随机唯一的 `ANKI_SINGLE_INSTANCE_KEY`；Anki 在导入 aqt 时读取此值。
3. 指定 `-b <临时目录> -p <测试账户> -l en`；配置独立 AnkiConnect 端口。
4. 正常插件测试不用 `--safemode`，因为它会禁用待验收的插件。
5. 关闭测试同步和更新提示，并在结束后只关闭该测试进程。

依据：Anki 的 `AnkiApp.KEY` 默认只由 OS 用户名生成；启动发现相同 key 的现有进程会发送消息并复用。AnkiConnect 官方 smoke test 正是设置唯一 key、临时 ProfileManager、关闭自动同步/更新检查后调用 `aqt._run()`。见[Anki IPC 实现](https://github.com/ankitects/anki/blob/26.09.3/qt/aqt/__init__.py#L329-L388)、[官方 smoke_gui.py](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/tools/smoke_gui.py)。

## 固定 AnkiConnect 提交的打包与安装

官方构建入口是 `make package` 或 Windows 上 `python tools/package_addon.py`。它先检查生成的 API contract，再把 `plugin/` 内容放到 `AnkiConnect.zip` 根目录，排除 `.pyc`、`__pycache__`、`user_files`、`meta.json` 和隐藏文件。`manifest.json` 包含 package `2055492159`、name `Anki-Connect`、conflicts `["AnkiConnectDev"]`，没有 `mod` 或 `human_version`。见[打包器](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/tools/package_addon.py)、[manifest](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/plugin/manifest.json)。

Anki 接受 `.ankiaddon` 和 `.zip`；不经 AnkiWeb 分发时，manifest 至少需要 package/name；ZIP 内不能额外包一层插件目录。见[官方分发文档](https://docs.ankiweb.net/addons/sharing)、[Anki AddonManager](https://github.com/ankitects/anki/blob/26.09.3/qt/aqt/addons.py#L174-L200)。

原生安装动作会先读取旧 meta，备份旧 `user_files`，替换插件代码，恢复用户文件，再把 manifest 中受支持的元数据键合并进旧 meta；`force_enable=True` 才主动将 `disabled` 改为 false。见[安装源码](https://github.com/ankitects/anki/blob/26.09.3/qt/aqt/addons.py#L446-L524)。

**实施建议：** 构建时固定源提交和包 hash；安装前读取已有插件状态。在未启动 Anki 的安装场景，可由安装器做带备份和回滚的文件部署，但行为应覆盖原生安装的保留规则。Anki 正在运行时，先正常退出再替换，或使用原生插件安装交互并提示重启；不能把磁盘文件替换视作已热更新内存中的插件。官方明确要求安装后重启。[AnkiConnect 安装说明](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/README.md)

## 配置、认证、端口与现有设置保留

有效配置是 `config.json` 默认值，再覆盖 `meta.json` 的 `config` 对象。Anki 的 `writeConfig()` 修改后者，并保留其他元数据。只修改 `config.json` 无法覆盖已存的用户值。见[Anki 配置 API](https://github.com/ankitects/anki/blob/26.09.3/qt/aqt/addons.py#L713-L737)。

固定提交的默认配置与协议：

| 项 | 事实 | 实施含义 |
| --- | --- | --- |
| 地址/端口 | IPv4 `127.0.0.1:8765`，直接 socket bind | 先读已有配置；端口占用不代表目标服务存在 |
| API | v1 为 `POST /api/v1` JSON-RPC 2.0；legacy 为 `/` version 6 | 不把旧接口 version 6 当作插件版本 |
| API key | 默认 null；v1 使用 `Authorization: Bearer <key>`；legacy 使用 JSON body 的 key | 已有密钥要沿用，不能为方便连接清空 |
| Origin | 不带 Origin 的 CLI 请求可通过 Origin 判定；认证检查仍适用 | CLI 无需添加 `*` 或改用户 CORS 白名单 |
| 重启 | listener 配置变化要求重启 Anki | 向导应等待真实重启/重连并验证新配置生效 |

来源：[配置帮助](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/plugin/config.md)、[默认值](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/plugin/util.py)、[监听与认证实现](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/plugin/web.py)。

建议的发现顺序：anki-x 上次成功连接信息 → 用户所选 Anki 数据目录中的插件有效配置 → 默认 loopback 端口。每一步用 API 身份/能力验证，不对发现的任意 HTTP 服务提交卡片写操作。若旧插件已有非默认端口/API key/CORS，先保存并复用；确需改变端口时对 meta 做最小合并且保留备份，不覆盖 `config` 以外的状态。新安装可使用随机生成的 key 并只保存在当前用户可读的配置中；已有插件的认证策略不静默改变。

`ANKICONNECT_BIND_ADDRESS` / `ANKICONNECT_CORS_ORIGIN` 仅出现在 util 的回退默认中，随包 `config.json` 或用户配置有同名值时优先级更高；此提交没有 `ANKICONNECT_PORT` 环境配置契约。不能靠随意设置环境变量完成端口迁移。[util.py](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/plugin/util.py)

## 兼容性与自动更新元数据

`api.describe` 返回 `apiMajor`、`ankiVersion`、schema、各方法 available/reason 和 limits；没有该插件的提交 hash 或独立语义版本。源码还对方法依赖的 Anki 原生能力逐一探测。连接时应检查 anki-x 实际需要的方法是否存在且 available，不能只检查对象非空或 API major。[runtime.py](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/plugin/runtime.py)

Anki 的插件元数据包括 `mod`（安装/更新时间戳）、`min_point_version`、`max_point_version`、`branch_index`、`human_version`、`disabled`、`update_enabled` 等。纯数字目录名会作为 AnkiWeb add-on ID；更新比较服务端 modified 和本地 mod，而非 Git hash。负的 max_point_version 是硬上限；正数仅表示已测版本，源码不会据此阻止更高版本。见[AddonMeta](https://github.com/ankitects/anki/blob/26.09.3/qt/aqt/addons.py#L104-L160)、[更新选择](https://github.com/ankitects/anki/blob/26.09.3/qt/aqt/addons.py#L630-L644)。

官方 AnkiWeb 下载请求包含当前 Anki 整数版本，重定向 URL 带 `t/minpt/maxpt/bidx`，Anki 用这些值安装元数据。仅凭固定源码提交和官方 ID，无法证明当日 AnkiWeb 返回的 ZIP 与该提交相同。[Anki 下载实现](https://github.com/ankitects/anki/blob/26.09.3/qt/aqt/addons.py#L1112-L1166)

**实施建议：** 以 anki-x 的依赖清单保存 commit/hash/已验证 Anki 范围；每次启动检查能力。保留用户原本的 `update_enabled`，不要给官方插件伪造未来 `mod` 来阻止更新。若安装器以后管理更新，需要明确更新归属：官方插件仍可由 Anki 更新，anki-x 检测兼容性变化并提供修复入口。不要悄悄改 package 为新的名字、留下两个同时监听的插件。

## 再分发与发布所需事实

- AnkiConnect 固定提交声明 **GPL-3.0-or-later**；其构建器仅打包 plugin 目录，仓库根 `LICENSE` 不会自动进入 ZIP。交付依赖包时需另外落实许可证文本、版权声明和对应源代码的可获取性；不要把“官方 builder 成功”当作发布清单已经完整。见[AnkiConnect LICENSE](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/LICENSE)、[打包器](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/tools/package_addon.py)。
- Anki 主程序为 **AGPL-3.0-or-later**，包含不同许可的第三方代码和二进制依赖；logo 也有单独说明。若 anki-x 直接再分发完整 Anki 包，需连同其许可/来源义务处理。使用官方下载入口与完整原包是较清晰的依赖安装路线；名称、logo 和对外说明应准确标明独立项目身份。见[Anki LICENSE](https://github.com/ankitects/anki/blob/26.09.3/LICENSE)、[官网商标声明](https://apps.ankiweb.net/)。
- 公告 Anki 26.09.3 的 release 特别要求升级到 26.09+，并说明含安全修复。产品固定版本策略应同时保留兼容验证和依赖更新通道，不能长期冻结旧版本却没有升级流程。[26.09.3 release](https://github.com/ankitects/anki/releases/tag/26.09.3)

这些是明确的发布输入；本文件没有替项目选择许可证，也没有把未核实的第三方词库/音频标为可分发。

## 三端构建、安装与测试边界

PyInstaller 需要在各 OS 分别构建；Linux 不捆绑 glibc，应在计划支持的最旧 Linux 上构建，并在较新系统验证。单文件模式需要临时目录可执行；安装目录不能承担用户状态存储。见[PyInstaller 多平台与 Linux 说明](https://pyinstaller.org/en/stable/usage.html#supporting-multiple-operating-systems)、[临时解包说明](https://pyinstaller.org/en/stable/usage.html#defining-the-extraction-location)。

当前 GitHub Actions 官方 runner 支持 Windows x64/ARM64、Linux x64/ARM64、macOS Intel/ARM64；可使用明确标签而非依赖 `-latest` 架构不变。Windows hosted runner 以管理员身份运行且关闭 UAC，所以通过其安装测试并不能证明普通用户首次安装的授权体验正常。[GitHub hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)

AnkiConnect 官方 Windows runner 为 `tools/test.ps1`，Unix 为 `tools/test.sh`；矩阵是 26.8/26.9.3，默认运行最新版本，GUI smoke 默认开启。Unix 单元测试可用 Qt offscreen，但 GUI 阶段要求工作显示环境；Linux 无 DISPLAY/WAYLAND 时会主动报错并提示使用 `xvfb-run`。测试脚本中的 `QTWEBENGINE_DISABLE_SANDBOX=1` 是受控测试用法，不应复制成产品启动默认值。见[Unix 测试入口](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/tools/test.sh)、[Windows 测试入口](https://git.sr.ht/~foosoft/anki-connect/tree/62fc13d107c2b02130e503749e9933495c6456fb/item/tools/test.ps1)。

建议将证据分层保存：

1. **逻辑测试**：配置合并/损坏恢复、版本/能力判定、端口冲突、key 处理、下载 hash、升级回退。
2. **原生服务测试**：用真实 Anki 临时目录和独立实例，完成牌组选择、翻卡、评分一次、撤销、重启恢复。
3. **发行包测试**：从安装器安装，移走源码、清理 Python 相关 PATH 后启动；测试含中文/空格路径、只读程序目录、升级后设置保留和卸载保留用户数据。
4. **桌面体验测试**：Windows 普通用户/UAC、macOS 下载隔离标记、Linux 目标桌面和音频；可视终端确认中文/音标/键盘/音频真实可用。

以上是验收建议，不是本轮已取得的结果。Python 单测通过、GUI offscreen 通过和真实安装/发音通过不能互相替代。

## 尚未被本轮证据证明的事项

- 没有运行 Windows、Linux 或新用户安装器；不能宣布三端开箱即用已成立。
- 没有下载/运行六个完整 Anki 二进制包，仅核对了官方资产 URL、架构、哈希与源码。
- 没有证明 AnkiWeb 当前 ID 2055492159 的动态下载包等于固定提交；产品若要求确定性，应分发经过自身构建/校验的固定源码包。
- 没有验证 Windows MSI 的全部自定义安装属性/普通用户 UAC 分支，也没有验证 macOS 签名/公证产物。
- GUI 测试隔离与配置保留规则由固定源码证实，但 anki-x 自己的实现仍需对应的行为测试。

本轮临时证据：`/private/tmp/anki-26.09.3-addons.py`、`/private/tmp/anki-26.09.3-aqt-init.py`、`/private/tmp/anki-26.09.3-profiles.py`、`/private/tmp/anki-26.09.3-qt-pyproject.toml`、`/private/tmp/anki-26.09.3-LICENSE`、`/private/tmp/anki-official-release-assets-26.09.3.html`。这些文件来自对应官方固定 URL，可重取；文中外链是长期引用依据。
