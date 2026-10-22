"""Simulate marketing-site visitors for the landing-hero experiment.

This demo site has no real traffic, so this script stands in for it. Each
simulated visitor goes through the real LaunchDarkly Python server SDK:

  1. A random anonymous visitor (LaunchDarkly "user" context) arrives.
  2. `landing-hero` is evaluated for that visitor, exactly like a real page
     view: targeting rules, then the experiment's 50/50 split, decide the variation.
  3. The visitor converts (or not) at the rates in RATES below, depending on
     the variation they were served and their device. Conversions are sent
     with track(), just like the browser's "Request a demo" click.

LaunchDarkly then attributes conversions to variations and computes the
results. THE TRAFFIC IS SIMULATED: the "truth" is the RATES table, and the
experiment's job is to discover it from the data.

Before running: create the metrics and the experiment, and START the
experiment iteration (README section 3.2). Events sent before the iteration
starts are not counted.

Usage (from the repo root, with LD_SDK_KEY in .env):
    python scripts/simulate_traffic.py                  # 20,000 visitors at ~150/s
    python scripts/simulate_traffic.py --visitors 30000 --rate 200
    python scripts/simulate_traffic.py --dry-run        # no LaunchDarkly; preview the math
"""

import argparse
import os
import random
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from flags import (  # noqa: E402
    FALLBACKS,
    LANDING_HERO,
    METRIC_DEMO_REQUEST_CLICKED,
    METRIC_PRICING_PAGE_VIEWED,
)

# ---------------------------------------------------------------------------
# The simulated "truth": the probability that a visitor converts, by metric,
# variation, and device. Tablets behave like desktop.
#
# Overall, the ROI calculator lifts demo requests by about a third, and
# pricing views are about the same (the new hero doesn't hurt them). Device
# differences make the traffic more realistic. LaunchDarkly can't slice
# results for anonymous contexts, so the per-device split shows only in this
# script's own summary.
# ---------------------------------------------------------------------------
RATES = {
    METRIC_DEMO_REQUEST_CLICKED: {
        "control":        {"desktop": 0.045, "mobile": 0.030},
        "roi-calculator": {"desktop": 0.065, "mobile": 0.031},
        "social-proof":   {"desktop": 0.050, "mobile": 0.036},
    },
    METRIC_PRICING_PAGE_VIEWED: {
        "control":        {"desktop": 0.150, "mobile": 0.120},
        "roi-calculator": {"desktop": 0.152, "mobile": 0.120},
        "social-proof":   {"desktop": 0.150, "mobile": 0.120},
    },
}

# Visitor attribute mix: (value, weight). Most visitors fall into the
# experiment audience (rule 5: US/GB/CA/AU). Some match earlier rules
# (DE/FR, regulated industries, LinkedIn, enterprise), like real traffic would.
ATTRIBUTES = {
    "country": [("US", 55), ("GB", 15), ("CA", 10), ("AU", 8), ("DE", 6), ("FR", 6)],
    "industry": [("SaaS", 40), ("Retail", 15), ("Logistics", 12), ("EdTech", 10),
                 ("Manufacturing", 13), ("Fintech", 5), ("Healthcare", 5)],
    "companySize": [(15, 20), (40, 25), (120, 25), (300, 20), (800, 6), (2500, 4)],
    "referrer": [("organic", 35), ("google-ads", 30), ("direct", 20), ("partner", 7), ("linkedin", 8)],
    "device": [("desktop", 55), ("mobile", 35), ("tablet", 10)],
}

FLUSH_EVERY = 500  # the SDK buffers up to 10,000 events; flush well before that


def pick(rng, weighted):
    """Pick a value from [(value, weight), ...]."""
    values, weights = zip(*weighted)
    return rng.choices(values, weights=weights, k=1)[0]


def new_visitor(rng):
    """A random anonymous visitor context, as a dict.

    Keys are always fresh UUIDs, even with --seed, so a re-run adds new
    visitors instead of repeating ones LaunchDarkly has already counted.
    """
    context = {"kind": "user", "key": str(uuid.uuid4()), "anonymous": True}
    for attr, weighted in ATTRIBUTES.items():
        context[attr] = pick(rng, weighted)
    return context


def device_group(context):
    """Tablets convert like desktop in RATES."""
    return "mobile" if context["device"] == "mobile" else "desktop"


class Stats:
    """Counts per variation and device, for the summary table."""

    def __init__(self):
        self.visitors = defaultdict(int)
        self.in_experiment = defaultdict(int)
        self.conversions = defaultdict(int)  # (metric, variation, device) -> count
        self.by_device = defaultdict(int)  # (variation, device) -> visitors

    def record(self, variation, device, in_experiment, converted_metrics):
        self.visitors[variation] += 1
        self.by_device[(variation, device)] += 1
        if in_experiment:
            self.in_experiment[variation] += 1
        for metric in converted_metrics:
            self.conversions[(metric, variation, device)] += 1

    def rate(self, metric, variation, device=None):
        devices = [device] if device else ["desktop", "mobile"]
        n = sum(self.by_device[(variation, d)] for d in devices)
        c = sum(self.conversions[(metric, variation, d)] for d in devices)
        return f"{c / n:6.2%}" if n else "     -"

    def print_summary(self):
        print("\nVariation         Visitors  In experiment   Demo req.  (desktop / mobile)   Pricing")
        for v in sorted(self.visitors, key=lambda k: -self.visitors[k]):
            print(f"{v:<16}{self.visitors[v]:>10}{self.in_experiment[v]:>15}   "
                  f"{self.rate(METRIC_DEMO_REQUEST_CLICKED, v)}  "
                  f"({self.rate(METRIC_DEMO_REQUEST_CLICKED, v, 'desktop')} / "
                  f"{self.rate(METRIC_DEMO_REQUEST_CLICKED, v, 'mobile')})  "
                  f"{self.rate(METRIC_PRICING_PAGE_VIEWED, v)}")
        print("\nThese are the simulator's own counts. LaunchDarkly's results count only "
              "visitors in the experiment, so its numbers will differ slightly.")


def start_client():
    """Start the LaunchDarkly server SDK with the key from .env."""
    from dotenv import load_dotenv
    import ldclient
    from ldclient.config import Config

    load_dotenv(REPO_ROOT / ".env")
    # LD SETUP: LD_SDK_KEY in .env must be the server-side SDK key for the
    # environment where the experiment is running.
    sdk_key = os.environ.get("LD_SDK_KEY", "").strip()
    if not sdk_key:
        sys.exit("LD_SDK_KEY is not set. Add it to .env, or use --dry-run.")

    ldclient.set_config(Config(sdk_key))
    client = ldclient.get()
    if not client.is_initialized():
        sys.exit("LaunchDarkly did not initialize. Check LD_SDK_KEY and your network.")
    return client


def main():
    parser = argparse.ArgumentParser(description="Simulate visitors for the landing-hero experiment.")
    parser.add_argument("--visitors", type=int, default=20000, help="Number of visitors (default: 20000)")
    parser.add_argument("--rate", type=float, default=150, help="Visitors per second (default: 150)")
    parser.add_argument("--seed", type=int, help="Random seed for attributes and conversions")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't contact LaunchDarkly: assign variations locally (50/50) and print the math")
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    rng = random.Random(args.seed)
    from ldclient import Context

    client = None if args.dry_run else start_client()
    stats = Stats()
    started = time.monotonic()
    print(f"Simulating {args.visitors:,} visitors"
          f"{' (dry run: no events sent)' if args.dry_run else f' at ~{args.rate:g}/s'}...")

    for i in range(1, args.visitors + 1):
        visitor = new_visitor(rng)
        context = Context.from_dict(visitor)
        device = device_group(visitor)

        if client:
            # Exactly what a real page view does: LaunchDarkly picks the variation.
            detail = client.variation_detail(LANDING_HERO, context, FALLBACKS[LANDING_HERO])
            variation = detail.value
            in_experiment = bool((detail.reason or {}).get("inExperiment"))
        else:
            variation = rng.choice(["control", "roi-calculator"])
            in_experiment = True

        converted = []
        for metric, by_variation in RATES.items():
            rate = by_variation.get(variation, by_variation["control"])[device]
            if rng.random() < rate:
                converted.append(metric)
                if client:
                    client.track(metric, context)
        stats.record(variation, device, in_experiment, converted)

        if client:
            if i % FLUSH_EVERY == 0:
                client.flush()
                print(f"  {i:>6,} visitors sent")
            # Pace the run so the event pipeline keeps up.
            behind = i / args.rate - (time.monotonic() - started)
            if behind > 0:
                time.sleep(behind)

    if client:
        client.close()  # flushes the remaining events

    stats.print_summary()
    if not args.dry_run and not sum(stats.in_experiment.values()):
        print("\nWARNING: no visitors landed in the experiment. Is the experiment iteration "
              "STARTED, is the flag on, and does rule 5 (US/GB/CA/AU) exist? See README 3.2.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped. Events sent so far still count.")
