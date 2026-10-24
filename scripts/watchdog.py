"""Watchdog: automatic remediation with a LaunchDarkly flag trigger.

Polls the app's /api/health endpoint. When the health-score error rate
crosses a threshold, it fires the flag trigger that turns OFF
health-score-v2-calc, then exits.

This is the same pattern teams use with an APM tool: a Datadog or New Relic
alert calls a LaunchDarkly trigger URL from its webhook, so a bad release is
turned off within seconds of the error spike, before a human even looks.

Standard library only. Usage (with the app running):
    python scripts/watchdog.py              # watch and fire for real
    python scripts/watchdog.py --dry-run    # watch and report, don't fire

LD SETUP: Put the URL of the health-score-v2-calc "Turn the flag off" trigger
in .env as LD_TRIGGER_URL (see README, section 3.2).
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def read_env(name):
    """Read a setting from the environment, falling back to the repo's .env file."""
    if os.environ.get(name):
        return os.environ[name].strip()
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name:
                return value.strip().strip("'\"")
    return ""


def get_health(app_url):
    """Fetch /api/health from the app."""
    with urllib.request.urlopen(f"{app_url}/api/health", timeout=5) as res:
        return json.load(res)


def fire_trigger(trigger_url, app_url, stats):
    """POST the LaunchDarkly trigger URL. The body appears in the flag's change history."""
    body = json.dumps({
        "eventName": f"Watchdog: health-score error rate {stats['errorRate']:.0%} "
                     f"({stats['errors']}/{stats['requests']} in {stats['windowSeconds']}s)",
        "url": f"{app_url}/api/health",
    }).encode()
    req = urllib.request.Request(trigger_url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as res:
        return res.status


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--app-url", default=f"http://localhost:{read_env('PORT') or 5000}",
                        help="Base URL of the running app (default: http://localhost:$PORT)")
    parser.add_argument("--threshold", type=float, default=0.05,
                        help="Error rate that triggers remediation (default: 0.05 = 5%%)")
    parser.add_argument("--min-requests", type=int, default=20,
                        help="Ignore the error rate until the window has this many requests (default: 20)")
    parser.add_argument("--interval", type=float, default=5, help="Seconds between checks (default: 5)")
    parser.add_argument("--dry-run", action="store_true", help="Report a breach but don't fire the trigger")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # show each check immediately, even when piped

    trigger_url = read_env("LD_TRIGGER_URL")
    if not trigger_url and not args.dry_run:
        sys.exit("LD_TRIGGER_URL is not set. Add it to .env, or use --dry-run.")

    print(f"Watching {args.app_url}/api/health every {args.interval:g}s "
          f"(fire at >= {args.threshold:.0%} errors, min {args.min_requests} requests). Ctrl+C to stop.")

    while True:
        try:
            stats = get_health(args.app_url)
        except (urllib.error.URLError, OSError) as err:
            print(f"  app unreachable ({err}); retrying")
            time.sleep(args.interval)
            continue

        print(f"  {time.strftime('%H:%M:%S')}  error rate {stats['errorRate']:.1%} "
              f"({stats['errors']}/{stats['requests']} in last {stats['windowSeconds']}s)")

        breached = stats["requests"] >= args.min_requests and stats["errorRate"] >= args.threshold
        if breached:
            if args.dry_run:
                print("THRESHOLD BREACHED: would fire the trigger (dry run, not firing).")
                return
            try:
                status = fire_trigger(trigger_url, args.app_url, stats)
            except urllib.error.HTTPError as err:
                # e.g. 404 when the trigger URL was reset or the trigger deleted
                sys.exit(f"THRESHOLD BREACHED, but the trigger call failed (HTTP {err.code}). "
                         "Check LD_TRIGGER_URL and that the trigger is enabled.")
            except (urllib.error.URLError, OSError) as err:
                sys.exit(f"THRESHOLD BREACHED, but LaunchDarkly couldn't be reached ({err}).")
            print(f"THRESHOLD BREACHED: fired LaunchDarkly trigger (HTTP {status}). "
                  "health-score-v2-calc is now off. Exiting.")
            return

        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
