#!/usr/bin/env python3
"""Drive the real curses executable in a PTY and inspect actual Anki effects."""
import fcntl
import json
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from anki_x.api import Client


def main():
    config = json.loads((ROOT / "config.json").read_text())
    c = Client(config["url"])
    c.connect()
    before = c.col("statistics.getToday")["count"]
    basic = next(x for x in c.col("noteTypes.list") if x["name"] in ("Basic", "问答题"))
    fields = c.col("noteTypes.get", noteType={"id": basic["id"]})["fields"]
    name = "__anki_x_terminal_" + str(time.time_ns())
    deck = c.change("decks.create", name=name)
    note = c.change("notes.create", deck={"id": deck["id"]}, noteType={"id": basic["id"]},
                    fields={fields[0]["name"]: "terminal verification", fields[1]["name"]: "终端中文验证：翻面、评分、撤销。"})
    card_id = note["cardIds"][0]
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 32, 100, 0, 0))
    env = dict(os.environ, TERM="xterm-256color", LC_ALL="en_US.UTF-8",
               ANKI_X_STATE_DIR=str(ROOT / ".state/terminal-test"))
    proc = subprocess.Popen([str(ROOT / "bin/anki-x"), "review", "--deck", name],
                            stdin=slave, stdout=slave, stderr=slave, env=env, cwd=ROOT)
    os.close(slave)
    captured = bytearray()

    def expect(text, timeout=20):
        start = len(captured)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.2)[0]:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                captured.extend(chunk)
                if text.encode() in captured[start:]:
                    return
            if proc.poll() is not None:
                break
        raise AssertionError("Terminal did not display " + repr(text) + "\n" + captured.decode(errors="replace")[-2000:])

    try:
        expect("terminal verification")
        assert "终端中文验证".encode() not in captured
        os.write(master, b" ")
        expect("终端中文验证")
        os.write(master, b"1")
        expect("已保存")
        assert len(c.col("reviews.list", cardIds=[card_id])["items"]) == 1
        os.write(master, b"u")
        expect("已撤销")
        assert c.col("reviews.list", cardIds=[card_id])["items"] == []
        os.write(master, b"q")
        # Continue draining the PTY while curses restores the screen and exits.
        # Waiting without reading can block the child on the PTY output buffer.
        expect("本次完成 0 次复习")
        assert proc.wait(timeout=5) == 0
    finally:
        (ROOT / "verification/terminal.log").write_bytes(captured)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        os.close(master)
        if c.col("reviews.list", cardIds=[card_id])["items"]:
            c.change("collection.undo")
        c.change("application.navigate", view="deckBrowser")
        c.change("decks.delete", decks=[{"id": deck["id"]}], deleteCards=True)
    assert c.col("statistics.getToday")["count"] == before
    print("PASS: actual terminal launch, Chinese answer reveal, key 1 persists review, key u undoes it, key q exits; test deck cleaned.")


if __name__ == "__main__":
    main()
