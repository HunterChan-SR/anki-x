import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from anki_x.navigation import DeckTree, NavigationStore, start_location
from anki_x.review import Reviewer


DECKS = [{"id": "1", "name": "Default"}, {"id": "2", "name": "English"},
         {"id": "3", "name": "English::CET4"}, {"id": "4", "name": "English::CET4::Hard"},
         {"id": "5", "name": "English::CET6"}]


class TreeTests(unittest.TestCase):
    def test_expand_enter_child_collapse_and_return_parent(self):
        tree = DeckTree(DECKS, preferred="English::CET4")
        self.assertEqual(tree.selected, "2")
        self.assertEqual([node.key for node, _ in tree.rows()], ["1", "2"])
        tree.right()
        self.assertEqual([node.key for node, _ in tree.rows()], ["1", "2", "3", "5"])
        tree.right()
        self.assertEqual(tree.selected, "3")
        tree.right()
        tree.right()
        self.assertEqual(tree.selected, "4")
        tree.left()
        self.assertEqual(tree.selected, "3")
        tree.left()
        self.assertNotIn("3", tree.expanded)
        tree.left()
        self.assertEqual(tree.selected, "2")

    def test_restore_keeps_ids_through_deck_rename(self):
        tree = DeckTree(DECKS, selected="4", expanded=["2", "3"])
        renamed = [dict(d, name=d["name"].replace("English", "Vocabulary")) for d in DECKS]
        restored = DeckTree(renamed, **tree.snapshot())
        self.assertEqual(restored.current.name, "Vocabulary::CET4::Hard")
        self.assertEqual(restored.expanded, {"2", "3"})

    def test_fresh_start_home_saved_review_and_explicit_overrides(self):
        tree = DeckTree(DECKS)
        self.assertEqual(start_location(tree, {}), ("home", None))
        saved = {"view": "review", "review": {"deck_id": "3"}}
        self.assertEqual(start_location(tree, saved)[1].key, "3")
        self.assertEqual(start_location(tree, saved, force_home=True), ("home", None))
        self.assertEqual(start_location(tree, saved, explicit_deck="English::CET6")[1].key, "5")
        deleted = DeckTree([d for d in DECKS if d["id"] != "3" and d["id"] != "4"])
        self.assertEqual(start_location(deleted, saved), ("home", None))

    def test_missing_parent_and_bad_saved_state_are_safe(self):
        tree = DeckTree([DECKS[-1]], selected=[], expanded=[{}])
        self.assertEqual(tree.current.name, "English")
        tree.right()
        tree.right()
        self.assertEqual(tree.current.deck_id, "5")
        self.assertEqual(start_location(tree, {"view": "review", "review": {"deck_id": []}}), ("home", None))


class StoreTests(unittest.TestCase):
    def test_restart_restores_each_profile_independently(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "navigation.json"
            a = NavigationStore(path, "http://local/api/v1", "A")
            b = NavigationStore(path, "http://local/api/v1", "B")
            state = {"view": "home", "home": {"selected": "3", "expanded": ["2"]}}
            a.save(state)
            self.assertEqual(b.load(), {})
            b.save({"view": "review", "review": {"deck_id": "5"}})
            self.assertEqual(NavigationStore(path, "http://local/api/v1", "A").load(), state)
            self.assertEqual(NavigationStore(path, "http://other/api/v1", "A").load(), {})
            self.assertFalse(path.with_suffix(".tmp").exists())

    def test_corrupt_bookmark_falls_back_to_home(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "navigation.json"
            path.write_text("{bad json")
            store = NavigationStore(path, "local", "A")
            self.assertEqual(store.load(), {})
            store.save({"view": "home"})
            self.assertEqual(store.load(), {"view": "home"})


class BookmarkTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.review = Reviewer(self.client, "English")
        self.addCleanup(self.review.close)
        self.review.state = {"card": {"id": "7", "noteId": "8", "scheduling": {"repetitions": 1}},
                             "side": "answer", "stateToken": "old-token", "answers": []}
        self.review.note = {"id": "8", "fields": {"Word": "employer"}}

    def test_restore_same_unanswered_card_side_without_old_token(self):
        bookmark = self.review.bookmark()
        self.assertNotIn("old-token", json.dumps(bookmark))
        self.assertNotIn("employer", json.dumps(bookmark))
        self.review.state["side"] = "question"
        self.review.state["stateToken"] = "fresh-token"
        self.assertTrue(self.review.restore(bookmark))
        self.assertEqual(self.review.state["side"], "answer")
        self.assertEqual(self.review.state["stateToken"], "fresh-token")

    def test_already_answered_or_edited_card_is_not_restored(self):
        bookmark = self.review.bookmark()
        self.review.state["side"] = "question"
        self.review.state["card"]["scheduling"]["repetitions"] += 1
        self.assertFalse(self.review.restore(bookmark))
        self.assertEqual(self.review.state["side"], "question")
        self.review.state["card"]["scheduling"]["repetitions"] -= 1
        self.review.note["fields"]["Word"] = "changed"
        self.assertFalse(self.review.restore(bookmark))

    def test_old_card_must_still_be_in_native_learning_queue(self):
        bookmark = self.review.bookmark()
        old_state, old_note = copy.deepcopy(self.review.state), copy.deepcopy(self.review.note)
        self.review.state["card"]["id"] = "9"
        self.review.state["side"] = "question"
        self.client.col.return_value = {"cards": [{"cardId": "9"}]}
        self.assertFalse(self.review.restore(bookmark))
        self.client.col.return_value = {"cards": [{"cardId": "9"}, {"cardId": "7"}]}
        self.review._read_card = Mock(return_value=(dict(old_state, stateToken="fresh"), old_note))
        self.assertTrue(self.review.restore(bookmark))
        self.assertEqual(self.review.state["card"]["id"], "7")
        self.assertEqual(self.review.state["stateToken"], "fresh")


class FakeClient:
    def __init__(self):
        self.selected = "2"
        self.navigated = []

    def col(self, method, **params):
        if method == "decks.list": return copy.deepcopy(DECKS)
        if method == "scheduling.getQueue": return {"cards": [{"cardId": self.selected + "0"}]}
        if method == "cards.get": return {"id": params["id"], "noteId": params["id"], "templateIndex": 0}
        if method == "notes.get": return {"id": params["id"], "fields": {"Word": "employer", "Meaning": "雇主"}}
        if method == "scheduling.predict": return {"stateToken": "fresh", "answers": [{"rating": "good", "label": "10m"}]}
        if method == "cards.render": return {"questionHtml": "employer", "answerHtml": "雇主"}
        raise AssertionError(method)

    def change(self, method, progress=None, **params):
        if method == "application.navigate":
            self.selected = next(d["id"] for d in DECKS if d["name"] == params["deck"]["name"])
            self.navigated.append(self.selected)
            return {"changed": True}
        raise AssertionError(method)

    def deck_counts(self, deck):
        return {"new": 3, "learning": 0, "review": 0, "total": 3}


if __name__ == "__main__":
    unittest.main()
