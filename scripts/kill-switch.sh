#!/usr/bin/env bash
# Kill switch: fire the LaunchDarkly flag trigger that turns OFF health-score-v2-calc.
#
# This is the manual remediation path. An on-call engineer runs it the moment a
# bad release is spotted. No deploy, no dashboard login: one HTTP POST.
#
# Usage (from the repo root, in bash / Git Bash / WSL):
#   ./scripts/kill-switch.sh
#
# Windows PowerShell equivalent:
#   Invoke-RestMethod -Method Post -Uri $env:LD_TRIGGER_URL
#
# LD SETUP: Create a generic trigger on the health-score-v2-calc flag with the
# action "Turn the flag off", and put its URL in .env as LD_TRIGGER_URL.
# The URL works like a password: anyone who has it can flip the flag.

set -euo pipefail

# Read LD_TRIGGER_URL from .env unless it's already set in the environment.
ENV_FILE="$(dirname "$0")/../.env"
if [[ -z "${LD_TRIGGER_URL:-}" && -f "$ENV_FILE" ]]; then
  LD_TRIGGER_URL="$(grep -E '^LD_TRIGGER_URL=' "$ENV_FILE" | head -n1 | cut -d= -f2- | tr -d '\r"'"'"' ')"
fi

if [[ -z "${LD_TRIGGER_URL:-}" ]]; then
  echo "LD_TRIGGER_URL is not set. Add the flag trigger URL to .env (see README, section 3.2)." >&2
  exit 1
fi

echo "Firing LaunchDarkly trigger: turn off health-score-v2-calc..."
# The JSON body is optional. eventName shows up in the flag's change history.
status=$(curl -sS -o /dev/null -w '%{http_code}' -X POST "$LD_TRIGGER_URL" \
  -H 'Content-Type: application/json' \
  -d '{"eventName": "Manual kill switch (scripts/kill-switch.sh)"}')

if [[ "$status" =~ ^2 ]]; then
  echo "Done (HTTP $status). The flag is off; open apps switch back to v1 scoring within seconds."
else
  echo "Trigger call failed (HTTP $status). Check LD_TRIGGER_URL, and that the trigger is enabled." >&2
  exit 1
fi
