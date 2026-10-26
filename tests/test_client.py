import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from anki_x.api import AnkiError, Client, ConnectionError, PendingOperation
from anki_x.render import card_text, text_from_html, width, wrap
from anki_x.review import Reviewer


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.journal = Path(self.temp.name) / "pending.json"
        self.client = Client(journal=self.journal, operation_timeout=0)
        self.client.session = "test-session"

    def test_accepted_answer_remains_pending_and_resume_does_not_resubmit(self):
        handle = {"operationId": "op-1"}
        self.client.call = Mock(side_effect=[handle, {"state": "running"},
                                             {"state": "succeeded", "result": {"cardId": "7"}}])
        with self.assertRaises(PendingOperation):
            self.client.change("reviewer.answer", stateToken="answer-7", rating="good")
        self.assertTrue(self.journal.exists())
        with self.assertRaises(AnkiError):
            self.client.change("reviewer.answer", stateToken="answer-7", rating="good")
        result = self.client.recover()
        self.assertEqual(result, {"cardId": "7"})
        self.assertFalse(self.journal.exists())
        methods = [c.args[0] for c in self.client.call.call_args_list]
        self.assertEqual(methods, ["reviewer.answer", "operations.get", "operations.get"])

    def test_lost_response_leaves_intent_and_blocks_resubmission(self):
        self.client.call = Mock(side_effect=ConnectionError("lost"))
        with self.assertRaises(ConnectionError):
            self.client.change("reviewer.answer", stateToken="old-token", rating="again")
        record = json.loads(self.journal.read_text())
        self.assertEqual(record["state"], "sending")
        with self.assertRaises(AnkiError):
            self.client.recover()
        with self.assertRaises(AnkiError):
            self.client.change("reviewer.answer", stateToken="old-token", rating="again")
        self.assertEqual(self.client.call.call_count, 1)

    def test_failed_operation_is_not_a_success(self):
        self.client.call = Mock(side_effect=[{"operationId": "op-2"},
            {"state": "failed", "error": {"code": 1015, "message": "vetoed"}}])
        with self.assertRaisesRegex(AnkiError, "vetoed"):
            self.client.change("reviewer.answer", stateToken="token", rating="good")
        self.assertFalse(self.journal.exists())

    def test_review_count_waits_for_completion(self):
        client = Mock()
        review = Reviewer(client, "English")
        self.addCleanup(review.close)
        review.state = {"card": {"id": "7"}, "side": "answer", "stateToken": "t",
                        "answers": [{"rating": "good"}]}
        client.col.side_effect = [{"stateToken": "fresh", "answers": [{"rating": "good"}]}, {"id": "7"}]
        client.change.side_effect = PendingOperation({"operationId": "op"})
        with self.assertRaises(PendingOperation):
            review.grade("good")
        self.assertEqual(review.reviewed, 0)
        client.recover.return_value = {"cardId": "7"}
        review.refresh = Mock()
        review.recover()
        self.assertEqual(review.reviewed, 1)
        self.assertTrue(review.can_undo)

    def test_question_cannot_be_graded(self):
        client = Mock()
        review = Reviewer(client, "English")
        self.addCleanup(review.close)
        review.state = {"card": {"id": "7"}, "side": "question"}
        with self.assertRaises(AnkiError):
            review.grade("good")
        client.change.assert_not_called()

    def test_empty_default_deck_has_zero_counts_without_hiding_real_errors(self):
        missing = AnkiError("Deck counts unavailable", data={"type": "notFound"})
        self.client.col = Mock(side_effect=[missing, {"id": "1", "name": "Default"}, {"ids": []}])
        self.assertEqual(self.client.deck_counts({"id": "1"})["total"], 0)
        self.client.col = Mock(side_effect=[missing, {"id": "1", "name": "Default"}, {"ids": ["7"]}])
        with self.assertRaises(AnkiError):
            self.client.deck_counts({"id": "1"})


class RenderingTests(unittest.TestCase):
    def test_actual_vocabulary_shape_does_not_leak_answer(self):
        note = {"fields": {"英语单词": "abandon", "英美音标": "[əˈbændən]",
            "Front": "legacy front", "Back": "extra dictionary material",
            "中文释义": "放弃", "英语例句": "Do not abandon hope.", "中文例句": "不要放弃希望。"}}
        state = {"side": "question", "card": {"templateIndex": 0}}
        self.assertEqual(card_text(state, note), "abandon\n\n[əˈbændən]")
        state["side"] = "answer"
        answer = card_text(state, note)
        self.assertIn("放弃", answer)
        self.assertIn("Do not abandon hope.\n不要放弃希望。", answer)
        self.assertNotIn("extra dictionary", answer)
        self.assertIn("extra dictionary", card_text(state, note, "details"))

    def test_html_hides_script_style_and_hidden_content(self):
        html = '<style>.secret {display:none}</style><div class="secret">answer</div><p>hello<br>world</p><script>bad()</script>'
        self.assertEqual(text_from_html(html, '.secret {display:none}'), "hello\nworld")
        self.assertNotIn("hidden", text_from_html('<span hidden>hidden</span><b>visible</b>'))

    def test_reverse_card_uses_rendered_question(self):
        state = {"side": "question", "card": {"templateIndex": 1}, "rendered": {"questionHtml": "放弃"}}
        self.assertEqual(card_text(state, {"fields": {"英语单词": "abandon"}}), "放弃")

    def test_unicode_width_and_control_characters(self):
        self.assertEqual(width("你好 abc"), 8)
        self.assertTrue(all(width(line) <= 6 for line in wrap("你好 world 世界", 6)))
        self.assertNotIn("\x1b", text_from_html("word\x1b[2J"))


if __name__ == "__main__":
    unittest.main()
