"""Generate fictional customer accounts for the Pulse demo app.

Writes data/accounts.json. Uses only the standard library and a fixed random
seed, so every run produces the same file and screenshots stay reproducible.

Usage (from anywhere):
    python scripts/seed_data.py

All company and person names are invented. Any resemblance to a real company
is coincidental.
"""

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Use the app's scoring module, so the seeded healthScore always matches what
# the server calculates with the v1 algorithm.
sys.path.insert(0, str(REPO_ROOT))
from scoring import clamp, health_score_v1, renewal_likelihood  # noqa: E402

SEED = 42
ACCOUNT_COUNT = 50

# Renewal dates are offsets from this fixed date, not today, so the output
# doesn't change from day to day.
BASE_DATE = date(2026, 10, 24)

OUTPUT_PATH = REPO_ROOT / "data" / "accounts.json"

NAME_PREFIXES = [
    "Northwind", "Bluefin", "Cobalt", "Harborline", "Juniper", "Lumenfield",
    "Meridian", "Quarrystone", "Redwood", "Sablecrest", "Tidewater", "Vantagely",
    "Willowmere", "Granitepeak", "Copperleaf", "Brightline", "Foxglove",
    "Kestrel", "Larkspur", "Oakhollow", "Pinecrest", "Silverbirch", "Driftwood",
    "Emberly", "Halcyon", "Ironbark", "Marigold", "Nimbusly", "Orchardly",
    "Starling",
]

# Each name suffix implies an industry, so names and industries stay consistent.
SUFFIX_INDUSTRY = {
    "Analytics": "SaaS",
    "Cloud": "SaaS",
    "Payments": "Fintech",
    "Capital": "Fintech",
    "Health": "Healthcare",
    "Clinics": "Healthcare",
    "Logistics": "Logistics",
    "Learning": "EdTech",
    "Robotics": "Manufacturing",
    "Retail": "Retail",
}

# Plan tiers: (weight, seat range, list price per seat per year in USD)
PLANS = {
    "Starter": (0.35, (10, 60), 300),
    "Growth": (0.40, (60, 400), 420),
    "Enterprise": (0.25, (400, 3000), 540),
}

CSM_OWNERS = ["Dana Whitfield", "Luis Ortega", "Mei Tanaka", "Sam Okafor"]

FEATURES = [
    "Health Scores",
    "Playbooks",
    "Renewal Forecasting",
    "Integrations",
    "Executive Dashboards",
]




def make_names(rng, count):
    """Return `count` unique company names with their industries."""
    combos = [(p, s) for p in NAME_PREFIXES for s in SUFFIX_INDUSTRY]
    rng.shuffle(combos)
    return [(f"{p} {s}", SUFFIX_INDUSTRY[s]) for p, s in combos[:count]]


def pick_plan(rng):
    """Pick a plan tier by its weight."""
    names = list(PLANS)
    weights = [PLANS[n][0] for n in names]
    return rng.choices(names, weights=weights, k=1)[0]


def logins_trend(rng, base, vitality):
    """Build 30 days of login counts.

    Healthy accounts (high vitality) trend flat or up; struggling accounts
    trend down. Small daily noise keeps the sparkline believable.
    """
    slope = (vitality - 0.5) * 0.02  # roughly -1%..+1% of base per day
    trend = []
    for day in range(30):
        expected = base * (1 + slope * (day - 15))
        trend.append(max(0, round(expected * rng.uniform(0.85, 1.15))))
    return trend






def risk_drivers(account):
    """List readable reasons an account may be at risk."""
    drivers = []
    if account["seatUtilization"] < 50:
        drivers.append(f"Low seat utilization ({account['seatUtilization']}%)")
    trend = account["loginsTrend30d"]
    if sum(trend[-7:]) < 0.85 * sum(trend[:7]):
        drivers.append("Logins declining over the last 30 days")
    if account["nps"] < 0:
        drivers.append(f"Negative NPS ({account['nps']})")
    if account["openTickets"] >= 6:
        drivers.append(f"High support load ({account['openTickets']} open tickets)")
    if not account["qbrCompleted"]:
        drivers.append("No QBR completed this quarter")
    low = [f for f, pct in account["featureAdoption"].items() if pct < 25]
    if low:
        drivers.append("Low adoption: " + ", ".join(low))
    days_to_renewal = (date.fromisoformat(account["renewalDate"]) - BASE_DATE).days
    if days_to_renewal <= 60 and drivers:
        drivers.insert(0, f"Renewal in {days_to_renewal} days")
    return drivers


def make_account(rng, index, name, industry):
    """Generate one account with coherent usage, success, and derived fields."""
    plan = pick_plan(rng)
    _, (seat_lo, seat_hi), price = PLANS[plan]
    seats = rng.randint(seat_lo, seat_hi)

    # A single hidden "vitality" factor drives every signal, so the metrics
    # agree with each other (a healthy account is healthy across the board).
    vitality = rng.betavariate(2.2, 1.6)

    seat_util = round(clamp(vitality * 100 + rng.gauss(0, 10), 8, 100))
    adoption = {
        f: round(clamp(vitality * 90 + rng.gauss(0, 18), 0, 100)) for f in FEATURES
    }
    wau = max(1, round(seats * seat_util / 100 * rng.uniform(0.7, 0.95)))

    account = {
        "id": f"acct-{index:03d}",
        "name": name,
        "industry": industry,
        "plan": plan,
        "seats": seats,
        "arr": int(round(seats * price * rng.uniform(0.8, 1.0), -2)),  # list price minus discount
        "renewalDate": (BASE_DATE + timedelta(days=rng.randint(10, 365))).isoformat(),
        "csmOwner": rng.choice(CSM_OWNERS),
        "weeklyActiveUsers": wau,
        "seatUtilization": seat_util,
        "featureAdoption": adoption,
        "loginsTrend30d": logins_trend(rng, max(1, wau / 5), vitality),
        "nps": round(clamp(vitality * 140 - 60 + rng.gauss(0, 15), -100, 100)),
        "openTickets": max(0, round((1 - vitality) * 10 + rng.gauss(0, 1.5))),
        "timeToValueDays": round(clamp((1 - vitality) * 90 + rng.gauss(14, 8), 5, 120)),
        "qbrCompleted": rng.random() < 0.3 + 0.6 * vitality,
    }

    account["healthScore"] = health_score_v1(account)
    account["renewalLikelihood"] = renewal_likelihood(account["healthScore"])
    account["riskDrivers"] = risk_drivers(account)
    return account


def main():
    """Generate all accounts and write them to data/accounts.json."""
    rng = random.Random(SEED)
    names = make_names(rng, ACCOUNT_COUNT)
    accounts = [
        make_account(rng, i + 1, name, industry)
        for i, (name, industry) in enumerate(names)
    ]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" keeps the file byte-identical on Windows, macOS, and Linux.
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(accounts, f, indent=2)
        f.write("\n")

    print(f"Wrote {len(accounts)} accounts to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
