"""Account assistant: an AI summary of a customer account, managed by a LaunchDarkly AI Config.

The AI Config `account-assistant` (shown as "AgentControl" in newer LaunchDarkly
docs) decides, per user, which MODEL and which PROMPT to use. A PM can change
either one in LaunchDarkly and the next request uses it, with no deploy. The
SDK also records duration, tokens, success/error, and user feedback, shown on
the AI Config's Monitoring tab.

Providers:
  anthropic  used when LLM_API_KEY (an Anthropic API key) is set
  mock       otherwise: a deterministic summary built from the account data,
             so the demo runs with no API key and no cost

SDK choice: this uses the stable `launchdarkly-server-sdk-ai` package (sync,
fallback defaults, feedback tracking). LaunchDarkly's newer AgentControl SDK
(`launchdarkly-ai-server`) is in open beta and async-only. Migrating would be
contained to this module. See README section 7.
"""

import base64
import json
import logging
import os
import time

import anthropic
import ldclient
from ldai.client import LDAIClient
from ldai.models import AICompletionConfigDefault, LDMessage, ModelConfig, ProviderConfig
from ldai.tracker import FeedbackKind, LDAIConfigTracker, TokenUsage

from flags import AI_CONFIG_ACCOUNT_ASSISTANT

log = logging.getLogger("abc_pulse.assistant")

# Claude models that support the server-side refusal fallback: if a safety
# check declines the request, Anthropic re-runs it on a recommended fallback
# model instead of returning a refusal. Haiku has no server-side fallback.
SERVER_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
SERVER_FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Used when LaunchDarkly is unreachable or the AI Config doesn't exist yet: a
# conservative, cheap brief, so the assistant keeps working (same principle as
# the feature-flag fallbacks in flags.py).
FALLBACK_CONFIG = AICompletionConfigDefault(
    enabled=True,
    model=ModelConfig("claude-haiku-5-5", parameters={"maxTokens": 4000}, custom={"effort": "low", "style": "brief"}),
    provider=ProviderConfig("anthropic"),
    messages=[
        LDMessage(role="system", content=(
            "You are a customer success analyst. Summarize the account's renewal risk "
            "in exactly 3 short bullets, in plain language."
        )),
        LDMessage(role="user", content="Account data:\n{{account_json}}"),
    ],
)

# Fields sent to the model: enough for a useful summary, nothing more.
PROMPT_FIELDS = [
    "name", "industry", "plan", "seats", "arr", "renewalDate", "csmOwner", "weeklyActiveUsers",
    "seatUtilization", "featureAdoption", "nps", "openTickets", "timeToValueDays", "qbrCompleted",
    "healthScore", "renewalLikelihood", "riskDrivers",
]

_ai_client = None


class AssistantError(Exception):
    """A user-presentable assistant failure (provider error, refusal, ...)."""


def _ai():
    """The LaunchDarkly AI client, created on first use (after ld.init_ld() has run)."""
    global _ai_client
    if _ai_client is None:
        _ai_client = LDAIClient(ldclient.get())
    return _ai_client


def _variation_key(tracker):
    """Read the served variation's key from the tracker's (public) resumption token."""
    token = tracker.resumption_token
    payload = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    return payload.get("variationKey") or "fallback"


def summarize(account, context):
    """Summarize one account for the current user, as the AI Config directs.

    Returns a dict for the API response. Raises AssistantError on provider failures.
    """
    prompt_account = {k: account[k] for k in PROMPT_FIELDS}
    config = _ai().completion_config(
        AI_CONFIG_ACCOUNT_ASSISTANT,
        context,
        FALLBACK_CONFIG,
        variables={"account_name": account["name"], "account_json": json.dumps(prompt_account, indent=2)},
    )

    # Turning the AI Config off in LaunchDarkly is an instant kill switch for the feature.
    if not config.enabled:
        return {"enabled": False, "message": "The account assistant is turned off."}

    tracker = config.create_tracker()
    use_mock = not os.environ.get("LLM_API_KEY", "").strip()
    started = time.monotonic()
    try:
        text, usage = _call_mock(config, account) if use_mock else _call_anthropic(config)
    except AssistantError:
        tracker.track_error()
        raise
    duration_ms = int((time.monotonic() - started) * 1000)

    # These metrics appear on the AI Config's Monitoring tab, per variation.
    tracker.track_duration(duration_ms)
    tracker.track_tokens(usage)
    tracker.track_success()

    return {
        "enabled": True,
        "text": text,
        "variation": _variation_key(tracker),
        "model": config.model.name if config.model else None,
        "provider": "mock" if use_mock else "anthropic",
        "durationMs": duration_ms,
        "tokens": {"input": usage.input, "output": usage.output, "total": usage.total},
        # Lets the browser send thumbs up/down for THIS response later.
        "feedbackToken": tracker.resumption_token,
    }


def record_feedback(token, positive, context):
    """Attach a thumbs up/down to an earlier response, identified by its feedback token."""
    result = LDAIConfigTracker.from_resumption_token(token, ldclient.get(), context)
    if not result.is_success():
        log.warning("Rejected feedback token: %s", result.error)
        raise AssistantError("Invalid feedback token.")
    kind = FeedbackKind.Positive if positive else FeedbackKind.Negative
    result.value.track_feedback({"kind": kind})


# ---------------------------------------------------------------------------
# Anthropic (Claude) provider
# ---------------------------------------------------------------------------

def build_anthropic_request(config):
    """Translate the AI Config variation into Messages API arguments.

    The model, max tokens, effort, and prompt all come from LaunchDarkly.
    """
    model = config.model.name
    system = "\n\n".join(m.content for m in config.messages or [] if m.role == "system")
    messages = [{"role": m.role, "content": m.content} for m in config.messages or [] if m.role != "system"]

    # The LaunchDarkly UI may store the limit as max_tokens or maxTokens; accept either.
    max_tokens = config.model.get_parameter("max_tokens") or config.model.get_parameter("maxTokens")
    request = {
        "model": model,
        "max_tokens": int(max_tokens or 4000),
        "messages": messages,
    }
    if system:
        request["system"] = system
    # Current Claude models are steered with effort (low/medium/high/...) rather
    # than temperature, and reject sampling parameters. So a temperature set in
    # the AI Config is ignored, not forwarded.
    effort = config.model.get_custom("effort")
    if effort:
        request["output_config"] = {"effort": effort}
    if config.model.get_parameter("temperature") is not None:
        log.info("Ignoring temperature from AI Config: %s doesn't accept sampling parameters", model)
    return request


def _call_anthropic(config):
    """Call Claude with the configured model and prompt. Returns (text, TokenUsage)."""
    request = build_anthropic_request(config)
    # LD SETUP: LLM_API_KEY in .env must be an Anthropic API key. If it's blank,
    # the mock provider is used instead.
    client = anthropic.Anthropic(api_key=os.environ["LLM_API_KEY"].strip())
    try:
        if request["model"] in SERVER_FALLBACK_MODELS:
            response = client.beta.messages.create(
                **request, betas=[SERVER_FALLBACK_BETA], fallbacks="default",
            )
        else:
            response = client.messages.create(**request)
    except anthropic.RateLimitError as e:
        raise AssistantError("The AI provider is rate limiting requests. Try again shortly.") from e
    except anthropic.AuthenticationError as e:
        raise AssistantError("The AI provider rejected the API key. Check LLM_API_KEY.") from e
    except anthropic.APIStatusError as e:
        raise AssistantError(f"The AI provider returned an error (HTTP {e.status_code}).") from e
    except anthropic.APIConnectionError as e:
        raise AssistantError("Couldn't reach the AI provider. Check your network.") from e

    if response.stop_reason == "refusal":
        raise AssistantError("The model declined to summarize this account.")

    text = "\n".join(block.text for block in response.content if block.type == "text").strip()
    usage = TokenUsage(
        total=response.usage.input_tokens + response.usage.output_tokens,
        input=response.usage.input_tokens,
        output=response.usage.output_tokens,
    )
    return text, usage


# ---------------------------------------------------------------------------
# Mock provider: no API key needed
# ---------------------------------------------------------------------------

def _call_mock(config, account):
    """A deterministic summary built from the data, shaped by the AI Config.

    The custom `style` parameter picks brief vs. detailed output, and the
    footer quotes the first line of the configured system prompt, so editing
    the prompt in LaunchDarkly is visible even without a real model.
    """
    brief = (config.model.get_custom("style") if config.model else None) != "detailed"
    time.sleep(0.6 if brief else 1.4)  # roughly realistic latency for the loading state

    risks = account["riskDrivers"] or ["No significant risk drivers"]
    lines = (_mock_brief if brief else _mock_detailed)(account, risks)

    system = next((m.content for m in config.messages or [] if m.role == "system"), "")
    first_line = system.strip().splitlines()[0] if system.strip() else "(no system prompt)"
    lines += ["", f"[Mock response. Prompt from LaunchDarkly: “{first_line[:140]}”]"]

    text = "\n".join(lines)
    prompt_chars = sum(len(m.content) for m in config.messages or [])
    usage = TokenUsage(total=0, input=prompt_chars // 4, output=len(text) // 4)  # rough estimate
    usage.total = usage.input + usage.output
    return text, usage


def _mock_brief(a, risks):
    return [
        f"- **Renewal outlook:** {a['renewalLikelihood']} likelihood (health {a['healthScore']}/100), "
        f"renewing {a['renewalDate']} at ${a['arr']:,} ARR.",
        f"- **Biggest risk:** {risks[0]}.",
        "- **Ask:** " + ("confirm the renewal plan with the CSM this week."
                         if a["renewalLikelihood"] != "high" else "no action needed; consider an expansion conversation."),
    ]


def _mock_detailed(a, risks):
    adoption = sorted(a["featureAdoption"].items(), key=lambda kv: kv[1])
    actions = []
    if not a["qbrCompleted"]:
        actions.append(f"Schedule a QBR in the next 2 weeks (owner: {a['csmOwner']}).")
    if a["seatUtilization"] < 60:
        actions.append(f"Run an activation campaign for unused seats (owner: {a['csmOwner']}, 30 days).")
    actions.append(f"Enablement session on {adoption[0][0]} ({adoption[0][1]}% adoption) within 30 days.")
    if a["openTickets"] >= 5:
        actions.append(f"Escalate the {a['openTickets']} open tickets with Support leadership this week.")
    if a["renewalLikelihood"] == "high":
        actions.append("Prepare an expansion proposal ahead of renewal.")

    return [
        "### Health summary",
        f"{a['name']} ({a['plan']}, {a['seats']:,} seats, ${a['arr']:,} ARR) has a health score of "
        f"{a['healthScore']}/100 and a {a['renewalLikelihood']} renewal likelihood. "
        f"Seat utilization is {a['seatUtilization']}%, NPS is {a['nps']:+d}, and renewal is due {a['renewalDate']}.",
        "",
        "### Risk drivers",
        *[f"- {r}" for r in risks],
        "",
        "### Recommended next actions",
        *[f"- {x}" for x in actions[:5]],
    ]
