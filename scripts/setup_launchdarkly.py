"""Create everything ABC Pulse needs in LaunchDarkly, through the REST API.

One command takes an empty project to a working demo:
  project + environment keys -> flags -> targeting -> flag trigger ->
  experiment metrics -> AI Config -> a check that targeting works

It's safe to re-run: it creates what's missing and leaves anything that
already exists alone. --reset restores the documented demo targeting on
existing flags and the AI Config.

Usage (from the repo root, with the venv active):
    python scripts/setup_launchdarkly.py                      # project/env from .env
    python scripts/setup_launchdarkly.py --project abc-pulse-auto
    python scripts/setup_launchdarkly.py --dry-run            # read-only: show what would happen
    python scripts/setup_launchdarkly.py --reset              # restore demo targeting

LD SETUP: Create an API access token in LaunchDarkly (Organization settings >
Authorization > Create token) with the Writer role (Admin if the script must
create the project), and set LD_API_TOKEN in .env.

The experiment itself is not automated: create and start it in the UI
(README section 3.2). The script prints that as a final step.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
sys.path.insert(0, str(REPO_ROOT))

API_BASE = "https://app.launchdarkly.com"
API_VERSION = "20240415"
SEMANTIC_PATCH = "application/json; domain-model=launchdarkly.semanticpatch"
TAGS = ["abc-pulse"]

# ---------------------------------------------------------------------------
# What to create: mirrors README section 3.2 exactly.
# ---------------------------------------------------------------------------

BOOLEAN = [{"value": True, "name": "On"}, {"value": False, "name": "Off"}]

FLAGS = [
    {
        "key": "account-health-panel",
        "name": "Account health panel",
        "description": "New Account Health experience in the Pulse app. Off = legacy usage-stats table.",
        "variations": BOOLEAN,
        "clientSideAvailability": {"usingEnvironmentId": True, "usingMobileKey": False},
        "defaults": {"onVariation": 0, "offVariation": 1},
    },
    {
        "key": "health-score-v2-calc",
        "name": "Health score v2 calculation",
        "description": "New (intentionally buggy) scoring algorithm. Server-only. Its trigger is the kill switch.",
        "variations": BOOLEAN,
        "clientSideAvailability": {"usingEnvironmentId": False, "usingMobileKey": False},
        "defaults": {"onVariation": 0, "offVariation": 1},
    },
    {
        "key": "landing-hero",
        "name": "Landing hero",
        "description": "Marketing-site hero variant: control, ROI calculator, or social proof.",
        "variations": [
            {"value": "control", "name": "Control"},
            {"value": "roi-calculator", "name": "ROI calculator"},
            {"value": "social-proof", "name": "Social proof"},
        ],
        "clientSideAvailability": {"usingEnvironmentId": True, "usingMobileKey": False},
        "defaults": {"onVariation": 0, "offVariation": 0},
    },
]


def clause(attribute, op, values, context_kind="user"):
    return {"contextKind": context_kind, "attribute": attribute, "op": op, "values": values, "negate": False}


def flag_targeting(flag_key, vid):
    """Semantic-patch instructions that put a flag in its demo starting state.

    vid(value) returns the LaunchDarkly variation ID for a variation value.
    """
    if flag_key in ("account-health-panel", "health-score-v2-calc"):
        beta_rule = {
            "description": "Beta testers (test in production)",
            "clauses": [clause("betaTester", "in", [True])],
            "variationId": vid(True),
        }
    if flag_key == "account-health-panel":
        return [
            {"kind": "replaceTargets", "targets": []},
            {"kind": "replaceRules", "rules": [beta_rule]},
            {"kind": "updateFallthroughVariationOrRollout", "variationId": vid(False)},
            {"kind": "updateOffVariation", "variationId": vid(False)},
            {"kind": "turnFlagOn"},
        ]
    if flag_key == "health-score-v2-calc":
        # Same rule, but OFF: the demo turns it on in step 5 to show the bad release.
        return [
            {"kind": "replaceTargets", "targets": []},
            {"kind": "replaceRules", "rules": [beta_rule]},
            {"kind": "updateFallthroughVariationOrRollout", "variationId": vid(False)},
            {"kind": "updateOffVariation", "variationId": vid(False)},
            {"kind": "turnFlagOff"},
        ]
    if flag_key == "landing-hero":
        control, roi, social = vid("control"), vid("roi-calculator"), vid("social-proof")
        return [
            {"kind": "replaceTargets", "targets": [
                {"contextKind": "user", "variationId": roi, "values": ["qa-tester-01", "sales-demo"]},
            ]},
            # Order matters: the first matching rule wins, so restrictions come first.
            {"kind": "replaceRules", "rules": [
                {"description": "Localization not ready", "clauses": [clause("country", "in", ["DE", "FR"])],
                 "variationId": control},
                {"description": "Compliance review pending for ROI claims",
                 "clauses": [clause("industry", "in", ["Fintech", "Healthcare"])], "variationId": control},
                {"description": "Social channels: peer validation", "clauses": [clause("referrer", "in", ["linkedin"])],
                 "variationId": social},
                {"description": "Enterprise buyers need a business case",
                 "clauses": [clause("companySize", "greaterThanOrEqual", [500])], "variationId": roi},
                {"description": "Experiment audience: English-speaking SMB/mid-market",
                 "clauses": [clause("country", "in", ["US", "GB", "CA", "AU"])], "variationId": control},
            ]},
            # Default rule: 10% rollout of the new hero (weights are thousandths of a percent).
            {"kind": "updateFallthroughVariationOrRollout",
             "rolloutWeights": {control: 90000, roi: 10000, social: 0}},
            {"kind": "updateOffVariation", "variationId": control},
            {"kind": "turnFlagOn"},
        ]
    raise ValueError(flag_key)


METRICS = [
    {"key": "demo-request-clicked", "name": "Demo requests", "eventKey": "demo-request-clicked",
     "description": "Clicks on any 'Request a demo' button (primary experiment metric)."},
    {"key": "pricing-page-viewed", "name": "Pricing page views", "eventKey": "pricing-page-viewed",
     "description": "Clicks on the Pricing link (guardrail metric)."},
]

MODEL_CONFIGS = [
    {"key": "Anthropic.claude-haiku-5-5", "id": "claude-haiku-5-5", "name": "Claude Haiku 5.5", "provider": "Anthropic"},
    {"key": "Anthropic.claude-opus-5-5", "id": "claude-opus-5-5", "name": "Claude Opus 5.5", "provider": "Anthropic"},
]

AI_CONFIG = {
    "key": "account-assistant",
    "name": "Account assistant",
    "mode": "completion",
    "description": "Summarizes a customer account. Model and prompt vary by role.",
}

USER_MESSAGE = {"role": "user", "content": "Account data:\n{{account_json}}"}
AI_VARIATIONS = [
    {
        "key": "exec-brief",
        "name": "exec-brief",
        "modelConfigKey": "Anthropic.claude-haiku-5-5",
        "model": {"name": "claude-haiku-5-5", "parameters": {"max_tokens": 4000},
                  "custom": {"effort": "low", "style": "brief"}},
        "messages": [
            {"role": "system", "content": (
                "You are a customer success analyst briefing an executive. Summarize this account's renewal "
                "risk in exactly 3 short bullets: outlook, biggest risk, and the one decision or ask for "
                "leadership. Plain language, no jargon.")},
            USER_MESSAGE,
        ],
    },
    {
        "key": "csm-deep-dive",
        "name": "csm-deep-dive",
        "modelConfigKey": "Anthropic.claude-opus-5-5",
        "model": {"name": "claude-opus-5-5", "parameters": {"max_tokens": 16000},
                  "custom": {"effort": "medium", "style": "detailed"}},
        "messages": [
            {"role": "system", "content": (
                "You are a senior customer success analyst writing for the CSM who owns this account. Give a "
                "short health summary, the key risk drivers, and 3 to 5 recommended next actions, each with an "
                "owner and timing. Use \"###\" headings and \"-\" bullets.")},
            USER_MESSAGE,
        ],
    },
]


def ai_targeting(vid):
    """Semantic-patch instructions for the AI Config: execs get the brief, everyone else the deep dive."""
    return [
        {"kind": "replaceRules", "rules": [
            {"description": "Executives get a short brief", "clauses": [clause("role", "in", ["Exec"])],
             "variationId": vid("exec-brief")},
        ]},
        {"kind": "updateFallthroughVariationOrRollout", "variationId": vid("csm-deep-dive")},
    ]


# Expected results for the built-in check (README section 5.2 / 5.4).
EXPECTED_HERO = {
    "enterprise-saas": "roi-calculator",
    "midmarket-fintech": "control",
    "german-startup": "control",
    "linkedin-visitor": "social-proof",
    "qa-tester": "roi-calculator",
    "sales-demo": "roi-calculator",
}
EXPECTED_PANEL = {"dana": True, "marco": False}
EXPECTED_AI = {"priya": "exec-brief", "dana": "csm-deep-dive"}

# ---------------------------------------------------------------------------
# Small REST client
# ---------------------------------------------------------------------------


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class LaunchDarklyAPI:
    """Minimal LaunchDarkly REST API client (standard library only)."""

    def __init__(self, token, dry_run=False):
        self.token = token
        self.dry_run = dry_run

    def request(self, method, path, body=None, content_type="application/json"):
        """Send a request. Returns parsed JSON, or None for 404. Writes are skipped in dry-run mode."""
        if self.dry_run and method != "GET":
            return {}
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(API_BASE + path, data=data, method=method, headers={
            "Authorization": self.token,
            "LD-API-Version": API_VERSION,
            "Content-Type": content_type,
        })
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=30) as res:
                    raw = res.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                if e.code == 404 and method == "GET":
                    return None
                if e.code == 429 and attempt < 3:  # rate limited: back off and retry
                    time.sleep(float(e.headers.get("Retry-After") or 2 ** attempt))
                    continue
                raise ApiError(e.code, _error_message(e)) from None
            except urllib.error.URLError as e:
                raise ApiError(0, f"Network error reaching LaunchDarkly: {e.reason}") from None
        raise ApiError(429, "Rate limited by LaunchDarkly; try again in a minute.")

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, body):
        return self.request("POST", path, body)

    def semantic_patch(self, path, environment_key, instructions, comment):
        return self.request("PATCH", path, {
            "environmentKey": environment_key, "comment": comment, "instructions": instructions,
        }, content_type=SEMANTIC_PATCH)


def _error_message(e):
    """Turn an HTTP error into an actionable message."""
    try:
        detail = json.loads(e.read()).get("message", "")
    except Exception:
        detail = ""
    hints = {
        401: "LD_API_TOKEN is invalid or expired.",
        403: "The API token's role doesn't allow this. Use a Writer-role token (Admin to create projects).",
        409: "Conflict: it already exists or was changed concurrently. Re-run the script.",
    }
    return f"HTTP {e.code}: {detail or hints.get(e.code, 'request failed')}" + (
        f" ({hints[e.code]})" if e.code in hints and detail else "")


# ---------------------------------------------------------------------------
# .env helpers: fill blanks only, never overwrite
# ---------------------------------------------------------------------------


def read_env():
    values = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.strip().startswith("#"):
                values[key.strip()] = value.strip().strip("'\"")
    return values


def fill_env_blanks(updates, dry_run):
    """Set .env values that are currently blank. Returns {key: 'written' | 'kept' | 'would write'}."""
    if not ENV_PATH.exists():
        example = REPO_ROOT / ".env.example"
        if not dry_run:
            ENV_PATH.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    current = read_env()
    lines = ENV_PATH.read_text(encoding="utf-8-sig").splitlines() if ENV_PATH.exists() else []
    result = {}
    for key, value in updates.items():
        if current.get(key):
            result[key] = "kept" if current[key] == value else "kept (different value already set)"
            continue
        result[key] = "would write" if dry_run else "written"
        replaced = False
        for i, line in enumerate(lines):
            if line.partition("=")[0].strip() == key:
                lines[i] = f"{key}={value}"
                replaced = True
        if not replaced:
            lines.append(f"{key}={value}")
    if not dry_run and lines:
        ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


# ---------------------------------------------------------------------------
# Setup steps
# ---------------------------------------------------------------------------


def say(symbol, text):
    print(f"  {symbol} {text}")


def setup_project(api, project, environment):
    print(f"\nProject '{project}', environment '{environment}'")
    if api.get(f"/api/v2/projects/{project}") is None:
        if api.dry_run:
            say("[+]", "project doesn't exist: would create it (with Test and Production environments)")
            return None
        api.post("/api/v2/projects", {"name": "ABC Pulse", "key": project, "tags": TAGS})
        say("[+]", "created project")
    else:
        say("[=]", "project exists")

    env = api.get(f"/api/v2/projects/{project}/environments/{environment}")
    if env is None:
        raise ApiError(404, f"Environment '{environment}' not found in project '{project}'. "
                            "Use --environment (new projects have 'test' and 'production').")
    say("[=]", f"environment found (client-side ID {env['_id']})")
    return env


def setup_flags(api, project, environment, reset):
    print("\nFlags and targeting")
    for spec in FLAGS:
        key = spec["key"]
        existing = api.get(f"/api/v2/flags/{project}/{key}")
        if existing is None:
            created = api.post(f"/api/v2/flags/{project}", {**spec, "temporary": True, "tags": TAGS})
            say("[+]", f"{key}: created" + (" (dry run)" if api.dry_run else ""))
            flag, apply_targeting = created, True
        else:
            say("[=]", f"{key}: exists" + ("" if reset else ", targeting left as-is"))
            flag, apply_targeting = existing, reset

        if apply_targeting and not api.dry_run:
            ids = {json.dumps(v["value"]): v["_id"] for v in flag["variations"]}
            api.semantic_patch(f"/api/v2/flags/{project}/{key}", environment,
                               flag_targeting(key, lambda value: ids[json.dumps(value)]),
                               "ABC Pulse demo targeting (scripts/setup_launchdarkly.py)")
            say("[ok]", f"{key}: demo targeting applied")
        elif apply_targeting:
            say("[+]", f"{key}: would apply demo targeting")


def setup_trigger(api, project, environment):
    print("\nFlag trigger (kill switch for health-score-v2-calc)")
    path = f"/api/v2/flags/{project}/health-score-v2-calc/triggers/{environment}"
    try:
        existing = api.get(path)
    except ApiError as e:
        say("[!]", f"couldn't read triggers ({e}). Flag triggers need an Enterprise or trial plan; skipping.")
        return None
    if existing and existing.get("items"):
        say("[=]", "a trigger already exists. Its URL is only shown when created; reset it in the UI if you need it.")
        return None
    if api.dry_run:
        say("[+]", "would create a generic 'turn flag off' trigger")
        return None
    try:
        trigger = api.post(path, {
            "integrationKey": "generic-trigger",
            "instructions": [{"kind": "turnFlagOff"}],
            "comment": "Kill switch: scripts/kill-switch.sh and scripts/watchdog.py",
        })
    except ApiError as e:
        say("[!]", f"couldn't create the trigger ({e}). Your plan may not include flag triggers; skipping.")
        return None
    say("[ok]", "created trigger")
    return trigger.get("triggerURL")


def setup_metrics(api, project):
    print("\nExperiment metrics")
    for m in METRICS:
        if api.get(f"/api/v2/metrics/{project}/{m['key']}") is not None:
            say("[=]", f"{m['key']}: exists")
            continue
        api.post(f"/api/v2/metrics/{project}", {
            **m, "kind": "custom", "isNumeric": False, "successCriteria": "HigherThanBaseline",
            "analysisUnits": ["user"], "tags": TAGS,
        })
        say("[+]", f"{m['key']}: created" + (" (dry run)" if api.dry_run else ""))


def setup_ai_config(api, project, environment, reset):
    print("\nAI Config (AgentControl): account-assistant")
    base = f"/api/v2/projects/{project}/ai-configs"
    try:
        existing = api.get(f"{base}/{AI_CONFIG['key']}")
    except ApiError as e:
        say("[!]", f"AI Configs unavailable ({e}). AgentControl is an add-on; skipping.")
        return

    if existing is None:
        listed = api.get(f"{base}/model-configs") or []
        items = listed.get("items", []) if isinstance(listed, dict) else listed
        have = {m.get("key") for m in items}
        for mc in MODEL_CONFIGS:
            if mc["key"] not in have:
                api.post(f"{base}/model-configs", mc)
                say("[+]", f"model config {mc['key']}: created" + (" (dry run)" if api.dry_run else ""))
        api.post(base, {**AI_CONFIG, "tags": TAGS})
        for variation in AI_VARIATIONS:
            api.post(f"{base}/{AI_CONFIG['key']}/variations", variation)
        say("[+]", "created with variations exec-brief and csm-deep-dive" + (" (dry run)" if api.dry_run else ""))
        apply_targeting = True
    else:
        say("[=]", "exists" + ("" if reset else ", targeting left as-is"))
        apply_targeting = reset

    if apply_targeting and not api.dry_run:
        targeting = api.get(f"{base}/{AI_CONFIG['key']}/targeting")
        ids = {}
        for v in targeting.get("variations", []):
            meta_key = (v.get("value") or {}).get("_ldMeta", {}).get("variationKey") if isinstance(v.get("value"), dict) else None
            ids[meta_key or v.get("name")] = v["_id"]
        api.semantic_patch(f"{base}/{AI_CONFIG['key']}/targeting", environment, ai_targeting(lambda k: ids[k]),
                           "ABC Pulse demo targeting (scripts/setup_launchdarkly.py)")
        say("[ok]", "targeting applied: role Exec -> exec-brief, default -> csm-deep-dive")
    elif apply_targeting:
        say("[+]", "would apply targeting")


def verify(sdk_key):
    """Evaluate the new setup with the server SDK and compare against the README tables."""
    print("\nChecking the setup with the server SDK")
    import logging
    logging.disable(logging.WARNING)
    from ldclient import Context, LDClient
    from ldclient.config import Config
    from ldai.client import LDAIClient

    import assistant
    import personas

    client = LDClient(Config(sdk_key), start_wait=10)
    try:
        if not client.is_initialized():
            say("[!]", "the SDK didn't connect within 10s; skipping the check")
            return True
        ok = True

        def check(label, actual, expected):
            nonlocal ok
            ok &= actual == expected
            say("[ok]" if actual == expected else "[FAIL]", f"{label}: {actual!r}" + ("" if actual == expected else f" (expected {expected!r})"))

        by_id = {p["id"]: p for p in personas.MARKETING_PERSONAS}
        for pid, expected in EXPECTED_HERO.items():
            ctx = Context.from_dict(by_id[pid]["context"])
            check(f"landing-hero for {by_id[pid]['label']}", client.variation("landing-hero", ctx, "control"), expected)
        for pid, expected in EXPECTED_PANEL.items():
            check(f"account-health-panel for {pid}", client.variation("account-health-panel", personas.context_for(pid), False), expected)

        ai = LDAIClient(client)
        for pid, expected in EXPECTED_AI.items():
            config = ai.completion_config("account-assistant", personas.context_for(pid), assistant.FALLBACK_CONFIG)
            check(f"account-assistant for {pid}", assistant._variation_key(config.create_tracker()), expected)
        return ok
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description="Create the ABC Pulse flags, metrics, and AI Config in LaunchDarkly.")
    env = read_env()
    parser.add_argument("--project", default=os.environ.get("LD_PROJECT_KEY") or env.get("LD_PROJECT_KEY") or "abc-pulse")
    parser.add_argument("--environment", default=os.environ.get("LD_ENVIRONMENT_KEY") or env.get("LD_ENVIRONMENT_KEY") or "test")
    parser.add_argument("--dry-run", action="store_true", help="Read only: print what would be created or changed")
    parser.add_argument("--reset", action="store_true", help="Also restore demo targeting on flags/AI Config that already exist")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    token = os.environ.get("LD_API_TOKEN") or env.get("LD_API_TOKEN")
    if not token:
        sys.exit("LD_API_TOKEN is not set. Create an API access token in LaunchDarkly "
                 "(Organization settings > Authorization) with the Writer role and add it to .env.")

    if args.reset and not args.dry_run:
        print("--reset: existing flags and the AI Config will be put back to the documented demo targeting.\n"
              "  Note: landing-hero's rules are replaced, so an experiment running on rule 5 loses its audience.")
    api = LaunchDarklyAPI(token, dry_run=args.dry_run)

    try:
        environment = setup_project(api, args.project, args.environment)
        if environment is None:
            print("\nDry run stopped: the project doesn't exist yet, so there's nothing more to inspect.")
            return
        setup_flags(api, args.project, args.environment, args.reset)
        trigger_url = setup_trigger(api, args.project, args.environment)
        setup_metrics(api, args.project)
        setup_ai_config(api, args.project, args.environment, args.reset)
    except ApiError as e:
        sys.exit(f"\nStopped: {e}")

    # Fill in blank .env values; never overwrite existing ones.
    updates = {"LD_SDK_KEY": environment["apiKey"], "LD_CLIENT_SIDE_ID": environment["_id"]}
    if trigger_url:
        updates["LD_TRIGGER_URL"] = trigger_url
    print("\n.env")
    env_results = fill_env_blanks(updates, args.dry_run)
    for key, status in env_results.items():
        say("[=]" if status.startswith("kept") else "[+]", f"{key}: {status}")
    mismatched = [k for k, s in env_results.items() if "different" in s]

    ok = True if args.dry_run else verify(environment["apiKey"])

    print("\nRemaining manual steps (README section 3.2):")
    print("  1. Create and START the experiment 'Landing hero: ROI calculator vs control' on landing-hero rule 5.")
    if mismatched:
        print(f"  2. .env already has different values for {', '.join(mismatched)} (another project or "
              f"environment). To run the app against '{args.project}', replace them with this environment's keys.")
    print(f"  {3 if mismatched else 2}. Restart the app: python app.py")
    if not ok:
        sys.exit("\nSome checks failed. Compare with README section 3.2, or re-run with --reset.")


if __name__ == "__main__":
    main()
