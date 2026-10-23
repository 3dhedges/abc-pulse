"""ABC Pulse: Flask server for the marketing site and the Pulse app.

Routes
    /                        marketing landing page (static/index.html)
    /app                     Pulse app for customer success managers (static/app.html)
    GET /api/accounts               all customer accounts
    GET /api/accounts/<id>          one account, or 404
    GET /api/accounts/<id>/health   health score (v1 or v2, per the health-score-v2-calc flag)
    GET /api/health                 error rate of health calculations (watchdog signal)
    GET /api/server-flags           server-evaluated flag values for the current persona
    POST /api/assistant             AI account summary (model + prompt from the AI Config)
    POST /api/assistant/feedback    thumbs up/down on a summary
    GET /api/config                 browser config: LaunchDarkly client-side ID + demo personas
    GET /api/status                 server-side LaunchDarkly SDK connection state

Requests from the Pulse app send an X-Persona header (the demo persona), so
server-side flags are evaluated for the same context as in the browser.

Run:  python app.py   (then open http://localhost:5000)
"""

import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request, send_from_directory

# Load .env before anything reads os.environ (including ld.py). If .env is
# missing, this does nothing; the app still runs with defaults.
load_dotenv()

import assistant  # noqa: E402  (must come after load_dotenv)
import ld  # noqa: E402
import personas  # noqa: E402
import scoring  # noqa: E402
from flags import HEALTH_SCORE_V2_CALC, SERVER_FLAGS  # noqa: E402
from health_monitor import ErrorRateMonitor  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("abc_pulse")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
ACCOUNTS_PATH = BASE_DIR / "data" / "accounts.json"

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")


def load_accounts():
    """Read the seeded accounts once at startup and index them by id."""
    if not ACCOUNTS_PATH.exists():
        sys.exit(
            f"Missing {ACCOUNTS_PATH}.\n"
            "Generate it with:  python scripts/seed_data.py"
        )
    with ACCOUNTS_PATH.open(encoding="utf-8") as f:
        accounts = json.load(f)
    return {a["id"]: a for a in accounts}


ACCOUNTS = load_accounts()

# Connect to LaunchDarkly once per process. Without LD_SDK_KEY this runs
# offline and every flag uses its fallback value.
ld.init_ld()

# Tracks failed health-score calculations for /api/health.
HEALTH_MONITOR = ErrorRateMonitor()


def current_context():
    """LaunchDarkly context for this request's persona (default: Dana)."""
    return personas.context_for(request.headers.get("X-Persona"))


@app.get("/")
def marketing_page():
    """Public marketing landing page."""
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/app")
def pulse_app():
    """Logged-in Pulse app for CSMs."""
    return send_from_directory(STATIC_DIR, "app.html")


@app.get("/api/accounts")
def list_accounts():
    """Return every account, sorted by name."""
    return jsonify(sorted(ACCOUNTS.values(), key=lambda a: a["name"]))


@app.get("/api/accounts/<account_id>")
def get_account(account_id):
    """Return one account by id, or 404 if it doesn't exist."""
    account = ACCOUNTS.get(account_id)
    if account is None:
        abort(404, description=f"Account {account_id!r} not found")
    return jsonify(account)


@app.get("/api/accounts/<account_id>/health")
def get_account_health(account_id):
    """Health score for one account, using the algorithm the flag selects.

    `health-score-v2-calc` is evaluated on the server for the current persona,
    so v2 can be released to beta testers first. The flag stays server-only:
    the browser never needs it, so it isn't exposed to client-side SDKs.
    """
    account = ACCOUNTS.get(account_id)
    if account is None:
        abort(404, description=f"Account {account_id!r} not found")

    use_v2 = ld.evaluate(HEALTH_SCORE_V2_CALC, current_context())
    algorithm = "v2" if use_v2 else "v1"
    try:
        score = scoring.health_score_v2(account) if use_v2 else scoring.health_score_v1(account)
    except Exception:
        # Record the failure so /api/health (and the watchdog) can see it.
        log.exception("Health score %s failed for %s", algorithm, account_id)
        HEALTH_MONITOR.record(ok=False)
        return jsonify(error="Health score calculation failed", algorithm=algorithm), 500

    HEALTH_MONITOR.record(ok=True)
    return jsonify(
        accountId=account_id,
        algorithm=algorithm,
        healthScore=score,
        renewalLikelihood=scoring.renewal_likelihood(score),
        riskDrivers=account["riskDrivers"],
    )


@app.get("/api/health")
def service_health():
    """Error rate of health calculations over the last minute.

    This is the signal a monitoring tool would alert on. scripts/watchdog.py
    polls it and fires the LaunchDarkly trigger when it crosses a threshold.
    """
    stats = HEALTH_MONITOR.snapshot()
    return jsonify(status="degraded" if stats["errors"] else "ok", **stats)


@app.get("/api/server-flags")
def server_flags():
    """Values of server-only flags for the current persona.

    The demo panel polls this to show (and react to) flags the browser SDK
    can't see.
    """
    context = current_context()
    return jsonify({key: ld.evaluate(key, context) for key in SERVER_FLAGS})


@app.post("/api/assistant")
def account_assistant():
    """Summarize an account with the model and prompt the AI Config serves this user.

    Body: {"accountId": "..."}. The persona (X-Persona) decides the variation,
    e.g. execs get a short brief and CSMs a detailed review.
    """
    body = request.get_json(silent=True) or {}
    account = ACCOUNTS.get(body.get("accountId", ""))
    if account is None:
        abort(404, description="Account not found")
    try:
        return jsonify(assistant.summarize(account, current_context()))
    except assistant.AssistantError as e:
        return jsonify(error=str(e)), 503


@app.post("/api/assistant/feedback")
def account_assistant_feedback():
    """Record thumbs up/down for a summary. Body: {"token": "...", "positive": true}."""
    body = request.get_json(silent=True) or {}
    if not body.get("token") or not isinstance(body.get("positive"), bool):
        return jsonify(error="token and positive (true/false) are required"), 400
    try:
        assistant.record_feedback(body["token"], body["positive"], current_context())
    except assistant.AssistantError as e:
        return jsonify(error=str(e)), 400
    return jsonify(ok=True)


@app.get("/api/config")
def client_config():
    """Settings the browser needs to start the LaunchDarkly JavaScript SDK.

    The client-side ID is designed to be public (it only reads flags marked
    available to client-side SDKs). The server-side SDK key never leaves the server.
    """
    # LD SETUP: Set LD_CLIENT_SIDE_ID in .env (Project settings > Environments >
    # your environment > Client-side ID). If blank, the browser uses fallback values.
    return jsonify(
        clientSideId=os.environ.get("LD_CLIENT_SIDE_ID", "").strip(),
        personas=personas.all_personas(),
    )


@app.get("/api/status")
def ld_status():
    """Server SDK connection state, shown in the demo panel."""
    return jsonify(server=ld.status())


@app.errorhandler(404)
def not_found(error):
    """Return 404s as JSON so the frontend can show the message."""
    return jsonify(error=str(error.description)), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print(f"ABC Pulse running at http://localhost:{port}  (app: /app)")
    # debug=False keeps a single process. The LaunchDarkly SDK should be
    # initialized once per process, and the reloader would start a second one.
    app.run(host="127.0.0.1", port=port, debug=False)
