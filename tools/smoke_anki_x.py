#!/usr/bin/env python3
"""Exercise real Anki with disposable cards; undo every test review before cleanup."""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from anki_x.api import AnkiError, Client
from anki_x.review import Reviewer
from anki_x.render import card_text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8766")
    args = parser.parse_args()
    client = Client(args.url)
    collection = client.connect()
    today_before = client.col("statistics.getToday")["count"]
    names = client.col("noteTypes.list")
    basic = next(n for n in names if n["name"] in ("Basic", "问答题"))
    model = client.col("noteTypes.get", noteType={"id": basic["id"]})
    front, back = [field["name"] for field in model["fields"]][:2]
    deck_name = "__anki_x_test_" + str(time.time_ns())
    deck = client.change("decks.create", name=deck_name)
    review = None
    card_id = None
    checks = []
    try:
        note = client.change("notes.create", noteType={"id": basic["id"]}, deck={"id": deck["id"]},
                             fields={front: "anki-x verification", back: "这是可撤销的临时验证卡。"})
        card_id = note["cardIds"][0]
        review = Reviewer(client, deck_name)
        review.start()
        assert review.state["card"]["id"] == card_id, review.state
        assert "anki-x verification" in card_text(review.state, review.note)
        assert "临时验证卡" not in card_text(review.state, review.note)
        checks.append("question renders without the answer")

        for rating in ("again", "hard", "good", "easy"):
            review.reveal()
            assert review.state["side"] == "answer"
            assert "临时验证卡" in card_text(review.state, review.note)
            previous_token = review.state["stateToken"]
            result = review.grade(rating)
            assert result["cardId"] == card_id
            # A separate client proves that the result is committed in Anki,
            # rather than being a local display counter or cached state.
            other = Client(args.url)
            other.connect()
            log = other.col("reviews.list", cardIds=[card_id])["items"]
            assert len(log) == 1, log
            assert log[0]["rating"] == rating, log
            card = other.col("cards.get", id=card_id)
            expected_type = "review" if rating == "easy" else "learning"
            assert card["scheduling"]["type"] == expected_type, card
            assert client.col("statistics.getToday")["count"] == today_before + 1
            checks.append(rating + ": persisted one native review and updated scheduling")
            if rating == "again":
                assert review.state.get("card", {}).get("id") == card_id, review.state
                assert review.state["side"] == "question"
                checks.append("Again returns to the native relearning queue")
            try:
                client.change("scheduling.answer", cardId=card_id, stateToken=previous_token, rating=rating)
            except AnkiError:
                pass
            else:
                raise AssertionError("A stale token unexpectedly allowed another answer")
            assert len(client.col("reviews.list", cardIds=[card_id])["items"]) == 1
            review.undo()
            assert client.col("reviews.list", cardIds=[card_id])["items"] == []
            assert client.col("cards.get", id=card_id)["scheduling"]["type"] == "new"
            assert client.col("statistics.getToday")["count"] == today_before
            assert review.state.get("card", {}).get("id") == card_id, review.state
        checks.append("all four ratings reject stale tokens; undo restores card and review count")
    finally:
        # If an assertion failed after a successful grade, remove that review
        # through native undo first; do not leave test history in the account.
        if review and review.can_undo:
            review.undo()
        if review:
            review.close()
        client.change("application.navigate", view="deckBrowser")
        deleted = client.change("decks.delete", decks=[{"id": deck["id"]}], deleteCards=True)
        assert all("error" not in item for item in deleted["items"]), deleted
    assert all(d["id"] != deck["id"] for d in client.col("decks.list"))
    assert client.col("statistics.getToday")["count"] == today_before
    checks.append("temporary deck removed; user's prior review count unchanged")
    report = {"profile": collection["profile"], "scheduler": collection["scheduler"], "checks": checks}
    target = Path(__file__).resolve().parents[1] / "verification/native-smoke.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
