#!/usr/bin/env python3
"""Exercise actual CLI/curses restart navigation with an isolated fixture backend."""
import fcntl
import importlib.util
import json
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from anki_x.navigation import NavigationStore


def child():
    from unittest.mock import patch
    from anki_x import __main__ as cli
    spec = importlib.util.spec_from_file_location("navigation_fixture", ROOT / "tests/test_navigation.py")
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)

    def client(*args, **kwargs):
        value = fixture.FakeClient()
        value.endpoint = "http://navigation-fixture/api/v1"
        value.journal = kwargs["journal"]
        value.connect = lambda: {"profile": "Navigation Test", "session": "fixture", "scheduler": "sm2"}
        return value

    config = Path(os.environ["ANKI_X_STATE_DIR"]) / "fixture-config.json"
    with patch.object(cli, "Client", client), patch.object(cli, "CONFIG", config):
        return cli.main(sys.argv[2:])


class Terminal:
    def __init__(self, directory, arguments=()):
        self.master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 32, 100, 0, 0))
        env = dict(os.environ, TERM="xterm-256color", LC_ALL="en_US.UTF-8", ANKI_X_STATE_DIR=str(directory))
        self.process = subprocess.Popen([sys.executable, str(Path(__file__)), "--child", *arguments],
                                        stdin=slave, stdout=slave, stderr=slave, env=env, cwd=ROOT)
        os.close(slave)
        self.output = bytearray()

    def expect(self, text, since=0):
        deadline = time.monotonic() + 8
        while text.encode() not in self.output[since:]:
            if time.monotonic() >= deadline:
                raise AssertionError("Missing " + repr(text) + "\n" + self.output.decode(errors="replace")[-2000:])
            if select.select([self.master], [], [], 0.1)[0]:
                try:
                    self.output.extend(os.read(self.master, 65536))
                except OSError:
                    raise AssertionError(self.output.decode(errors="replace"))

    def press(self, key, expected):
        mark = len(self.output)
        os.write(self.master, key.encode())
        self.expect(expected, mark)

    def send(self, key):
        os.write(self.master, key.encode())

    def quit(self):
        self.press("q", "本次完成 0 次复习")
        assert self.process.wait(timeout=3) == 0

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=3)
        os.close(self.master)


def main():
    sessions = []
    with tempfile.TemporaryDirectory(prefix="anki-x-navigation-check-") as directory:
        directory = Path(directory)
        (directory / "fixture-config.json").write_text(json.dumps({"deck": "English::CET4", "autoplay": False}))
        store = NavigationStore(directory / "navigation.json", "http://navigation-fixture/api/v1", "Navigation Test")

        def launch(arguments=()):
            terminal = Terminal(directory, arguments)
            sessions.append(terminal)
            return terminal

        def selected(key):
            deadline = time.monotonic() + 5
            while store.load().get("home", {}).get("selected") != key:
                if time.monotonic() >= deadline:
                    raise AssertionError("Selection was not persisted: " + key)
                time.sleep(0.02)

        try:
            first = launch()
            first.expect("我的牌组")
            first.press("l", "CET4")
            first.send("l")
            selected("3")
            first.press("\n", "employer")
            first.press(" ", "雇主")
            first.quit()
            review_state = store.load()
            assert review_state["view"] == "review"
            assert review_state["review"]["deck_id"] == "3"
            assert review_state["review"]["side"] == "answer"
            print("PASS fresh home, tree expansion, entering a deck, and saving answer page", flush=True)

            second = launch()
            second.expect("核对答案")
            second.expect("雇主")
            second.press("b", "我的牌组")
            second.send("j")
            selected("5")
            second.press("\n", "employer")
            second.press("\x1b", "我的牌组")
            second.quit()
            home_state = store.load()
            assert home_state["view"] == "home"
            assert home_state["home"]["selected"] == "5"
            assert "2" in home_state["home"]["expanded"]
            print("PASS restart into answer page, back to home, switch deck, Escape back", flush=True)

            third = launch()
            third.expect("我的牌组")
            third.expect("English::CET6")
            third.quit()
            assert store.load()["home"] == home_state["home"]
            print("PASS restart preserves the home selection and expanded tree", flush=True)

            store.save(review_state)
            forced = launch(["home"])
            forced.expect("我的牌组")
            forced.quit()
            assert store.load()["view"] == "home"
            print("PASS explicit home overrides saved study screen", flush=True)

            direct = launch(["review", "--deck", "English::CET6"])
            direct.expect("employer")
            direct.press(" ", "雇主")
            mark = len(direct.output)
            direct.process.send_signal(signal.SIGINT)
            direct.expect("已退出", mark)
            assert direct.process.wait(timeout=3) == 130
            assert store.load()["view"] == "review"
            assert store.load()["review"]["side"] == "answer"
            print("PASS explicit deck override and Ctrl+C preserve the current screen", flush=True)
        finally:
            for terminal in sessions:
                terminal.close()


if __name__ == "__main__":
    sys.exit(child() if len(sys.argv) > 1 and sys.argv[1] == "--child" else main())
