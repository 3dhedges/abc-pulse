"""API smoke tests with LaunchDarkly offline (every flag serves its fallback)."""

import unittest
from unittest import mock

import support  # noqa: F401  (must come first: isolates env and .env)
import app as app_module
import assistant
import ld


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        app_module.HEALTH_MONITOR._events.clear()
        # The mock assistant sleeps to look realistic; not needed in tests.
        patcher = mock.patch.object(assistant.time, "sleep", lambda s: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_pages(self):
        for path in ("/", "/app"):
            with self.client.get(path) as resp:  # closes the static file
                self.assertEqual(resp.status_code, 200, path)

    def test_accounts(self):
        accounts = self.client.get("/api/accounts").get_json()
        self.assertEqual(len(accounts), 50)
        self.assertEqual(self.client.get("/api/accounts/acct-001").get_json()["id"], "acct-001")
        self.assertEqual(self.client.get("/api/accounts/nope").status_code, 404)

    def test_health_score_uses_v1_fallback(self):
        body = self.client.get("/api/accounts/acct-001/health").get_json()
        self.assertEqual(body["algorithm"], "v1")
        self.assertEqual(self.client.get("/api/health").get_json()["status"], "ok")

    def test_buggy_v2_returns_500s_and_degrades_health(self):
        real = ld.evaluate
        with mock.patch.object(ld, "evaluate", lambda key, ctx: True if key == "health-score-v2-calc" else real(key, ctx)):
            codes = [self.client.get(f"/api/accounts/{a}/health").status_code for a in app_module.ACCOUNTS]
        self.assertEqual(codes.count(500), 5)
        health = self.client.get("/api/health").get_json()
        self.assertEqual(health["status"], "degraded")
        self.assertEqual(health["errors"], 5)

    def test_server_flags_and_status(self):
        self.assertEqual(self.client.get("/api/server-flags").get_json(), {"health-score-v2-calc": False})
        self.assertEqual(self.client.get("/api/status").get_json()["server"]["state"], "not-configured")

    def test_config_exposes_personas_not_server_key(self):
        body = self.client.get("/api/config").get_json()
        self.assertEqual(body["clientSideId"], "")
        self.assertEqual({p["id"] for p in body["personas"]["app"]}, {"dana", "marco", "priya", "alex"})
        self.assertNotIn("sdk-", str(body))

    def test_assistant_mock_and_feedback(self):
        resp = self.client.post("/api/assistant", json={"accountId": "acct-001"}, headers={"X-Persona": "priya"})
        body = resp.get_json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual((body["provider"], body["variation"]), ("mock", "fallback"))
        self.assertIn("Renewal outlook", body["text"])
        fb = self.client.post("/api/assistant/feedback", json={"token": body["feedbackToken"], "positive": True})
        self.assertEqual(fb.status_code, 200)

    def test_assistant_bad_input(self):
        self.assertEqual(self.client.post("/api/assistant", json={"accountId": "nope"}).status_code, 404)
        self.assertEqual(self.client.post("/api/assistant/feedback", json={}).status_code, 400)
        bad = self.client.post("/api/assistant/feedback", json={"token": "not-a-token", "positive": False})
        self.assertEqual(bad.status_code, 400)


if __name__ == "__main__":
    unittest.main()
