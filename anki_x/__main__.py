import argparse
import fcntl
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path

from . import __version__
from .api import AnkiError, Client, ConnectionError, PendingOperation
from .navigation import NavigationStore


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config.json"


@contextmanager
def exclusive(directory):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "session.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AnkiError("另一个 anki-x 正在学习或写入，请先退出它。")
        yield


def output(value, as_json=False):
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2))
    else:
        for key, item in value.items():
            print(f"{key}: {item}")


def save_preference(path, name, enabled):
    preferences = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    preferences[name] = enabled
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(preferences, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def parser():
    p = argparse.ArgumentParser(prog="anki-x", description="在终端按 Anki 的间隔重复计划背英语单词。")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--url", help="AnkiConnect 地址（优先于配置文件）")
    p.add_argument("--json", action="store_true", help="查询结果输出 JSON")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("home", help="打开牌组主界面，忽略上次退出位置")
    review = sub.add_parser("review", help="直接开始背词")
    review.add_argument("--deck", help="牌组完整名称")
    review.add_argument("--choose", action="store_true", help="打开牌组主界面")
    review.add_argument("--layout", choices=["auto", "template"])
    sub.add_parser("decks", help="列出牌组和当前待学数量")
    sub.add_parser("stats", help="今日学习进度")
    sub.add_parser("doctor", help="检查 Anki 连接、排程和配置")
    sub.add_parser("sync", help="同步并等待 Anki 确认完成")
    recover = sub.add_parser("recover", help="检查上次未确认的操作（不会重发）")
    recover.add_argument("--acknowledge", action="store_true", help="已在桌面核对结果，清除无法跟踪的操作记录")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    config = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    endpoint = args.url or os.environ.get("ANKI_CONNECT_URL") or config.get("url")
    directory = Path(os.environ.get("ANKI_X_STATE_DIR", ROOT / ".state"))
    client = Client(endpoint, journal=directory / "pending.json")
    command = args.command or "ui"
    preferred = config.get("deck")

    try:
        if command == "recover" and args.acknowledge:
            with exclusive(directory):
                client._clear_pending()
            print("已清除未确认记录；没有重新提交操作。")
            return 0
        collection = client.connect()
        if command == "doctor":
            description = client.call("api.describe")
            data = {"连接": "正常", "地址": client.endpoint, "账户": collection["profile"],
                    "排程": collection["scheduler"].upper(), "默认词库": preferred or "选择牌组",
                    "未确认操作": "有，请运行 recover" if client.journal.exists() else "无",
                    "API v1": "可用" if description else "不可用"}
            output(data, args.json)
            return 0
        if command == "decks":
            data = []
            for deck in client.col("decks.list"):
                counts = client.deck_counts({"id": deck["id"]})
                data.append(dict(name=deck["name"], **counts))
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                for item in data:
                    print("{name}\n  新卡 {new} · 学习中 {learning} · 待复习 {review} · 共 {total} 张".format(**item))
            return 0
        if command == "stats":
            today = client.col("statistics.getToday")
            data = {"日期": today["day"], "今日复习次数": today["count"], "排程": collection["scheduler"].upper()}
            if preferred:
                counts = client.deck_counts({"name": preferred})
                data.update({"词库": preferred, "新卡": counts["new"], "学习中": counts["learning"], "待复习": counts["review"]})
            output(data, args.json)
            return 0
        with exclusive(directory):
            if command == "recover":
                result = client.recover()
                output({"结果": "操作已确认完成" if result is not None else "没有待确认操作", "详情": result}, args.json)
                return 0
            if client.journal.exists():
                client.recover()
            if command == "sync":
                print("正在同步…")
                result = client.change("collection.sync")
                output({"同步": "已完成", "详情": result}, args.json)
                return 0
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                raise AnkiError("复习需要交互终端。请在 Terminal / iTerm 中运行 anki-x；查询可使用 decks / stats。")
            from .tui import run
            force_home = command == "home" or getattr(args, "choose", False)
            deck = (getattr(args, "deck", None) or preferred) if command == "review" and not force_home else None
            preference_path = directory / "preferences.json"
            preferences = json.loads(preference_path.read_text(encoding="utf-8")) if preference_path.exists() else {}
            navigation = NavigationStore(directory / "navigation.json", client.endpoint, collection["profile"])
            reviewed = run(client, deck=deck, preferred=preferred, layout=getattr(args, "layout", None),
                           autoplay=preferences.get("autoplay", config.get("autoplay", True)),
                           show_title=preferences.get("show_title", config.get("show_title", True)),
                           force_home=force_home, navigation=navigation.load(), on_navigation_change=navigation.save,
                           on_preference_change=lambda name, value: save_preference(preference_path, name, value))
            print(f"本次完成 {reviewed} 次复习。学习记录已保存在 Anki。")
            if client.journal.exists():
                print("另有操作尚未确认，请运行 anki-x recover。")
        return 0
    except PendingOperation as exc:
        print(str(exc) + " 请运行 anki-x recover。", file=sys.stderr)
        return 3
    except (AnkiError, OSError) as exc:
        print("错误：" + str(exc), file=sys.stderr)
        if isinstance(exc, ConnectionError):
            print("请打开 Anki，确认 AnkiConnect 已启用，再运行 anki-x doctor。", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已退出。若操作仍在处理，请运行 anki-x recover。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
