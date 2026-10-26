import copy
import unittest
from unittest.mock import Mock

from anki_x.api import AnkiError, ConnectionError
from anki_x.review import Reviewer


class PredictionRefreshTests(unittest.TestCase):
    def setUp(self):
        self.card = {"id": "7", "noteId": "8", "modifiedAt": "2026-10-26T00:00:00Z",
                     "scheduling": {"type": "learning", "repetitions": 1}}
        self.note = {"id": "8", "fields": {"Word": "employer", "Meaning": "雇主"}}
        self.answers = [{"rating": "good", "label": "10m", "interval": {"value": 600, "unit": "seconds"}}]
        self.client = Mock()
        self.review = Reviewer(self.client, "English")
        self.addCleanup(self.review.close)
        self.review.state = {"card": copy.deepcopy(self.card), "side": "answer",
                             "stateToken": "old-display-token", "answers": self.answers}
        self.review.note = copy.deepcopy(self.note)
        self.review.refresh = Mock()
        self.predictions = 0

        def read(method, **params):
            if method == "scheduling.predict":
                self.predictions += 1
                return {"stateToken": f"fresh-{self.predictions}", "answers": self.answers}
            if method == "cards.get":
                return copy.deepcopy(self.card)
            if method == "notes.get":
                return copy.deepcopy(self.note)
            raise AssertionError(method)

        self.client.col.side_effect = read
        self.client.change.return_value = {"cardId": "7", "reviewId": "99"}

    def stale(self):
        return AnkiError("Prediction/conversion token is stale.", data={"type": "conflict"})

    def test_fetches_current_prediction_at_the_time_of_grading(self):
        self.review.grade("good")
        self.assertEqual(self.client.change.call_args.kwargs["stateToken"], "fresh-1")
        self.assertEqual(self.review.reviewed, 1)

    def test_explicit_prewrite_clock_conflict_can_retry_with_a_fresh_token(self):
        self.client.change.side_effect = [self.stale(), {"cardId": "7", "reviewId": "99"}]
        self.review.grade("good")
        tokens = [call.kwargs["stateToken"] for call in self.client.change.call_args_list]
        self.assertEqual(tokens, ["fresh-1", "fresh-2"])
        self.assertEqual(self.review.reviewed, 1)

    def test_card_already_answered_elsewhere_is_not_answered_again(self):
        self.card["scheduling"]["repetitions"] += 1
        with self.assertRaises(AnkiError):
            self.review.grade("good")
        self.client.change.assert_not_called()
        self.assertEqual(self.review.reviewed, 0)

    def test_note_changed_after_display_requires_reviewing_again(self):
        self.note["fields"]["Meaning"] = "changed meaning"
        with self.assertRaises(AnkiError):
            self.review.grade("good")
        self.client.change.assert_not_called()

    def test_real_change_during_a_clock_conflict_is_not_retried(self):
        def race(*args, **kwargs):
            self.card["scheduling"]["repetitions"] += 1
            raise self.stale()

        self.client.change.side_effect = race
        with self.assertRaises(AnkiError):
            self.review.grade("good")
        self.assertEqual(self.client.change.call_count, 1)

    def test_lost_response_never_retries_an_uncertain_answer(self):
        self.client.change.side_effect = ConnectionError("lost response")
        with self.assertRaises(ConnectionError):
            self.review.grade("good")
        self.assertEqual(self.client.change.call_count, 1)
        self.assertEqual(self.review.reviewed, 0)

    def test_persistent_conflicts_are_bounded_and_do_not_count_as_reviews(self):
        self.client.change.side_effect = self.stale()
        with self.assertRaises(AnkiError) as caught:
            self.review.grade("good")
        self.assertNotIn("Prediction/conversion", str(caught.exception))
        self.assertLessEqual(self.client.change.call_count, 4)
        self.assertEqual(self.review.reviewed, 0)


if __name__ == "__main__":
    unittest.main()
