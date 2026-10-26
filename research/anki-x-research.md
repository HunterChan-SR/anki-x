# 用终端配合 Anki 背英语单词：调研与建议

> 后续实现已完成，使用入口与实测结果见 [README](../README.md)。实装时发现当前插件的 GUI 评分通道在本机返回内部错误，因此成品采用已通过真实评分、撤销和终端按键测试的原生 `scheduling` 接口。以下保留最初调研记录。

调研日期：2026-10-26。需求：桌面 Anki 可以常开，希望在终端按间隔重复学习英语单词。本文依据官方文档、项目源码和本机只读检查；尚未安装插件或对真实卡片进行复习测试。

## 建议

采用 **Anki Desktop + AnkiConnect + 终端复习界面**。不需要重新研发排程引擎、学习数据库或 AnkiWeb 同步。现成的 `ProfessionalGriefer/anki-tui` 最贴近需求，但源码核查发现评分完成处理的缺口；适合先体验和验收。日常正式使用前，应修补这些问题，或基于 AnkiConnect v1 做一层小型前端。

这里适合的是 TUI，即在终端运行、用键盘交互的界面：选择英语牌组，先回忆单词，空格显示释义与例句，按 1–4 评价记忆程度。Anki 决定下一张卡及下一次复习时间。`anki-tui` 的 README 和源码使用 AnkiConnect 的 GUI reviewer actions；它没有自己计算复习间隔。[项目](https://github.com/ProfessionalGriefer/anki-tui)

FSRS 可以作为 Anki 的排程算法，利用复习表现估计记忆情况。初期可采用官方默认的 90% 目标保留率；这是排程目标，不是学习效果保证。忘记时选 Again，Hard 表示费力但仍然回忆成功。尚未读取本机牌组设置，因此这里是建议，不是对当前配置的描述。[Anki 官方说明](https://docs.ankiweb.net/manual/deck-options#fsrs)

## 本机检查

| 项目 | 结果 |
| --- | --- |
| 操作系统架构 | macOS arm64 |
| 安装路径 | `/Applications/Anki.app` |
| 应用声明版本 | `26.9.3`，来自应用 `Info.plist` |
| Bundle ID | `net.ankiweb.anki` |
| 默认插件目录中的 AnkiConnect | 未发现 |
| `127.0.0.1:8765` 的只读 `version` 请求 | 连接失败 |

检查没有访问卡片正文或改写 collection。端口未响应只说明默认端点不可用；自定义配置目录或端口不在本次检查范围。

## AnkiConnect 的最新状态

不能仅根据旧 GitHub 仓库的归档标记判断项目停更。作者的 GitHub README 明确说明已永久迁移到 SourceHut。[迁移声明](https://github.com/FooSoft/anki-connect)

本次直接读取的 SourceHut 主线 README 说明：

- 要求 Anki Desktop 26.08 或更新；维护者的兼容测试矩阵含 26.08、26.09.3，后者与本机版本相符。
- 新接入推荐 `/api/v1`，采用 JSON-RPC 2.0；旧的根路径 API v6 继续兼容，所以现有客户端有继续使用的路径。
- 操作针对桌面端当前 profile 的 collection；Anki 需保持运行。
- 当前主线在 macOS 自动抑制 App Nap，无需照抄旧教程的 `defaults write` 命令。

以上是**维护者对主线的声明**，不等于本机实测，也不证明 AnkiWeb 上某次下载一定包含全部新接口。部署后应调用 `api.describe` 确认 v1 能力；老客户端可验证 v6 接口。[当前 README](https://git.sr.ht/~foosoft/anki-connect/blob/master/README.md)

v1 已覆盖需要的核心能力：

| 需求 | 官方接口 |
| --- | --- |
| 列出牌组 | `decks.list` |
| 原生顺序获取复习队列 | `scheduling.getQueue` |
| 渲染卡片 | `cards.render`，返回 HTML/CSS |
| 获取评分后的预计间隔 | `scheduling.predict` |
| 写入一次原生评分 | `scheduling.answer` |
| 驱动桌面复习状态及其自定义排程钩子 | `application.navigate`、`reviewer.get/showAnswer/answer` |
| 重播当前卡片发音 | `reviewer.playAudio` |
| 撤销、今日统计、同步 | `collection.undo`、`statistics.getToday`、`collection.sync` |

评分接口有 session/state token，防止把过期状态当作当前卡片提交。自定义 reviewer 状态应使用 `reviewer.*`。异步评分、同步需等待 operation 的最终结果。旧版 `guiAnswerCard` 单独请求的成功只表示接收操作；用 `multi` 才能观察最终完成。实现时必须区分“接收”和“已经完成”。[v1 文档](https://git.sr.ht/~foosoft/anki-connect/blob/master/API_V1.md) · [兼容接口文档](https://git.sr.ht/~foosoft/anki-connect/blob/master/API_LEGACY.md)

## 采用现成工具还是研发

**现成工具可以体验，但需要补齐评分完成处理。** 基础的英语单词、释义、例句和已有音频，符合 `anki-tui` 的用途。源码却把评分请求的 `Ok(_)` 当作成功，既未判断布尔拒绝结果，也未等待异步评分最终完成就获取当前卡；这与新版接口契约有缺口，可能显示旧卡或误报成功。这里是静态分析，尚未运行复现。下面的项目核查记录提供永久源码链接。复杂 HTML/CSS、JavaScript 卡片模板和互动题型的呈现也需用实际词库验证。

安装路径已经明确：从 Anki 的“工具 → 插件 → 获取插件”安装代码 `2055492159`，重启并打开目标 profile；Apple Silicon 可以按项目说明安装 `brew install professionalgriefer/tap/anki-tui`，随后运行 `anki-tui`。[插件入口](https://ankiweb.net/shared/info/2055492159) · [TUI 安装说明](https://github.com/ProfessionalGriefer/anki-tui#installation)

第一次验收宜使用少量测试卡，检查：中英文与音标显示、音频播放、Again 后的重学、评分后实际换卡、撤销恢复、终端与桌面复习记录一致；同步需另查最终完成。这是尚待执行的验收，不是已经通过的检查。

**建议研发范围仅限小型前端。** 若追求每天稳定使用，我倾向基于 AnkiConnect v1 自写一个聚焦背词的前端：单词与释义显示、已有音频播放、评分、下次复习时间、今日进度和撤销。先不加入 AI 出题和复杂卡片管理。所有排程仍交给 Anki。粗略工程估算：文字和已有音频的基本复习闭环约 0.5–1 个开发日；补齐连接恢复、撤销、评分完成确认和实际词库验证，总计约 2–3 个开发日。此估算尚未经过实施验证，复杂模板、拼写判分与内容生产另算。修补现成 TUI 也是可行分支，但其源码许可声明存在不一致，若要派生发布需先厘清。

若自研，建议先采用 reviewer 路径，与桌面评分行为及扩展保持一致；只有明确不依赖 GUI reviewer 的自定义状态时，再使用独立 scheduling 路径。避免客户端直接更新 SQLite 的排程字段：Anki 官方说明，模型 API 会维护同步标记和数据一致性，裸数据库写入不能自动保证这些。[Anki 开发文档](https://docs.ankiweb.net/addons/the-anki-module)

词库本身仍是独立选择：TUI 提供学习入口，不自动提供英语课程。针对背词，优先选择能清楚呈现单词、一个目标义项、例句和发音的卡片；具体词表可在部署阶段按学习目标确定。

---

## 项目源码核查

方法：阅读项目官方 README、包配置、Git 历史与源码。源码以只读浅克隆取得，没有安装或运行这些软件，没有读取用户卡片、修改 Anki 数据，也没有在用户环境中复现运行时错误。下述维护日期是所取得默认分支 HEAD 的提交日期，不等于正式发布日期。成熟度判断依据实现、发布方式和明确限制，不以 star 数量排序。

## 主要候选对比

| 项目 | 与常开桌面端配合 | 终端复习 | 卡片管理 | 音频/图片 | 调研结论 |
|---|---|---|---|---|---|
| [ProfessionalGriefer/anki-tui](https://github.com/ProfessionalGriefer/anki-tui) | AnkiConnect | 原生 GUI reviewer | 不提供制卡/编辑；有统计和暂停 | 支持，媒体显示有约束 | 最贴近目标；评分完成确认需修补或替换 |
| [ubermenchh/anki-cli](https://github.com/ubermenchh/anki-cli) | 管理命令支持 AnkiConnect | TUI review 只支持 direct SQLite 后端 | 较全面，结构化输出 | 不能当完整 Anki 媒体渲染器 | 可考虑管理用途；不作为本次 reviewer 首选 |
| [alvenw/clanki](https://github.com/alvenw/clanki) | 要求关闭 Anki | 使用 Anki Python 后端 | 明确不计划制卡/编辑 | 支持基本音图；复杂模板不支持 | 有发布可试，但与常开桌面要求及本机新版本不匹配 |
| [pluveto/ankiterm](https://github.com/pluveto/ankiterm) | AnkiConnect | 原生 GUI reviewer；流式/单行两种界面 | 无完整管理 | 图片替换为文字占位符 | 旧而简洁，可参考；不推荐作为新日常方案 |

## 1. ProfessionalGriefer/anki-tui

**维护和分发。** 取得 HEAD 为 [`4dc61370072b75d83d11e2faffce48efb29e2efb`](https://github.com/ProfessionalGriefer/anki-tui/commit/4dc61370072b75d83d11e2faffce48efb29e2efb)，日期 2026-06-17。源码 Cargo 版本为 0.1.6；`v0.1.6` tag 指向 2026-06-17 的 `6786975418319440b7dd98d664b3bbf2e185a450`。官方个人 [Homebrew formula](https://github.com/ProfessionalGriefer/homebrew-tap/blob/main/Formula/anki-tui.rb) 当前安装 v0.1.6 的 macOS arm64 预编译包，并固定 SHA256。安装命令是 `brew install professionalgriefer/tap/anki-tui`，本次未执行。

**核心路线正确。** [`src/anki.rs`](https://github.com/ProfessionalGriefer/anki-tui/blob/4dc61370072b75d83d11e2faffce48efb29e2efb/src/anki.rs) 实现了 `guiDeckReview`、`guiCurrentCard`、`guiShowAnswer`、`guiAnswerCard`。常规评分提交给桌面 Anki，因此不另行实现 FSRS；实际调度取决于桌面端及其牌组配置。这个架构判断不等于已经用用户环境验证 FSRS。

**实际功能比 README 多。** [主事件循环](https://github.com/ProfessionalGriefer/anki-tui/blob/4dc61370072b75d83d11e2faffce48efb29e2efb/src/main.rs#L91-L136) 有牌组搜索、`y` 同步、`r` 重播音频、`u` 撤销、`!` 暂停、`i` 卡片统计；README 仍写“no statistics”。不能只据 README 断言它没有统计或同步。

**四档评分映射。** [`main.rs` 133–136 行](https://github.com/ProfessionalGriefer/anki-tui/blob/4dc61370072b75d83d11e2faffce48efb29e2efb/src/main.rs#L133-L136) 将按键 1/2/3/4 原样传给 `grade`；[`review.rs` 91–106 行](https://github.com/ProfessionalGriefer/anki-tui/blob/4dc61370072b75d83d11e2faffce48efb29e2efb/src/app/review.rs#L91-L106) 检查返回的可用 `buttons`。未发现这条正常路径的数值映射错。空格先揭示答案，再按空格会打 Good，需要在使用说明中说明。

**评分完成存在契约缺口。** [`review.rs` 123–130 行](https://github.com/ProfessionalGriefer/anki-tui/blob/4dc61370072b75d83d11e2faffce48efb29e2efb/src/app/review.rs#L123-L130) 对 `gui_answer_card` 的 `Ok(_)` 都进入成功分支，包括 `Ok(false)`，随后立即 `load_current_card()`。代码没有等待 operation 完成或确认卡片切换。若接口只返回 accepted，这不能证明评分已经落库或 reviewer 已切到下一张。此处是源码与接口语义的静态分析结论，**本次没有复现“重复卡”“评分丢失”或其他实际错误**。

**撤销和同步也需要完成确认。** [`review.rs` 134–162 行](https://github.com/ProfessionalGriefer/anki-tui/blob/4dc61370072b75d83d11e2faffce48efb29e2efb/src/app/review.rs#L134-L162) 收到 `guiUndo=true` 就恢复本地缓存卡，再评分时走 [`answerCards` 分支](https://github.com/ProfessionalGriefer/anki-tui/blob/4dc61370072b75d83d11e2faffce48efb29e2efb/src/app/review.rs#L109-L120)。[`decklist.rs` 215–225 行](https://github.com/ProfessionalGriefer/anki-tui/blob/4dc61370072b75d83d11e2faffce48efb29e2efb/src/app/decklist.rs#L215-L225) 在同步请求无传输错误后立即显示 `Synced with AnkiWeb`，没有完成轮询。不能根据该文案判断同步已经完成。

**英语媒体支持和限制。** [README](https://github.com/ProfessionalGriefer/anki-tui/blob/4dc61370072b75d83d11e2faffce48efb29e2efb/README.md) 说明图片采用 Kitty / Sixel / iTerm2 / half-block 终端渲染，macOS 音频使用 `afplay`。源码 [`media.rs`](https://github.com/ProfessionalGriefer/anki-tui/blob/4dc61370072b75d83d11e2faffce48efb29e2efb/src/media.rs) 解析 HTML、获取 Anki 媒体、简化 CSS/JS；它不是浏览器级模板渲染。[`review.rs` 18–40 行](https://github.com/ProfessionalGriefer/anki-tui/blob/4dc61370072b75d83d11e2faffce48efb29e2efb/src/app/review.rs#L18-L40) 从全部 note fields 提取声音供 `r` 重播，未按正反面过滤，因此不能保证仅播放当前一面的音频。对于普通单词/释义/发音卡是值得试的形态，复杂 JS、遮挡、输入答案模板需单独验收。

**改造前的许可信息不完整。** README 和 formula 标 MIT，但该 commit 的仓库树没有 `LICENSE` 文件，Cargo.toml 也没有 `license` 字段；项目自己的 [`brew.md`](https://github.com/ProfessionalGriefer/anki-tui/blob/4dc61370072b75d83d11e2faffce48efb29e2efb/brew.md) 明确指出这一点。这不妨碍了解或体验它；若准备分发修改版，需把许可元数据澄清。我们自行写薄前端不依赖复制其源码。

## 2. ubermenchh/anki-cli

取得 HEAD 为 [`dfe9e909b44ea4080f74425c1b92a6eb9aae61c8`](https://github.com/ubermenchh/anki-cli/commit/dfe9e909b44ea4080f74425c1b92a6eb9aae61c8)，日期 2026-10-15。近提交包含 TUI、批量管理、主题和共享复习状态的功能修正；`pyproject.toml` 标 0.2.0、Python 3.12–3.13，项目明确处于 Alpha。发布包为 `anki-cli`，可选 `[tui]`。

[README](https://github.com/ubermenchh/anki-cli/blob/dfe9e909b44ea4080f74425c1b92a6eb9aae61c8/README.md) 提供牌组/模型/标签、查询、制卡、编辑和多种输出格式，适合脚本及个人管理。它有 `auto` / `ankiconnect` / `direct` 后端；常开桌面时应明确选择 `--backend ankiconnect`。

关键限制是 [`review:start`](https://github.com/ubermenchh/anki-cli/blob/dfe9e909b44ea4080f74425c1b92a6eb9aae61c8/anki_cli/cli/commands/review.py#L158-L183) 只支持 direct 后端。其 direct 模式使用本地 FSRS 库并直接操作数据库，不能据此宣称与桌面 Anki 各版本的调度完全一致。AnkiConnect 后端的 [`answer_card`](https://github.com/ubermenchh/anki-cli/blob/dfe9e909b44ea4080f74425c1b92a6eb9aae61c8/anki_cli/backends/ankiconnect.py#L825-L847) 只能评分桌面当前正在展示的卡；它不是常开桌面下可即用的完整 TUI 学习闭环。对当前“主要背单词”的目标，其全面管理功能不构成优先采用的理由。

## 3. alvenw/clanki

取得 HEAD 为 [`b9e1d577be693f5876c116cef1eb2384ab0661c0`](https://github.com/alvenw/clanki/commit/b9e1d577be693f5876c116cef1eb2384ab0661c0)，日期 2026-03-24；可见 tags 包括 v0.1.4，2026-02/03 有跨平台音频和牌组筛选修正。[README](https://github.com/alvenw/clanki/blob/b9e1d577be693f5876c116cef1eb2384ab0661c0/README.md) 描述基本卡、Cloze、音频、图片与 `clanki sync`；强调运行时 **Anki Desktop 必须关闭**，同步需要主动调用。

它使用原生 Anki Python 后端，但 [`pyproject.toml`](https://github.com/alvenw/clanki/blob/b9e1d577be693f5876c116cef1eb2384ab0661c0/pyproject.toml) 固定 `anki==25.9.2`，开发状态为 Alpha。不能将“使用原生后端”推导成“可安全处理任何更新桌面版本的数据库”。README 明确不支持图片遮挡、自定义样式、数学/LaTeX，也不计划制卡/编辑。这是可试的独立终端 reviewer，但不符合本次优先使用常开桌面和现代 AnkiConnect 的路线。

## 4. pluveto/ankiterm

取得 HEAD 为 [`62598b572d1c807b6073f9b8ce951cff5d4ab0be`](https://github.com/pluveto/ankiterm/commit/62598b572d1c807b6073f9b8ce951cff5d4ab0be)，日期 2024-11-22（修复非法输入），仓库仅 6 次提交；基础版本源于 2023-11，tag v0.0.1。其 [README](https://github.com/pluveto/ankiterm/blob/62598b572d1c807b6073f9b8ce951cff5d4ab0be/README.md) 提供 stream / oneline 复习形式，需要自己构建 Go 程序。

[`x/automata/lib.go`](https://github.com/pluveto/ankiterm/blob/62598b572d1c807b6073f9b8ce951cff5d4ab0be/x/automata/lib.go) 和 [`x/ankicc/lib.go`](https://github.com/pluveto/ankiterm/blob/62598b572d1c807b6073f9b8ce951cff5d4ab0be/x/ankicc/lib.go) 证明它调用 GUI reviewer。[`x/xmisc/lib.go`](https://github.com/pluveto/ankiterm/blob/62598b572d1c807b6073f9b8ce951cff5d4ab0be/x/xmisc/lib.go) 将图片替换为 `(image)`。没有核实当前 Anki/AnkiConnect 的兼容性，也没有充分维护证据支持优先采用。可作简洁交互的参考，不推荐作为本次新建日常流程的基础。

## 其他检视结果与排除原因

- **[cicbyte/anki-cli](https://github.com/cicbyte/anki-cli)**：中文 README 功能很齐，但取得默认分支仅一个初始提交 [`d4fd6b2`](https://github.com/cicbyte/anki-cli/commit/d4fd6b2fa7105f4928d27f2adacf1f8992f079c7)（2026-04-29）。[`fetchCards`](https://github.com/cicbyte/anki-cli/blob/d4fd6b2fa7105f4928d27f2adacf1f8992f079c7/internal/tui/review.go#L496-L522) 一次查询 `is:due OR is:new` 并加载列表，[评分后](https://github.com/cicbyte/anki-cli/blob/d4fd6b2fa7105f4928d27f2adacf1f8992f079c7/internal/tui/model.go#L356-L383) 只递增列表下标；[`AnswerCard`](https://github.com/cicbyte/anki-cli/blob/d4fd6b2fa7105f4928d27f2adacf1f8992f079c7/internal/client/review.go#L17-L22) 丢弃 `answerCards` 的结果，只返回请求错误。该实现不等同于原生动态学习队列，也没有证据保证 Again 后按学习间隔重新出现；因此不因功能列表齐全而推荐。
- **[lervag/apy](https://github.com/lervag/apy)**：维护活跃，HEAD [`65c84a5`](https://github.com/lervag/apy/commit/65c84a5deecb3e3371b22d8cc4a6e39e7f0424ac) 为 2026-10-23；当前 [包配置](https://github.com/lervag/apy/blob/65c84a5deecb3e3371b22d8cc4a6e39e7f0424ac/pyproject.toml) 已固定 Anki 26.9.3、Python >=3.14。它擅长 `$EDITOR` / Markdown 制卡和维护；[`review`](https://github.com/lervag/apy/blob/65c84a5deecb3e3371b22d8cc4a6e39e7f0424ac/src/apyanki/cli.py#L742-L777) 的含义是 Review/Edit notes，实际动作菜单是编辑/删除/暂停等，不是四档评分的间隔复习。不能把同名 review 命令误认为背单词界面。
- **[briansunter/anki-ai](https://github.com/briansunter/anki-ai)**：HEAD [`f24c69b`](https://github.com/briansunter/anki-ai/commit/f24c69b32ab700e3e1d569c14095523974779e57) 为 2026-04-28，包版本 1.5.0。它是 CLI/MCP 的广泛 API 包装，支持制卡、编辑、媒体、`run sync` 等；[`getNextCards`](https://github.com/briansunter/anki-ai/blob/f24c69b32ab700e3e1d569c14095523974779e57/src/tools/cards.ts#L47-L125) 自行按查询拼接学习/复习/新卡列表，没有完整交互式 reviewer。适合作为自动化工具候选，不解决本次的主要交互需求。
- **[nathanlct/anki-cli](https://github.com/nathanlct/anki-cli)**：官方 README 仍要求 Python 2 `urllib2`，没有现代 Anki/FSRS 支持证据；不推荐新部署。

## 必要但尚未完成的验证

没有运行安装、构建测试或真卡学习。若采用现成 reviewer 或自写薄前端，至少要在测试牌组确认：新卡/学习/复习队列与桌面一致；1–4 的评分结果及复习日志一致；Again 后按设置再次出现；超时不造成重复提交；撤销等到真实完成；同步状态区分 accepted / running / complete；英语发音、Cloze 及实际模板显示正确。首轮只需要少量测试卡，无需接触现有正式学习进度。
