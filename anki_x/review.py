"""Native Anki queue/scheduling with terminal-owned reveal and audio playback."""

import base64
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .api import AnkiError, ConnectionError, PendingOperation


RATINGS = [("again", "忘记"), ("hard", "吃力"), ("good", "记得"), ("easy", "轻松")]


class Reviewer:
    def __init__(self, client, deck):
        self.client = client
        self.deck = deck
        self.state = None
        self.note = None
        self.counts = {}
        self.reviewed = 0
        self.can_undo = False
        self.pending_action = None
        self.shown_at = time.monotonic()
        self.player = None
        self.media_cache = tempfile.TemporaryDirectory(prefix="anki-x-audio-")

    def start(self, progress=None, bookmark=None):
        self.client.change("application.navigate", view="deckOverview", deck={"name": self.deck}, progress=progress)
        self.refresh()
        if bookmark:
            self.restore(bookmark)
        return self.state

    def _read_card(self, card_id):
        card = self.client.col("cards.get", id=card_id)
        prediction = self.client.col("scheduling.predict", cardId=card_id)
        state = {"active": True, "card": card, "side": "question",
                 "rendered": self.client.col("cards.render", id=card_id),
                 "stateToken": prediction["stateToken"], "answers": prediction["answers"]}
        note = self.client.col("notes.get", id=card["noteId"])
        return state, note

    def refresh(self):
        queue = self.client.col("scheduling.getQueue", fetchLimit=1)
        if queue["cards"]:
            card_id = queue["cards"][0]["cardId"]
            self.state, self.note = self._read_card(card_id)
        else:
            self.state = {"active": False, "card": None, "side": "none", "answers": []}
            self.note = None
        self.shown_at = time.monotonic()
        self.counts = self.client.deck_counts({"name": self.deck})
        return self.state

    @staticmethod
    def _signature(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def bookmark(self):
        card = (self.state or {}).get("card")
        if not card:
            return {"card_id": None, "side": "none"}
        return {"card_id": card["id"], "side": self.state["side"],
                "card_signature": self._signature(card), "note_signature": self._signature(self.note),
                "elapsed_ms": max(0, int((time.monotonic() - self.shown_at) * 1000))}

    def restore(self, bookmark):
        card_id = bookmark.get("card_id")
        if not isinstance(card_id, str) or not card_id:
            return False
        state, note = self.state, self.note
        if not state.get("card") or state["card"]["id"] != card_id:
            queue = self.client.col("scheduling.getQueue", fetchLimit=1000)
            if card_id not in {card["cardId"] for card in queue["cards"]}:
                return False
            state, note = self._read_card(card_id)
        if (bookmark.get("card_signature") != self._signature(state["card"])
                or bookmark.get("note_signature") != self._signature(note)):
            return False
        self.state, self.note = state, note
        self.state["side"] = "answer" if bookmark.get("side") == "answer" else "question"
        elapsed = bookmark.get("elapsed_ms", 0)
        if not isinstance(elapsed, int):
            elapsed = 0
        self.shown_at = time.monotonic() - min(max(elapsed, 0), 3600000) / 1000
        return True

    def reveal(self):
        if not self.state.get("card") or self.state["side"] != "question":
            return
        self.state["side"] = "answer"

    def _prepare_answer(self, rating):
        card_id = self.state["card"]["id"]
        # Learning predictions include elapsedSecs, which changes even when the
        # stored card does not. Obtain a token at submission, not at display.
        # Read the token BEFORE checking the displayed card/note: a concurrent
        # write is then caught either by these checks or by Anki's token check.
        prediction = self.client.col("scheduling.predict", cardId=card_id)
        card = self.client.col("cards.get", id=card_id)
        if card != self.state["card"]:
            raise AnkiError("这张卡片已在 Anki 中被修改或评分，本次未提交。按 g 刷新后继续。")
        if self.note is not None:
            note = self.client.col("notes.get", id=card["noteId"])
            if note != self.note:
                raise AnkiError("词卡内容已改变，本次未评分。按 g 刷新后重新核对。")
        self.state["stateToken"] = prediction["stateToken"]
        self.state["answers"] = prediction["answers"]
        if rating not in {item["rating"] for item in prediction["answers"]}:
            raise AnkiError("评分选项已更新，请核对后重新选择。")
        return prediction["stateToken"]

    def grade(self, rating, progress=None):
        if not self.state.get("card") or self.state["side"] != "answer":
            raise AnkiError("先按空格显示答案，再评分。")
        offered = {item["rating"] for item in self.state["answers"]}
        if rating not in offered:
            raise AnkiError("当前卡片不提供这个评分。")
        try:
            for attempt in range(4):
                token = self._prepare_answer(rating)
                self.pending_action = "grade"
                try:
                    result = self.client.change("scheduling.answer", cardId=self.state["card"]["id"],
                                                stateToken=token, rating=rating,
                                                elapsedMs=max(0, int((time.monotonic() - self.shown_at) * 1000)),
                                                progress=progress)
                    break
                except AnkiError as exc:
                    # A typed conflict is rejected BEFORE the native write.
                    # Only this definite non-write may be retried. Timeouts,
                    # lost responses, and pending operations never are.
                    if not isinstance(exc.data, dict) or exc.data.get("type") != "conflict":
                        raise
                    self.pending_action = None
            else:
                raise AnkiError("Anki 状态持续变化，本次评分尚未保存。请稍后再按评分键。")
        except (PendingOperation, ConnectionError):
            raise
        except AnkiError:
            self.pending_action = None
            raise
        self.pending_action = None
        if not isinstance(result, dict) or result.get("cardId") != self.state["card"]["id"]:
            raise AnkiError("评分返回结果不符合当前卡片，请刷新并在 Anki 核对。")
        self.reviewed += 1
        self.can_undo = True
        self.refresh()
        return result

    def undo(self, progress=None):
        if not self.can_undo:
            raise AnkiError("本次学习没有可撤销的评分。")
        self.pending_action = "undo"
        try:
            result = self.client.change("collection.undo", progress=progress)
        except (PendingOperation, ConnectionError):
            raise
        except AnkiError:
            self.pending_action = None
            raise
        self.pending_action = None
        if not result.get("changed"):
            raise AnkiError("Anki 没有执行撤销。")
        self.reviewed = max(0, self.reviewed - 1)
        self.can_undo = False
        self.refresh()
        return result

    def recover(self, progress=None):
        result = self.client.recover(progress=progress)
        if self.pending_action == "grade" and result is not None:
            self.reviewed += 1
            self.can_undo = True
        elif self.pending_action == "undo" and result and result.get("changed"):
            self.reviewed = max(0, self.reviewed - 1)
            self.can_undo = False
        self.pending_action = None
        return self.refresh()

    def audio(self):
        if not self.state.get("card"):
            return
        fields = self.note.get("fields", {})
        explicit = [value for key, value in fields.items() if key.lower() in
                    {"英语发音", "发音", "audio", "sound", "word audio", "word_audio"}]
        side = "questionHtml" if self.state["side"] == "question" else "answerHtml"
        content = " ".join(explicit) if explicit else self.state["rendered"].get(side, "")
        filenames = list(dict.fromkeys(re.findall(r"\[sound:([^\]]+)\]", content)))
        if not filenames:
            raise AnkiError("这张卡片没有可播放的音频。")
        executable = shutil.which("afplay") or shutil.which("mpv")
        if not executable:
            raise AnkiError("未找到音频播放器；macOS 使用系统 afplay。")
        filename = filenames[0]
        path = Path(self.media_cache.name) / (hashlib.sha256(filename.encode()).hexdigest() + Path(filename).suffix)
        if not path.exists():
            media = self.client.col("media.get", filename=filename)
            path.write_bytes(base64.b64decode(media["data"], validate=True))
        self.stop_audio()
        self.player = subprocess.Popen([executable, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop_audio(self):
        if self.player and self.player.poll() is None:
            self.player.terminate()
            self.player.wait(timeout=2)

    def close(self):
        self.stop_audio()
        self.media_cache.cleanup()
