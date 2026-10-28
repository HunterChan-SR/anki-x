"""Installed CLI and first-run entry point; UI starts even without Anki."""

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .api import AnkiError, PendingOperation
from .bootstrap import Connector
from .diagnostics import export_diagnostics
from .storage import AppPaths, SessionLock, Settings, migrate_legacy


def parser():
    result = argparse.ArgumentParser(prog="anki-x", description="打开即用的 Anki 终端学习助手。")
    result.add_argument("--version", action="version", version=__version__)
    result.add_argument("--url", help="手动指定 AnkiConnect 地址")
    result.add_argument("--json", action="store_true", help="输出 JSON")
    sub = result.add_subparsers(dest="command")
    sub.add_parser("home", help="打开牌组主界面")
    sub.add_parser("setup", help="打开首次接入向导")
    review = sub.add_parser("review", help="进入指定牌组")
    review.add_argument("--deck")
    review.add_argument("--choose", action="store_true")
    sub.add_parser("decks", help="列出牌组")
    sub.add_parser("stats", help="今日学习进度")
    doctor = sub.add_parser("doctor", help="检查环境，无需先连上 Anki")
    doctor.add_argument("--export", action="store_true", help="导出脱敏诊断文件")
    sub.add_parser("sync", help="同步并确认完成")
    recover = sub.add_parser("recover", help="检查上次未完成操作")
    recover.add_argument("--acknowledge", action="store_true")
    sub.add_parser("paths", help="显示用户配置和数据目录")
    install = sub.add_parser("install", help="安装当前自包含发行包")
    install.add_argument("--payload", help=argparse.SUPPRESS)
    sub.add_parser("update", help="检查和安装更新")
    sub.add_parser("rollback", help="切换回上一个已安装版本")
    uninstall = sub.add_parser("uninstall", help="卸载程序，保留学习数据和设置")
    uninstall.add_argument("--yes", action="store_true")
    return result


def print_result(value, as_json):
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2))
    elif isinstance(value, dict):
        for key, item in value.items():
            print(f"{key}: {item}")
    else:
        print(value)


def main(argv=None):
    if os.name == "nt":
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
    args = parser().parse_args(argv)
    paths = AppPaths.discover()
    paths.ensure()
    if args.command == "paths":
        print_result({key: str(value) for key, value in vars(paths).items()}, args.json)
        return 0
    try:
        if not os.environ.get("ANKI_X_HOME") or os.environ.get("ANKI_X_LEGACY_HOME"):
            migrate_legacy(paths)
        settings = Settings(paths)
        if args.command == "install":
            from .updater import install_payload
            payload = args.payload or (str(Path(sys.executable).parent) if getattr(sys, "frozen", False) else None)
            if payload is None:
                raise RuntimeError("请从发行包运行安装器。开发环境可使用 pip install -e .。")
            print("安装完成：" + str(install_payload(payload, paths)))
            print("打开新的终端后运行 anki-x，或使用应用菜单中的 anki-x。")
            return 0
        if args.command in ("update", "rollback", "uninstall"):
            from .updater import run_update_command
            return run_update_command(args, paths)
        connector = Connector(paths, settings, args.url)
        if args.command in (None, "home", "review", "setup"):
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                print("请在交互终端中运行 anki-x；查询可使用 doctor、decks、stats。", file=sys.stderr)
                return 1
            from .app import AnkiX
            initial = "home" if args.command == "home" or getattr(args, "choose", False) else "setup" if args.command == "setup" else "resume"
            deck = getattr(args, "deck", None)
            if args.command == "review" and not getattr(args, "choose", False) and not deck:
                deck = settings.get("deck")
            with SessionLock(paths.state):
                AnkiX(paths, settings, explicit_url=args.url, initial=initial, deck=deck, connector=connector).run()
            return 0
        report = connector.inspect()
        if args.command == "doctor":
            result = report.diagnostic()
            result["message"] = report.message
            if args.export:
                result["diagnostics"] = str(export_diagnostics(paths, report))
            print_result(result, args.json)
            return 0 if report.state == "ready" else 1
        if report.state != "ready":
            raise RuntimeError(report.message + " 运行 anki-x setup 可自动设置。")
        client = report.client
        if args.command == "decks":
            results = [dict(name=item["name"], **client.deck_counts({"id": item["id"]})) for item in client.col("decks.list")]
            if args.json:
                print_result(results, True)
            else:
                for item in results:
                    print("{name}\n  新卡 {new} · 学习中 {learning} · 待复习 {review} · 共 {total} 张".format(**item))
        elif args.command == "stats":
            print_result(client.col("statistics.getToday"), args.json)
        else:
            with SessionLock(paths.state):
                if args.command == "recover":
                    if args.acknowledge:
                        client._clear_pending()
                        print_result({"result": "已确认；未重发操作"}, args.json)
                    else:
                        print_result({"result": client.recover()}, args.json)
                elif args.command == "sync":
                    if client.journal.exists():
                        client.recover()
                    print_result(client.change("collection.sync"), args.json)
        return 0
    except PendingOperation as exc:
        print(str(exc) + " 打开 anki-x 即可继续检查。", file=sys.stderr)
        return 3
    except (AnkiError, RuntimeError, OSError, ValueError) as exc:
        print("错误：" + str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已退出，学习记录保存在 Anki。", file=sys.stderr)
        return 130
