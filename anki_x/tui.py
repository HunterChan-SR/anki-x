"""Keyboard-first, UTF-8 terminal interface; no third-party dependencies."""

import curses
import locale
import time

from .api import AnkiError, ConnectionError, PendingOperation
from .render import card_text, clip, wrap
from .review import RATINGS, Reviewer
from .navigation import DeckTree, start_location


class Screen:
    def __init__(self, screen):
        self.screen = screen
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        screen.keypad(True)
        screen.timeout(1000)
        self.accent = curses.A_BOLD
        self.muted = curses.A_DIM
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            curses.init_pair(2, curses.COLOR_YELLOW, -1)
            self.accent = curses.color_pair(1) | curses.A_BOLD
        self.height, self.columns = screen.getmaxyx()

    def begin(self):
        self.height, self.columns = self.screen.getmaxyx()
        self.screen.erase()
        self.left = max(2, (self.columns - 100) // 2)
        self.body_width = max(12, min(100, self.columns - self.left - 2))

    def line(self, y, text, style=0, x=None):
        x = self.left if x is None else x
        if y < 0 or y >= self.height or x >= self.columns - 1:
            return
        try:
            self.screen.addstr(y, x, clip(text, self.columns - x - 1), style)
        except curses.error:
            pass

    def rule(self, y):
        self.line(y, "─" * self.body_width, self.muted)

    def key(self):
        try:
            return self.screen.get_wch()
        except curses.error:
            return None

    def flush(self):
        self.screen.refresh()

    def progress(self, state):
        text = "请在 Anki 窗口完成提示，再回到终端。" if state == "waitingForUser" else "正在等待 Anki 完成…"
        self.line(self.height - 3, " " * self.body_width)
        self.line(self.height - 3, text, self.accent)
        self.flush()


class App:
    def __init__(self, ui, client, preferred=None, deck=None, force_home=False,
                 navigation=None, on_navigation_change=None, layout=None,
                 autoplay=True, show_title=True, on_preference_change=None):
        self.ui, self.client = ui, client
        self.preferred = preferred
        self.autoplay, self.show_title = autoplay, show_title
        self.layout = layout or "auto"
        self.explicit_layout = layout
        self.on_preference_change = on_preference_change
        self.on_navigation_change = on_navigation_change
        self.saved = navigation if isinstance(navigation, dict) else {}
        home = self.saved.get("home", {})
        home = home if isinstance(home, dict) else {}
        self.tree = DeckTree(client.col("decks.list"), selected=home.get("selected"),
                             expanded=home.get("expanded"), preferred=preferred)
        self.home_top = self.number(home.get("top"))
        self.review_bookmark = self.saved.get("review", {})
        if not isinstance(self.review_bookmark, dict):
            self.review_bookmark = {}
        self.view, self.initial_deck = start_location(self.tree, self.saved, deck, force_home)
        self.total_reviewed = 0
        self.message = ""
        if self.view == "home" and self.saved.get("view") == "review" and not force_home:
            self.message = "上次学习的牌组已不可用，已返回主界面。"
        if deck is not None and self.initial_deck is None and not force_home:
            self.message = "未找到指定牌组，请从主界面选择。"
        self.counts = {}

    @staticmethod
    def number(value):
        return max(0, value) if isinstance(value, int) else 0

    def snapshot(self):
        return {"view": self.view, "home": dict(self.tree.snapshot(), top=self.home_top),
                "review": self.review_bookmark}

    def persist(self):
        if self.on_navigation_change:
            try:
                self.on_navigation_change(self.snapshot())
            except (OSError, ValueError) as exc:
                self.message = "界面位置暂未保存：" + str(exc)

    def switches(self):
        return ("[a 自动发音：" + ("开" if self.autoplay else "关")
                + "]  [t 标题：" + ("开" if self.show_title else "关") + "]")

    def toggle(self, key, review=None):
        if key == "a":
            self.autoplay = not self.autoplay
            name, value = "autoplay", self.autoplay
            if review and not value:
                review.stop_audio()
            self.message = "自动发音已" + ("开启。" if value else "关闭。")
        else:
            self.show_title = not self.show_title
            name, value = "show_title", self.show_title
            self.message = "顶部标题已" + ("显示。" if value else "隐藏。")
        if self.on_preference_change:
            try:
                self.on_preference_change(name, value)
            except (OSError, ValueError) as exc:
                self.message += " 本次已生效，但设置未能保存：" + str(exc)

    def reload_tree(self):
        state = self.tree.snapshot()
        self.tree = DeckTree(self.client.col("decks.list"), preferred=self.preferred, **state)
        self.counts.clear()

    def home(self):
        self.view = "home"
        try:
            self.reload_tree()
        except AnkiError as exc:
            self.message = str(exc) + " 按 g 重试。"
        self.persist()
        ui = self.ui
        while True:
            ui.begin()
            if self.show_title:
                ui.line(1, "anki-x  /  主界面", ui.accent)
            ui.line(3, "我的牌组    " + self.switches(), ui.accent)
            ui.rule(4)
            rows = self.tree.rows()
            page_size = max(1, ui.height - 13)
            selected_index = next((i for i, (node, _) in enumerate(rows) if node.key == self.tree.selected), 0)
            self.home_top = min(self.home_top, max(0, len(rows) - page_size))
            if selected_index < self.home_top:
                self.home_top = selected_index
            elif selected_index >= self.home_top + page_size:
                self.home_top = selected_index - page_size + 1
            for index, (node, depth) in enumerate(rows[self.home_top:self.home_top + page_size]):
                marker = ("▾" if node.key in self.tree.expanded else "▸") if node.children else "·"
                selected = node.key == self.tree.selected
                text = ("› " if selected else "  ") + "  " * depth + marker + " " + node.label
                ui.line(6 + index, text, ui.accent if selected else 0)
            if not rows:
                ui.line(6, "暂无牌组。可先在 Anki 导入词库，再按 g 刷新。")
            node = self.tree.current
            if node:
                ui.line(ui.height - 6, node.name, ui.muted)
                if node.deck_id and node.key not in self.counts:
                    try:
                        self.counts[node.key] = self.client.deck_counts({"id": node.deck_id})
                    except AnkiError as exc:
                        self.message = str(exc) + " 按 g 刷新。"
                        self.counts[node.key] = None
                counts = self.counts.get(node.key)
                if counts:
                    ui.line(ui.height - 5, "新卡 {new}   学习中 {learning}   待复习 {review}   共 {total} 张".format(**counts), ui.accent)
            ui.rule(ui.height - 4)
            ui.line(ui.height - 3, "↑↓/jk 选择  →/l 展开  ←/h 收起  Enter 学习  q 退出", ui.muted)
            ui.line(ui.height - 2, "Space 展开/收起  g 刷新  a 自动发音  t 标题", ui.muted)
            ui.line(ui.height - 1, self.message)
            ui.flush()
            key = ui.key()
            if key is None or key == curses.KEY_RESIZE:
                continue
            if key in ("q", "\x1b"):
                self.persist()
                return None
            try:
                if key in ("j", curses.KEY_DOWN):
                    self.tree.move(1)
                elif key in ("k", curses.KEY_UP):
                    self.tree.move(-1)
                elif key == curses.KEY_NPAGE:
                    self.tree.move(page_size)
                elif key == curses.KEY_PPAGE:
                    self.tree.move(-page_size)
                elif key in ("l", curses.KEY_RIGHT):
                    self.tree.right()
                elif key in ("h", curses.KEY_LEFT, "\b", "\x7f", curses.KEY_BACKSPACE):
                    self.tree.left()
                elif key == " ":
                    self.tree.toggle()
                elif key in ("\n", "\r", curses.KEY_ENTER):
                    if node and node.deck_id:
                        self.persist()
                        return node
                    self.tree.right()
                elif key in ("a", "t"):
                    self.toggle(key)
                elif key == "g":
                    self.reload_tree()
                    self.message = "牌组与学习数量已刷新。"
            except AnkiError as exc:
                self.message = str(exc)
            self.persist()

    def remember_review(self, node, review, offset, detail):
        self.review_bookmark = dict(review.bookmark(), deck_id=node.deck_id, deck_name=node.name,
                                    offset=offset, detail=detail, layout=self.layout)

    def study(self, node):
        ui = self.ui
        review = Reviewer(self.client, node.name)
        offset, detail = 0, False
        entered = False
        try:
            ui.begin()
            ui.progress("running")
            review.start(progress=ui.progress)
            saved = self.review_bookmark if self.review_bookmark.get("deck_id") == node.deck_id else {}
            if saved:
                restored = review.restore(saved)
                if restored:
                    offset, detail = self.number(saved.get("offset")), bool(saved.get("detail"))
                    self.message = "已恢复上次的词卡与阅读位置。"
                else:
                    self.message = "已回到上次的牌组，继续 Anki 当前可学的词卡。"
                if not self.explicit_layout and saved.get("layout") in ("auto", "template"):
                    self.layout = saved["layout"]
            else:
                self.message = "先回忆，再翻面；Esc / b 返回主界面。"
            self.view = "review"
            self.tree.select(node.key)
            entered = True
            self.remember_review(node, review, offset, detail)
            self.persist()
            started = time.monotonic()
            last_played_state = None
            while True:
                ui.begin()
                if self.show_title:
                    ui.line(1, "anki-x  /  " + node.name, ui.accent)
                elapsed = int(time.monotonic() - started)
                ui.line(3, "待学 {new}   学习中 {learning}   待复习 {review}   本次完成 {done}   {minutes:02}:{seconds:02}".format(
                    **review.counts, done=self.total_reviewed + review.reviewed,
                    minutes=elapsed // 60, seconds=elapsed % 60), ui.muted)
                ui.rule(4)
                state = review.state
                is_answer = state.get("side") == "answer"
                side_title = ("核对答案" if is_answer else "回忆单词") if state.get("card") else "学习完成"
                ui.line(5, side_title + "    " + self.switches(), ui.accent)
                if state.get("card"):
                    text = card_text(state, review.note, "details" if detail else self.layout)
                    lines = wrap(text or "这张卡片没有可显示的文字；可按 r 播放音频。", ui.body_width)
                else:
                    lines = ["当前可学习的卡片已完成。", "", "Anki 会根据你的评分安排下次复习。",
                             "按 Esc / b 返回牌组，g 检查新到期词卡，q 退出。"]
                body_height = max(1, ui.height - 14)
                offset = min(max(0, offset), max(0, len(lines) - body_height))
                for i, line in enumerate(lines[offset:offset + body_height]):
                    ui.line(7 + i, line, curses.A_BOLD if offset + i == 0 else 0)
                footer = ui.height - 6
                ui.rule(footer)
                if is_answer:
                    offered = {item["rating"]: item for item in state["answers"]}
                    buttons = [f"{i} {label} · {offered[rating]['label']}" for i, (rating, label) in enumerate(RATINGS, 1) if rating in offered]
                    ui.line(footer + 1, "    ".join(buttons), ui.accent)
                else:
                    ui.line(footer + 1, "Space / Enter 显示答案" if state.get("card") else "已完成当前学习队列", ui.accent)
                ui.line(footer + 2, "Esc/b 返回  q 退出  r 重播  u 撤销  d 详情  j/k 滚动  g 刷新", ui.muted)
                ui.line(footer + 3, self.message)
                if len(lines) > body_height:
                    ui.line(footer + 4, f"内容 {offset + 1}–{min(offset + body_height, len(lines))}/{len(lines)} 行", ui.muted)
                ui.flush()
                self.remember_review(node, review, offset, detail)
                if self.autoplay and state.get("card") and state is not last_played_state:
                    last_played_state = state
                    try:
                        review.audio()
                    except (AnkiError, OSError, ValueError) as exc:
                        self.message = "自动发音未播放：" + str(exc)
                    continue
                key = ui.key()
                if key is None or key == curses.KEY_RESIZE:
                    continue
                if key == "q":
                    return "quit"
                if key in ("b", "\x1b", "\b", "\x7f", curses.KEY_BACKSPACE):
                    self.view = "home"
                    self.message = "已返回牌组。"
                    return "home"
                try:
                    if key in ("j", curses.KEY_DOWN):
                        offset += 1
                    elif key in ("k", curses.KEY_UP):
                        offset -= 1
                    elif key == curses.KEY_NPAGE:
                        offset += body_height
                    elif key == curses.KEY_PPAGE:
                        offset -= body_height
                    elif key in (" ", "\n", "\r", curses.KEY_ENTER):
                        if not is_answer:
                            review.reveal()
                            offset = 0
                            self.message = "1 忘记 · 2 吃力但想起 · 3 记得 · 4 很轻松"
                    elif isinstance(key, str) and key in "1234":
                        rating, label = RATINGS[int(key) - 1]
                        review.grade(rating, progress=ui.progress)
                        self.message = f"已保存：{label}。"
                        offset, detail = 0, False
                    elif key == "r":
                        review.audio()
                        self.message = "正在重播当前词卡的发音。"
                    elif key in ("a", "t"):
                        self.toggle(key, review)
                        if key == "a" and self.autoplay:
                            last_played_state = None
                    elif key == "u":
                        review.undo(progress=ui.progress)
                        self.message = "已撤销上次评分。"
                        offset, detail = 0, False
                    elif key == "d" and is_answer:
                        detail = not detail
                        offset = 0
                    elif key == "g":
                        review.recover(progress=ui.progress)
                        self.message = "已读取 Anki 当前状态。"
                        offset, detail = 0, False
                except PendingOperation:
                    self.message = "仍在处理：按 g 继续检查，勿重复评分；q 可退出。"
                except ConnectionError as exc:
                    self.message = str(exc)
                except AnkiError as exc:
                    self.message = str(exc)
                    kind = exc.data.get("type") if isinstance(exc.data, dict) else None
                    if kind == "staleSession":
                        self.message = "Anki 账户已改变，请退出后重新运行 anki-x。"
                    elif kind == "conflict":
                        self.message = "卡片状态已改变，本次未提交。按 g 刷新后继续。"
                self.remember_review(node, review, offset, detail)
                self.persist()
                if key in ("1", "2", "3", "4", "u", "g"):
                    curses.flushinp()
        except AnkiError as exc:
            self.message = str(exc) + " 可从主界面重试。"
            self.view = "home"
            return "home"
        finally:
            if entered:
                self.remember_review(node, review, offset, detail)
            self.total_reviewed += review.reviewed
            review.close()
            self.persist()

    def run(self):
        node = self.initial_deck
        try:
            while True:
                if self.view == "home":
                    node = self.home()
                    if node is None:
                        return self.total_reviewed
                result = self.study(node)
                if result == "quit":
                    return self.total_reviewed
                self.view = "home"
        finally:
            self.persist()


def run(client, deck=None, preferred=None, layout=None, autoplay=True, *, show_title=True,
        force_home=False, navigation=None, on_navigation_change=None, on_preference_change=None):
    locale.setlocale(locale.LC_ALL, "")

    def main(screen):
        app = App(Screen(screen), client, preferred=preferred, deck=deck, force_home=force_home,
                  navigation=navigation, on_navigation_change=on_navigation_change,
                  layout=layout, autoplay=autoplay, show_title=show_title,
                  on_preference_change=on_preference_change)
        return app.run()

    return curses.wrapper(main)
