"""Account health scoring for Pulse.

Two algorithms:
  v1  the current, trusted algorithm. Also used by scripts/seed_data.py to
      precompute healthScore in data/accounts.json.
  v2  a "new and improved" algorithm being released behind the
      `health-score-v2-calc` flag. It contains a deliberate bug, so the demo
      can show a bad release being caught and turned off with a flag trigger.
"""


def clamp(value, low, high):
    """Limit value to the range [low, high]."""
    return max(low, min(high, value))


def _avg_adoption(account):
    """Average feature adoption across all features (0-100)."""
    values = account["featureAdoption"].values()
    return sum(values) / len(values)


def health_score_v1(account):
    """Current, trusted health-score algorithm (0-100).

    Weighted blend of five signals:
      30%  seat utilization
      25%  average feature adoption
      20%  NPS, mapped from -100..100 to 0..100
      15%  support load (0 open tickets = full marks, 10+ = none)
      10%  login momentum (last 7 days vs first 7 days of the 30-day trend)
    """
    nps = (account["nps"] + 100) / 2
    support = 100 - clamp(account["openTickets"], 0, 10) * 10

    trend = account["loginsTrend30d"]
    first, last = sum(trend[:7]) or 1, sum(trend[-7:])
    momentum = clamp(50 + (last / first - 1) * 100, 0, 100)

    score = (
        0.30 * account["seatUtilization"]
        + 0.25 * _avg_adoption(account)
        + 0.20 * nps
        + 0.15 * support
        + 0.10 * momentum
    )
    return round(clamp(score, 0, 100))


def health_score_v2(account):
    """New algorithm under test: v1 plus a "support efficiency" signal.

    Idea: an account that gets a lot of value (adoption) per support ticket is
    healthier than one that needs constant help. v2 blends v1 (85%) with
    adoption-per-ticket (15%).
    """
    # INTENTIONAL BUG (demo): divides by openTickets, which is 0 for some
    # accounts (ironically, the healthiest ones). Those raise
    # ZeroDivisionError, and the API returns HTTP 500.
    # The fix would be to treat zero tickets as full marks, e.g.
    #   adoption / max(1, account["openTickets"]).
    support_efficiency = clamp(_avg_adoption(account) / account["openTickets"] * 2, 0, 100)

    score = 0.85 * health_score_v1(account) + 0.15 * support_efficiency
    return round(clamp(score, 0, 100))


def renewal_likelihood(score):
    """Map a health score to a renewal-likelihood bucket."""
    if score >= 70:
        return "high"
    if score >= 45:
        return "medium"
    return "low"
