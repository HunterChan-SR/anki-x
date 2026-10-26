#!/usr/bin/env python3
"""Regression against real Anki + AnkiConnect services in an isolated collection.

Requires anki==26.9.3 in the test interpreter. No live Anki/profile is contacted.
Pass --addon-source to an unpacked official AnkiConnect plugin directory.
"""

import argparse
import importlib
import json
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from anki_x.api import AnkiError
from anki_x.review import Reviewer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--addon-source", type=Path, required=True)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--tick-during-submit", action="store_true")
    args = parser.parse_args()
    # Load the official services without importing Anki Desktop startup code.
    package = types.ModuleType("anki_connect_regression")
    package.__path__ = [str(args.addon_source)]
    sys.modules[package.__name__] = package
    services = importlib.import_module(package.__name__ + ".services")
    runtime_class = importlib.import_module(package.__name__ + ".runtime").Runtime
    from anki.collection import Collection
    from google.protobuf.json_format import MessageToDict

    with tempfile.TemporaryDirectory(prefix="anki-x-regression-") as folder:
        col = Collection(str(Path(folder) / "collection.anki2"))
        runtime = runtime_class.__new__(runtime_class)
        runtime.tokens = {}
        runtime._session = "isolated-regression"
        runtime.generation = 0
        runtime.active_reviewer_card = None
        service = services.Services(runtime, col, runtime._session)

        class NativeClient:
            delayed = False

            def col(self, method, **params):
                try:
                    return service.execute(method, params)
                except services.ApiError as exc:
                    error = exc.record()
                    raise AnkiError(error["message"], error["code"], error["data"]) from exc

            def change(self, method, progress=None, **params):
                if method == "scheduling.answer" and args.tick_during_submit and not self.delayed:
                    self.delayed = True
                    time.sleep(1.2)
                return self.col(method, **params)

            def deck_counts(self, deck):
                return self.col("decks.getCounts", deck=deck)

        review = None
        try:
            note = col.new_note(col.models.by_name("Basic"))
            note["Front"], note["Back"] = "employer", "雇主"
            col.add_note(note, 1)
            card_id = str(note.card_ids()[0])
            prediction = service.scheduling_predict(card_id)
            service.scheduling_answer(card_id, "again", prediction["stateToken"], 1000)
            # The original fast smoke test only answered NEW cards. Real users
            # also read LEARNING cards for more than one scheduler clock tick.
            review = Reviewer(NativeClient(), "Default")
            review.refresh()
            assert review.state["card"]["scheduling"]["type"] == "learning"
            review.reveal()
            before = col._backend.get_scheduling_states(int(card_id))
            stored_before = col.get_card(int(card_id))._to_backend_card().SerializeToString()
            time.sleep(1.2)
            after = col._backend.get_scheduling_states(int(card_id))
            if args.inspect:
                print("STORED_CARD_UNCHANGED", stored_before == col.get_card(int(card_id))._to_backend_card().SerializeToString())
                print("BEFORE", json.dumps(MessageToDict(before), ensure_ascii=False))
                print("AFTER", json.dumps(MessageToDict(after), ensure_ascii=False))
            result = review.grade("good")
            assert result["cardId"] == card_id
            assert col.db.scalar("select count(*) from revlog where cid=?", int(card_id)) == 2
            assert review.reviewed == 1
            print("PASS: learning card can be read for >1 second and graded exactly once.")
        finally:
            if review:
                review.close()
            col.close()


if __name__ == "__main__":
    main()
