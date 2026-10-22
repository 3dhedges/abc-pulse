"""LaunchDarkly flag and config keys used by the Python server.

Each key is defined once here so a typo can't silently evaluate a flag that
doesn't exist (which would quietly return the fallback value). The browser
keeps its own copy of these keys at the top of static/js/ld.js.

LD SETUP: Each key below must exist in your LaunchDarkly project with exactly
this key. scripts/setup_launchdarkly.py creates them for you, or follow the
manual steps in README.md.
"""

# Part 1, Release & Remediate (boolean): the new Account Health panel in /app.
# Toggling it releases or rolls back the panel live. A flag trigger turns it off.
ACCOUNT_HEALTH_PANEL = "account-health-panel"

# Part 1, Remediation (boolean): switches to a deliberately buggy v2 scoring
# algorithm, so we can show a bad release being caught and killed. Its flag
# trigger (LD_TRIGGER_URL) turns it off. Server-side only.
HEALTH_SCORE_V2_CALC = "health-score-v2-calc"

# Part 2, Target + Experiment (string): landing-page hero variant on /.
# Variations: "control", "roi-calculator", "social-proof".
LANDING_HERO = "landing-hero"

# Extra credit, AI Configs: model and prompt for the account assistant.
ACCOUNT_ASSISTANT = "account-assistant"

# Experiment metric (custom conversion event) sent with track() on the demo CTA.
METRIC_DEMO_REQUEST_CLICKED = "demo-request-clicked"

# Value served when LaunchDarkly can't be reached, the SDK key is missing, or
# the flag doesn't exist yet. Each fallback is the safe, existing experience,
# so an outage never releases an unfinished feature.
FALLBACKS = {
    ACCOUNT_HEALTH_PANEL: False,
    HEALTH_SCORE_V2_CALC: False,
    LANDING_HERO: "control",
}

# Flags evaluated only on the server. They're NOT made available to
# client-side SDKs; the browser reads their values from /api/server-flags.
SERVER_FLAGS = [HEALTH_SCORE_V2_CALC]
