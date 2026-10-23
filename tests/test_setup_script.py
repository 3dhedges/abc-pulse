"""Request building: LaunchDarkly setup instructions and the Claude request."""

import json
import unittest

import support  # noqa: F401
import assistant
import setup_launchdarkly as setup
from ldai.models import LDMessage, ModelConfig
from ldclient.impl.operators import ops as SDK_OPERATORS

FLAG_INSTRUCTIONS = {
    "replaceTargets", "replaceRules", "updateFallthroughVariationOrRollout",
    "updateOffVariation", "turnFlagOn", "turnFlagOff",
}


def fake_ids(values):
    """Map variation values to fake variation IDs."""
    return {json.dumps(v): f"id-{i}" for i, v in enumerate(values)}


class SetupInstructionsTest(unittest.TestCase):
    def check(self, instructions, ids):
        for ins in instructions:
            self.assertIn(ins["kind"], FLAG_INSTRUCTIONS)
            for rule in ins.get("rules", []):
                self.assertIn(rule["variationId"], ids)
                for clause in rule["clauses"]:
                    self.assertIn(clause["op"], SDK_OPERATORS)
            if "rolloutWeights" in ins:
                self.assertEqual(sum(ins["rolloutWeights"].values()), 100000)

    def test_flag_targeting_for_every_flag(self):
        for spec in setup.FLAGS:
            ids = fake_ids([v["value"] for v in spec["variations"]])
            instructions = setup.flag_targeting(spec["key"], lambda value: ids[json.dumps(value)])
            self.check(instructions, set(ids.values()))

    def test_v2_flag_starts_off(self):
        ids = fake_ids([True, False])
        kinds = [i["kind"] for i in setup.flag_targeting("health-score-v2-calc", lambda v: ids[json.dumps(v)])]
        self.assertIn("turnFlagOff", kinds)

    def test_landing_hero_rule_order(self):
        ids = fake_ids(["control", "roi-calculator", "social-proof"])
        rules = next(i for i in setup.flag_targeting("landing-hero", lambda v: ids[json.dumps(v)])
                     if i["kind"] == "replaceRules")["rules"]
        attributes = [r["clauses"][0]["attribute"] for r in rules]
        self.assertEqual(attributes, ["country", "industry", "referrer", "companySize", "country"])

    def test_ai_targeting(self):
        instructions = setup.ai_targeting(lambda key: f"id-{key}")
        self.assertEqual(instructions[0]["rules"][0]["variationId"], "id-exec-brief")
        self.assertEqual(instructions[1]["variationId"], "id-csm-deep-dive")


class AnthropicRequestTest(unittest.TestCase):
    def config(self, parameters, custom=None, model="claude-opus-5-5"):
        class Config:
            pass
        c = Config()
        c.model = ModelConfig(model, parameters=parameters, custom=custom)
        c.messages = [LDMessage("system", "Be brief."), LDMessage("user", "Account data: {}")]
        return c

    def test_maps_config_to_request(self):
        req = assistant.build_anthropic_request(self.config({"max_tokens": 16000, "temperature": 0.7}, {"effort": "medium"}))
        self.assertEqual(req["model"], "claude-opus-5-5")
        self.assertEqual(req["max_tokens"], 16000)
        self.assertEqual(req["system"], "Be brief.")
        self.assertEqual(req["messages"], [{"role": "user", "content": "Account data: {}"}])
        self.assertEqual(req["output_config"], {"effort": "medium"})
        self.assertNotIn("temperature", req)  # current Claude models reject sampling parameters

    def test_max_tokens_spellings_and_default(self):
        self.assertEqual(assistant.build_anthropic_request(self.config({"maxTokens": 1234}))["max_tokens"], 1234)
        self.assertEqual(assistant.build_anthropic_request(self.config({}))["max_tokens"], 4000)

    def test_refusal_fallback_only_for_supported_models(self):
        self.assertIn("claude-opus-5-5", assistant.SERVER_FALLBACK_MODELS)
        self.assertNotIn("claude-haiku-5-5", assistant.SERVER_FALLBACK_MODELS)


if __name__ == "__main__":
    unittest.main()
