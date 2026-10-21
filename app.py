"""ABC Pulse: Flask server for the marketing site and the Pulse app.

Routes
    /                        marketing landing page (static/index.html)
    /app                     Pulse app for customer success managers (static/app.html)
    GET /api/accounts        all customer accounts
    GET /api/accounts/<id>   one account, or 404

Run:  python app.py   (then open http://localhost:5000)
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, send_from_directory

# Load .env before anything reads os.environ. If .env is missing, this does
# nothing; the app still runs with defaults.
load_dotenv()

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


@app.errorhandler(404)
def not_found(error):
    """Return 404s as JSON so the frontend can show the message."""
    return jsonify(error=str(error.description)), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print(f"ABC Pulse running at http://localhost:{port}  (app: /app)")
    # debug=False keeps a single process. The LaunchDarkly SDK (Phase 1) should
    # be initialized once per process, and the reloader would start a second one.
    app.run(host="127.0.0.1", port=port, debug=False)
