"""Health-score algorithms: v1 is trusted, v2 has a deliberate bug."""

import json
import unittest

import support
import scoring


class ScoringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.accounts = json.loads((support.REPO_ROOT / "data" / "accounts.json").read_text(encoding="utf-8"))

    def test_v1_matches_seeded_scores(self):
        for a in self.accounts:
            self.assertEqual(scoring.health_score_v1(a), a["healthScore"], a["id"])

    def test_v2_fails_exactly_on_zero_ticket_accounts(self):
        failed = set()
        for a in self.accounts:
            try:
                score = scoring.health_score_v2(a)
                self.assertTrue(0 <= score <= 100)
            except ZeroDivisionError:
                failed.add(a["id"])
        expected = {a["id"] for a in self.accounts if a["openTickets"] == 0}
        self.assertEqual(failed, expected)
        self.assertTrue(failed, "the demo needs at least one failing account")

    def test_renewal_likelihood_buckets(self):
        self.assertEqual(scoring.renewal_likelihood(70), "high")
        self.assertEqual(scoring.renewal_likelihood(69), "medium")
        self.assertEqual(scoring.renewal_likelihood(45), "medium")
        self.assertEqual(scoring.renewal_likelihood(44), "low")


if __name__ == "__main__":
    unittest.main()
