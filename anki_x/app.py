"""Cross-platform product UI: setup, decks, study, settings and recovery."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, ContentSwitcher, Footer, Input, Label, Select, Static, Tree

from .api import AnkiError, ConnectionError, PendingOperation
from .bootstrap import Connector
from .content import import_package, starter_deck
from .diagnostics import export_diagnostics
from .navigation import DeckTree, NavigationStore, start_location
from .render import card_text
from .review import RATINGS, Reviewer
from .setup import install_addon, install_anki


class PathDialog(ModalScreen):
    DEFAULT_CSS = """
    PathDialog { align: center middle; }
    PathDialog > Vertical { width: 75%; max-width: 90; height: auto; border: round $accent; padding: 1 2; background: $surface; }
    PathDialog Horizontal { height: auto; margin-top: 1; }
    """

    def __init__(self, title, value="", secret=False):
        super().__init__()
        self.title_text, self.value, self.secret = title, value, secret

    def compose(self):
        with Vertical():
            yield Label(self.title_text)
            yield Input(value=self.value, password=self.secret, id="path-value")
            with Horizontal():
                yield Button("确定", id="path-ok", variant="primary")
                yield Button("取消", id="path-cancel")

    def on_mount(self):
        self.query_one(Input).focus()

    @on(Button.Pressed, "#path-ok")
    @on(Input.Submitted)
    def accepted(self):
        self.dismiss(self.query_one(Input).value.strip())

    @on(Button.Pressed, "#path-cancel")
    def cancelled(self):
        self.dismiss(None)

    def key_escape(self):
        self.dismiss(None)


class DeckWidget(Tree):
    BINDINGS = [Binding("j", "cursor_down", show=False), Binding("k", "cursor_up", show=False),
                Binding("right,l", "expand_or_child", show=False), Binding("left,h", "collapse_or_parent", show=False)]

    def action_expand_or_child(self):
        node = self.cursor_node
        if node and node.children:
            if node.is_expanded:
                self.move_cursor(node.children[0])
            else:
                node.expand()

    def action_collapse_or_parent(self):
        node = self.cursor_node
        if node:
            if node.is_expanded and node.children:
                node.collapse()
            elif node.parent and node.parent is not self.root:
                self.move_cursor(node.parent)


class AnkiX(App):
    TITLE = "anki-x"
    CSS = """
    Screen { background: $background; }
    #brand { height: 3; padding: 1 3; text-style: bold; color: $accent; }
    #status { height: auto; min-height: 1; max-height: 3; padding: 0 3; }
    #main { height: 1fr; }
    .page { padding: 1 3; }
    .title { height: auto; text-style: bold; margin-bottom: 1; }
    .toolbar { height: auto; min-height: 3; }
    .toolbar Button { margin-right: 1; min-width: 10; }
    #deck-tree { height: 1fr; border: round $panel; }
    #deck-counts, #study-counts { height: auto; margin: 1 0; color: $text-muted; }
    #card-scroll { height: 1fr; border: round $panel; padding: 1 2; }
    #card { height: auto; }
    #study-side { height: auto; text-style: bold; color: $accent; margin: 0 0 1 0; }
    #ratings { height: auto; min-height: 3; margin-top: 1; }
    #ratings Button { width: 1fr; min-width: 12; margin-right: 1; }
    #reveal { width: 100%; }
    #setup-copy, #settings-copy, #help-copy { height: auto; margin-bottom: 1; }
    #setup-actions Button, #settings-buttons Button { width: 100%; margin-bottom: 1; }
    #setup-actions, #settings-buttons { height: auto; max-width: 75; }
    #profiles { width: 36; }
    #busy { height: auto; min-height: 1; padding: 0 3; color: $warning; }
    """
    BINDINGS = [Binding("q", "quit_app", "退出"), Binding("escape,b", "back", "返回"),
                Binding("space,enter", "reveal", "翻面", show=False), Binding("1", "grade(1)", show=False),
                Binding("2", "grade(2)", show=False), Binding("3", "grade(3)", show=False), Binding("4", "grade(4)", show=False),
                Binding("r", "audio", "重播"), Binding("u", "undo", "撤销"), Binding("g", "refresh", "刷新"),
                Binding("a", "autoplay", show=False), Binding("t", "title", show=False),
                Binding("d", "details", show=False), Binding("s", "settings", "设置"), Binding("?", "help", "帮助"),
                Binding("j", "scroll_card(1)", show=False), Binding("k", "scroll_card(-1)", show=False),
                Binding("ctrl+c", "quit_app", show=False, priority=True)]

    def __init__(self, paths, settings, *, explicit_url=None, initial="resume", deck=None, connector=None):
        super().__init__()
        self.paths, self.settings = paths, settings
        self.connector = connector or Connector(paths, settings, explicit_url)
        self.client = None
        self.environment = None
        self.navigation = None
        self.saved = {}
        self.deck_model = None
        self.tree_nodes = {}
        self.review = None
        self.deck = None
        self.detail = False
        self.total_reviews = 0
        self.initial, self.explicit_deck = initial, deck
        self.page = "setup"
        self.busy = False
        self._io = asyncio.Lock()
        self._restore_once = True
        self._tree_building = False
        self._selected_profile = None
        self._profiles_loading = False
        self._started_anki = False
        self._last_bookmark = None
        self._return_page = "home"
        self._update = None

    def compose(self) -> ComposeResult:
        yield Static("anki-x", id="brand", markup=False)
        yield Static("欢迎使用 anki-x", id="status", markup=False)
        yield Static("", id="busy", markup=False)
        with ContentSwitcher(initial="setup", id="main"):
            with VerticalScroll(id="setup", classes="page"):
                yield Static("连接你的 Anki", classes="title")
                yield Static("正在检查本机环境…", id="setup-copy", markup=False)
                with Vertical(id="setup-actions"):
                    yield Button("重新检查 / 连接", id="connect", variant="primary")
                    yield Button("启动 Anki", id="start-anki")
                    yield Button("下载并安装官方 Anki", id="install-anki")
                    yield Button("安装 / 修复连接插件", id="install-addon")
                    yield Button("选择 Anki 数据目录", id="choose-base")
                    yield Button("选择 Anki 程序位置", id="choose-executable")
                    yield Button("检查未完成操作", id="recover")
                    yield Button("已在 Anki 核对结果，解除未确认状态", id="acknowledge", variant="warning")
                    yield Button("导出诊断信息", id="diagnostics")
            with Vertical(id="home", classes="page"):
                with Horizontal(classes="toolbar"):
                    yield Static("我的牌组", classes="title")
                    yield Select([], prompt="Anki 账户", id="profiles")
                yield DeckWidget("牌组", id="deck-tree")
                yield Static("选择牌组后按 Enter 开始，左右键展开/收起。", id="deck-counts", markup=False)
                with Horizontal(classes="toolbar"):
                    yield Button("开始学习", id="study", variant="primary")
                    yield Button("导入牌组", id="import")
                    yield Button("体验词卡", id="starter")
                    yield Button("设置", id="settings-home")
            with Vertical(id="review", classes="page"):
                yield Static("", id="study-counts", markup=False)
                yield Static("回忆单词", id="study-side", markup=False)
                with VerticalScroll(id="card-scroll"):
                    yield Static("", id="card", markup=False)
                yield Button("空格 / Enter · 显示答案", id="reveal", variant="primary")
                with Horizontal(id="ratings"):
                    for i, (_, label) in enumerate(RATINGS, 1):
                        yield Button(f"{i} {label}", id=f"grade-{i}")
                with Horizontal(classes="toolbar"):
                    yield Button("返回牌组", id="back-home")
                    yield Button("重播发音", id="audio")
                    yield Button("撤销", id="undo")
                    yield Button("详细释义", id="details")
            with VerticalScroll(id="settings", classes="page"):
                yield Static("设置", classes="title")
                yield Static("", id="settings-copy", markup=False)
                with Vertical(id="settings-buttons"):
                    yield Button("自动发音", id="toggle-autoplay")
                    yield Button("顶部标题", id="toggle-title")
                    yield Button("同步并等待完成", id="sync")
                    yield Button("检查更新", id="updates")
                    yield Button("安装已发现的更新", id="apply-update")
                    yield Button("重新设置 Anki 接入", id="setup-again")
                    yield Button("导出诊断信息", id="diagnostics-settings")
                    yield Button("返回", id="settings-back")
            with VerticalScroll(id="help", classes="page"):
                yield Static("使用帮助", classes="title")
                yield Static("主界面：↑↓ / j k 选择，→/l 展开，←/h 收起，Enter 学习。\n\n学习：空格翻面；1 忘记、2 吃力但想起、3 记得、4 轻松。\n忘记时请选择 1，不要选 2。\n\nr 重播，u 撤销，d 详情，a 自动发音，t 标题。\nEsc / b 返回，q 退出；下次自动恢复。\n\nAnki 未运行时会自动启动。需要账户选择或系统授权时，在对应窗口完成即可。\n\n复杂图片遮挡、脚本互动和视频卡片请在桌面 Anki 学习。", id="help-copy", markup=False)
                yield Button("返回", id="help-back")
        yield Footer()

    async def on_mount(self):
        self.query_one("#brand").display = self.settings.get("show_title", True)
        self.query_one("#apply-update").display = False
        self.set_interval(1, self.save_navigation)
        self.run_worker(self.connect_environment(), exclusive=False)

    def status(self, message):
        self.query_one("#status", Static).update(message)

    def show_page(self, page):
        self.page = page
        self.query_one("#main", ContentSwitcher).current = page
        if page == "home":
            self.query_one("#deck-tree").focus()
        elif page == "review":
            self.query_one("#card-scroll").focus()
        self.save_navigation()

    async def task(self, label, function, *args, **kwargs):
        if self.busy:
            return None
        self.busy = True
        self.query_one("#busy", Static).update(label)
        try:
            async with self._io:
                return await asyncio.to_thread(function, *args, **kwargs)
        finally:
            self.busy = False
            self.query_one("#busy", Static).update("")

    def show_error(self, exc):
        self.status(str(exc))
        if isinstance(exc, PendingOperation) or (self.paths.state / "pending.json").exists():
            self.show_recovery()
        elif isinstance(exc, ConnectionError):
            self.show_page("setup")
            self.query_one("#setup-copy", Static).update("连接中断。已保存的评分仍在 Anki 中；点击重新检查即可继续。")

    async def connect_environment(self):
        try:
            report = await self.task("正在检查 Anki…", self.connector.inspect)
            if report is None:
                return
            self.environment = report
            self.query_one("#install-anki").display = report.state == "anki_missing"
            self.query_one("#install-addon").display = report.state in ("plugin_missing", "plugin_disabled", "port_conflict", "incompatible", "restart_needed")
            self.query_one("#start-anki").display = report.executable is not None and report.state != "ready"
            pending = (self.paths.state / "pending.json").exists()
            self.query_one("#recover").display = pending
            self.query_one("#acknowledge").display = pending
            self.query_one("#setup-copy", Static).update(report.title + "\n\n" + report.message)
            if report.state == "anki_stopped" and not self._started_anki:
                self._started_anki = True
                await self.task("正在启动 Anki…", self.connector.start_anki)
                for _ in range(15):
                    await asyncio.sleep(1)
                    report = await self.task("等待 Anki 加载账户…", self.connector.inspect)
                    if report.state != "anki_stopped":
                        break
                self.environment = report
            if report.state != "ready":
                self.show_page("setup")
                self.query_one("#setup-copy", Static).update(report.title + "\n\n" + report.message)
                self.status("按界面提示完成一次设置，之后会自动连接。")
                return
            self.client = report.client
            self.client.timeout = 15
            self.navigation = NavigationStore(self.paths.state / "navigation.json", self.client.endpoint, report.profile)
            self.saved = self.navigation.load()
            if self.client.journal.exists():
                self.show_recovery()
                return
            resume_state = json.loads(json.dumps(self.saved))
            await self.load_home()
            if self._restore_once:
                self._restore_once = False
                location, node = start_location(self.deck_model, resume_state, self.explicit_deck, self.initial == "home")
                if location == "review" and node:
                    self.saved = resume_state
                    await self.enter_deck(node)
                elif self.initial == "setup":
                    self.show_page("setup")
            self.status("Anki 已连接。" if report.tested_version else "已连接；此 Anki 版本超出当前完整测试矩阵，请先用体验词卡验证。")
        except Exception as exc:
            self.show_page("setup")
            self.query_one("#setup-copy", Static).update(str(exc))
            self.status("未能完成接入，可以重试或导出诊断信息。")

    async def load_home(self):
        decks = await self.task("正在读取牌组…", self.client.col, "decks.list")
        if decks is None:
            return
        home = self.saved.get("home", {})
        if self.deck_model:
            home = self.deck_model.snapshot()
        self.deck_model = DeckTree(decks, home.get("selected"), home.get("expanded"), self.settings.get("deck"))
        widget = self.query_one("#deck-tree", DeckWidget)
        self._tree_building = True
        widget.clear()
        widget.show_root = False
        self.tree_nodes = {}

        def add(key, parent):
            node = self.deck_model.nodes[key]
            child = parent.add(Text(node.label), data=key, expand=key in self.deck_model.expanded, allow_expand=bool(node.children))
            self.tree_nodes[key] = child
            for sub in node.children:
                add(sub, child)

        for root in self.deck_model.roots:
            add(root, widget.root)
        widget.root.expand()
        desired = self.deck_model.selected

        def restore_cursor():
            if desired in self.tree_nodes:
                widget.move_cursor(self.tree_nodes[desired])
                self.deck_model.selected = desired
            self._tree_building = False

        self.call_after_refresh(restore_cursor)
        self.show_page("home")
        try:
            profiles = await self.task("正在读取账户…", self.client.call, "profiles.list")
            if profiles is not None:
                self._profiles_loading = True
                names = [p["name"] if isinstance(p, dict) else p for p in profiles]
                select = self.query_one("#profiles", Select)
                select.set_options([(name, name) for name in names])
                self._selected_profile = self.environment.profile
                select.value = self._selected_profile
                self._profiles_loading = False
        except AnkiError:
            self.query_one("#profiles").display = False
        await self.update_counts()

    @on(Tree.NodeHighlighted, "#deck-tree")
    def highlighted(self, event):
        if self._tree_building or not self.deck_model or event.node.data is None:
            return
        if event.node is not self.query_one("#deck-tree", DeckWidget).cursor_node:
            return
        self.deck_model.selected = event.node.data
        self.save_navigation()
        self.run_worker(self.update_counts(), group="counts", exclusive=True)

    async def update_counts(self):
        if not self.deck_model or not self.deck_model.current or self.busy:
            return
        node = self.deck_model.current
        if not node.deck_id:
            return
        try:
            async with self._io:
                counts = await asyncio.to_thread(self.client.deck_counts, {"id": node.deck_id})
            if self.deck_model.current and self.deck_model.current.key == node.key:
                self.query_one("#deck-counts", Static).update(node.name + "\n" + "新卡 {new} · 学习中 {learning} · 待复习 {review} · 共 {total} 张".format(**counts))
        except AnkiError as exc:
            self.status(str(exc))

    @on(Tree.NodeExpanded, "#deck-tree")
    def expanded(self, event):
        if self.deck_model and event.node.data:
            self.deck_model.expanded.add(event.node.data)
            self.save_navigation()

    @on(Tree.NodeCollapsed, "#deck-tree")
    def collapsed(self, event):
        if self.deck_model and event.node.data:
            self.deck_model.expanded.discard(event.node.data)
            self.save_navigation()

    @on(Tree.NodeSelected, "#deck-tree")
    async def selected(self, event):
        if self.page == "home" and event.node.data and not self.busy:
            await self.enter_deck(self.deck_model.nodes[event.node.data])

    async def enter_deck(self, node):
        if not node.deck_id or self.busy:
            return
        try:
            if self.review:
                self.total_reviews += self.review.reviewed
                self.review.close()
            self.review = Reviewer(self.client, node.name)
            self.deck = node
            await self.task("正在进入牌组…", self.review.start)
            bookmark = self.saved.get("review", {})
            self.detail = False
            offset = 0
            if bookmark.get("deck_id") == node.deck_id:
                restored = await self.task("正在恢复阅读位置…", self.review.restore, bookmark)
                if restored:
                    self.detail = bool(bookmark.get("detail"))
                    offset = bookmark.get("offset", 0)
            self.show_page("review")
            self.render_review()
            self.query_one("#card-scroll", VerticalScroll).scroll_to(y=max(0, int(offset)), animate=False)
            await self.autoplay()
        except Exception as exc:
            self.show_error(exc)

    def render_review(self):
        state = self.review.state
        answered = state.get("side") == "answer"
        self.query_one("#brand", Static).update("anki-x / " + self.deck.name)
        self.query_one("#study-counts", Static).update("新卡 {new} · 学习中 {learning} · 待复习 {review} · 本次完成 {done}".format(
            **self.review.counts, done=self.total_reviews + self.review.reviewed))
        self.query_one("#study-side", Static).update("核对答案" if answered else "回忆单词")
        if state.get("card"):
            text = card_text(state, self.review.note, "details" if self.detail else "auto")
        else:
            text = "当前可学习的词卡已完成。\n\n按 Esc 返回牌组，或稍后按 g 检查新到期词卡。"
        self.query_one("#card", Static).update(Text(text or "此卡片没有可显示的文字，可以重播发音或在 Anki 中查看。"))
        self.query_one("#reveal").display = bool(state.get("card")) and not answered
        self.query_one("#ratings").display = answered
        offered = {item["rating"]: item for item in state.get("answers", [])}
        for i, (rating, label) in enumerate(RATINGS, 1):
            button = self.query_one(f"#grade-{i}", Button)
            button.disabled = rating not in offered
            button.label = f"{i} {label}" + (" · " + offered[rating]["label"] if rating in offered else "")
        self.query_one("#undo", Button).disabled = not self.review.can_undo
        self.save_navigation()

    async def autoplay(self):
        if self.settings.get("autoplay", True) and self.review and self.review.state.get("card"):
            await self.action_audio(automatic=True)

    async def action_reveal(self):
        if self.page == "review" and not self.busy:
            self.review.reveal()
            self.render_review()

    async def action_grade(self, value):
        if self.page != "review" or self.busy:
            return
        try:
            self.saved["review"] = {"deck_id": self.deck.deck_id, "in_flight": True}
            if self.navigation:
                # If the process ends after Anki commits but before the next
                # frame, do not restore an already-answered cached side.
                snapshot = dict(self.saved, view="review")
                self.navigation.save(snapshot)
            await self.task("正在保存评分…", self.review.grade, RATINGS[value - 1][0])
            self.detail = False
            self.query_one("#card-scroll", VerticalScroll).scroll_home(animate=False)
            self.render_review()
            self.status("评分已保存。")
            await self.autoplay()
        except Exception as exc:
            self.show_error(exc)

    async def action_audio(self, automatic=False):
        if self.page == "review" and not self.busy:
            try:
                await self.task("正在播放…", self.review.audio)
            except Exception as exc:
                self.status(("当前词卡无可用音频。" if automatic else str(exc)))

    async def action_undo(self):
        if self.page == "review" and not self.busy:
            try:
                await self.task("正在撤销…", self.review.undo)
                self.render_review()
                self.status("已撤销上次评分。")
            except Exception as exc:
                self.show_error(exc)

    def action_details(self):
        if self.page == "review" and self.review.state.get("side") == "answer":
            self.detail = not self.detail
            self.query_one("#card-scroll", VerticalScroll).scroll_home(animate=False)
            self.render_review()

    def action_scroll_card(self, direction):
        if self.page == "review":
            scroll = self.query_one("#card-scroll", VerticalScroll)
            scroll.scroll_relative(y=direction, animate=False)

    def action_autoplay(self):
        value = not self.settings.get("autoplay", True)
        self.settings.set("autoplay", value)
        if not value and self.review:
            self.review.stop_audio()
        self.status("自动发音已" + ("开启" if value else "关闭"))
        self.render_settings()
        if value:
            self.run_worker(self.autoplay())

    def action_title(self):
        value = not self.settings.get("show_title", True)
        self.settings.set("show_title", value)
        self.query_one("#brand").display = value
        self.render_settings()

    async def action_refresh(self):
        if self.busy:
            return
        if self.page == "review":
            try:
                await self.task("正在刷新…", self.review.recover)
                self.render_review()
            except Exception as exc:
                self.show_error(exc)
        elif self.page == "home" and self.client:
            await self.load_home()
        else:
            await self.connect_environment()

    async def action_back(self):
        if self.busy:
            self.status("操作仍在进行，请稍等。")
            return
        if self.page in ("settings", "help"):
            self.show_page(self._return_page)
        elif self.page == "review":
            self.save_navigation()
            self.review.stop_audio()
            self.saved["view"] = "home"
            self.show_page("home")
            await self.load_home()

    def action_settings(self):
        if self.page not in ("settings", "help"):
            self._return_page = self.page
        self.save_navigation()
        self.render_settings()
        self.show_page("settings")

    def render_settings(self):
        if not self.is_mounted:
            return
        self.query_one("#settings-copy", Static).update("设置会自动保存，升级不会覆盖学习记录。\n" +
            ("账户：" + self.environment.profile if self.environment and self.environment.profile else "尚未连接 Anki"))
        self.query_one("#toggle-autoplay", Button).label = "自动发音：" + ("开" if self.settings.get("autoplay") else "关")
        self.query_one("#toggle-title", Button).label = "顶部标题：" + ("显示" if self.settings.get("show_title") else "隐藏")

    def action_help(self):
        if self.page not in ("settings", "help"):
            self._return_page = self.page
        self.save_navigation()
        self.show_page("help")

    def save_navigation(self):
        if not self.navigation or not self.deck_model or self.busy:
            return
        if self.page in ("home", "review"):
            self.saved["view"] = self.page
        self.saved["home"] = self.deck_model.snapshot()
        if self.review and self.deck and self.review.state:
            self.saved["review"] = dict(self.review.bookmark(), deck_id=self.deck.deck_id, deck_name=self.deck.name,
                                        detail=self.detail, offset=int(self.query_one("#card-scroll", VerticalScroll).scroll_y))
        if self.saved != self._last_bookmark:
            try:
                self.navigation.save(self.saved)
                self._last_bookmark = json.loads(json.dumps(self.saved))
            except OSError:
                self.status("界面位置未能保存，请检查用户目录权限。")

    def action_quit_app(self):
        if self.busy:
            self.status("正在完成操作，请稍等后退出；不会重复提交评分。")
            return
        self.save_navigation()
        if self.review:
            self.review.close()
        self.exit()

    def show_recovery(self):
        self.show_page("setup")
        self.query_one("#recover").display = True
        self.query_one("#acknowledge").display = True
        self.query_one("#setup-copy", Static).update("上次操作的结果尚未确认。\n\n先点击“检查未完成操作”。若请求中断且没有操作编号，请在 Anki 中核对结果，再选择解除未确认状态。不会重新提交评分。")

    @on(Select.Changed, "#profiles")
    async def profile_changed(self, event):
        if self._profiles_loading or event.value == Select.NULL or event.value == self._selected_profile or self.busy:
            return
        try:
            self.save_navigation()
            if self.review:
                self.review.close()
                self.review = None
                self.deck = None
            await self.task("正在切换账户…", self.client.change, "profiles.switch", name=event.value, application=True)
            self.deck_model = None
            self._restore_once = True
            await self.connect_environment()
        except Exception as exc:
            self.show_error(exc)

    async def path_result(self, kind, value):
        if not value:
            return
        try:
            if kind == "import":
                await self.task("正在导入牌组…", import_package, self.client, value)
                await self.load_home()
                self.status("牌组已导入。")
            else:
                self.settings.set(kind, str(Path(value).expanduser()))
                await self.connect_environment()
        except Exception as exc:
            self.show_error(exc)

    @on(Button.Pressed)
    async def button(self, event):
        identifier = event.button.id
        if self.busy:
            return
        try:
            if identifier == "connect":
                await self.connect_environment()
            elif identifier == "start-anki":
                await self.task("正在启动 Anki…", self.connector.start_anki)
                await asyncio.sleep(2)
                await self.connect_environment()
            elif identifier == "install-anki":
                self.status("将下载并校验 Anki 官方安装包；系统安装授权请在弹窗中完成。")
                await self.task("正在下载并安装 Anki…", install_anki, self.paths, self.settings)
                await self.connect_environment()
            elif identifier == "install-addon":
                report = self.environment or self.connector.inspect()
                await self.task("正在安装连接插件…", install_addon, report.base, self.paths, self.settings, repair_port=True)
                await self.connect_environment()
            elif identifier in ("choose-base", "choose-executable"):
                kind = "anki_base" if identifier == "choose-base" else "anki_executable"
                self.push_screen(PathDialog("选择 " + ("Anki 数据目录" if kind == "anki_base" else "Anki 程序路径"), self.settings.get(kind) or ""),
                                 lambda value: self.run_worker(self.path_result(kind, value)))
            elif identifier == "study" and self.deck_model.current:
                await self.enter_deck(self.deck_model.current)
            elif identifier == "import":
                self.push_screen(PathDialog("输入或粘贴 .apkg 文件路径"), lambda value: self.run_worker(self.path_result("import", value)))
            elif identifier == "starter":
                name = await self.task("正在添加体验词卡…", starter_deck, self.client)
                await self.load_home()
                self.status("体验词卡已就绪：" + name)
            elif identifier.startswith("grade-"):
                await self.action_grade(int(identifier[-1]))
            elif identifier == "reveal":
                await self.action_reveal()
            elif identifier == "audio":
                await self.action_audio()
            elif identifier == "undo":
                await self.action_undo()
            elif identifier == "details":
                self.action_details()
            elif identifier in ("back-home", "settings-back", "help-back"):
                await self.action_back()
            elif identifier == "settings-home":
                self.action_settings()
            elif identifier == "toggle-autoplay":
                self.action_autoplay()
            elif identifier == "toggle-title":
                self.action_title()
            elif identifier == "setup-again":
                self.show_page("setup")
                await self.connect_environment()
            elif identifier in ("diagnostics", "diagnostics-settings"):
                output = export_diagnostics(self.paths, self.environment)
                self.status("诊断信息已保存（不含密钥和卡片正文）：" + str(output))
            elif identifier == "recover":
                if not self.client:
                    raise RuntimeError("请先连接原来的 Anki 账户。")
                await self.task("正在确认原操作…", self.client.recover)
                await self.connect_environment()
            elif identifier == "acknowledge":
                if self.client:
                    self.client._clear_pending()
                    await self.connect_environment()
            elif identifier == "sync":
                if not self.client:
                    raise RuntimeError("请先连接 Anki。")
                result = await self.task("正在同步，请在 Anki 中完成必要提示…", self.client.change, "collection.sync")
                self.status("同步已完成。" if result else "同步尚未完成。")
            elif identifier == "updates":
                from .updater import check_update
                result = await self.task("正在检查更新…", check_update)
                self._update = result
                self.query_one("#apply-update").display = result.get("available", False)
                self.status(result["message"])
            elif identifier == "apply-update" and self._update:
                from .updater import apply_update
                self.save_navigation()
                result = await self.task("正在下载并安装更新…", apply_update, self.paths, self._update, lock_held=True)
                self.status(result)
                self.query_one("#apply-update").display = False
        except Exception as exc:
            self.show_error(exc)
