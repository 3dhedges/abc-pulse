"""Demo personas: the LaunchDarkly contexts the demo panel switches between.

Defined once, here. The browser gets them from /api/config and passes the
context to identify(). The server builds the same context with context_for()
when it evaluates flags for an API request. Both sides always agree on who
the current user is.

In a real product these contexts would come from the session (logged-in
user) or from request data (geo-IP, referrer, device). The personas simulate
that, so targeting can be shown live without real visitors.

All people and companies are fictional. Emails use the reserved .example domain.
"""

from ldclient import Context

# ---------------------------------------------------------------------------
# Marketing site (/): one "user" context per visitor.
#
# Anonymous visitors get anonymous contexts. LaunchDarkly can still target and
# roll out to them, but doesn't list them on the Contexts page. The QA tester
# and sales demo are known internal people, so they're regular contexts that
# can be picked by key for individual targeting.
#
# Attributes used by targeting rules: industry, companySize, country.
# referrer and device are extra attributes for segmenting results.
# ---------------------------------------------------------------------------
MARKETING_PERSONAS = [
    {
        "id": "enterprise-saas",
        "label": "Enterprise SaaS visitor",
        "description": "US · SaaS · 2,000 employees",
        "context": {
            "kind": "user",
            "key": "visitor-enterprise-saas",
            "anonymous": True,
            "industry": "SaaS",
            "companySize": 2000,
            "country": "US",
            "referrer": "google-ads",
            "device": "desktop",
        },
    },
    {
        "id": "midmarket-fintech",
        "label": "Mid-market fintech visitor",
        "description": "US · Fintech · 300 employees",
        "context": {
            "kind": "user",
            "key": "visitor-midmarket-fintech",
            "anonymous": True,
            "industry": "Fintech",
            "companySize": 300,
            "country": "US",
            "referrer": "linkedin",
            "device": "desktop",
        },
    },
    {
        "id": "german-startup",
        "label": "German startup visitor",
        "description": "DE · SaaS · 40 employees",
        "context": {
            "kind": "user",
            "key": "visitor-german-startup",
            "anonymous": True,
            "industry": "SaaS",
            "companySize": 40,
            "country": "DE",
            "referrer": "organic",
            "device": "mobile",
        },
    },
    {
        # Its attributes would match the "localization not ready" rule (DE).
        # Individual targeting takes priority over rules, so it shows how a
        # tester can preview the new hero anyway.
        "id": "qa-tester",
        "label": "QA tester (qa-tester-01)",
        "description": "Internal QA · individually targeted",
        "context": {
            "kind": "user",
            "key": "qa-tester-01",
            "name": "QA Tester",
            "industry": "SaaS",
            "companySize": 40,
            "country": "DE",
            "referrer": "direct",
            "device": "desktop",
        },
    },
    {
        "id": "sales-demo",
        "label": "Sales demo (sales-demo)",
        "description": "Sales engineer demo account · individually targeted",
        "context": {
            "kind": "user",
            "key": "sales-demo",
            "name": "Sales Demo",
            "industry": "Fintech",
            "companySize": 300,
            "country": "US",
            "referrer": "direct",
            "device": "desktop",
        },
    },
    {
        # The browser builds this context itself: a random anonymous key kept
        # in localStorage (so the visitor stays in the same rollout bucket)
        # plus random attributes. See static/js/demo-panel.js.
        "id": "random",
        "label": "Random visitor",
        "description": "Anonymous · random attributes · falls through to the rollout",
        "context": None,
    },
]

# ---------------------------------------------------------------------------
# Pulse app (/app): a multi-context of "user" + "organization".
#
# The organization is the Pulse customer (tenant) the user belongs to. Using
# both kinds lets a release target people (betaTester, role, email) or whole
# companies (plan, seats), and percentage rollouts can bucket by organization
# so everyone at a company sees the same thing.
#
# email is a private attribute: rules can still target it, but the SDK never
# sends its value to LaunchDarkly in analytics events.
# ---------------------------------------------------------------------------
ABC_INTERNAL_ORG = {
    "key": "org-abc-company",
    "name": "ABC Company",
    "plan": "Enterprise",
    "seats": 250,
}


def _app_context(user, org):
    """Build a user + organization multi-context dict."""
    return {
        "kind": "multi",
        "user": {**user, "_meta": {"privateAttributes": ["email"]}},
        "organization": org,
    }


APP_PERSONAS = [
    {
        "id": "dana",
        "label": "Dana Whitfield",
        "description": "CSM · beta tester · ABC Company (internal)",
        "context": _app_context(
            {"key": "user-dana-whitfield", "name": "Dana Whitfield",
             "email": "dana.whitfield@abc.example", "role": "CSM",
             "region": "NA", "betaTester": True},
            ABC_INTERNAL_ORG,
        ),
    },
    {
        "id": "marco",
        "label": "Marco Rossi",
        "description": "CS Manager · ABC Company (internal)",
        "context": _app_context(
            {"key": "user-marco-rossi", "name": "Marco Rossi",
             "email": "marco.rossi@abc.example", "role": "CS Manager",
             "region": "EMEA", "betaTester": False},
            ABC_INTERNAL_ORG,
        ),
    },
    {
        "id": "priya",
        "label": "Priya Raman",
        "description": "Exec · ABC Company (internal)",
        "context": _app_context(
            {"key": "user-priya-raman", "name": "Priya Raman",
             "email": "priya.raman@abc.example", "role": "Exec",
             "region": "NA", "betaTester": False},
            ABC_INTERNAL_ORG,
        ),
    },
    {
        "id": "alex",
        "label": "Alex Morgan",
        "description": "CSM · customer at Northwind Analytics",
        "context": _app_context(
            {"key": "user-alex-morgan", "name": "Alex Morgan",
             "email": "alex.morgan@northwind.example", "role": "CSM",
             "region": "NA", "betaTester": False},
            {"key": "org-northwind-analytics", "name": "Northwind Analytics",
             "plan": "Growth", "seats": 120},
        ),
    },
]

DEFAULT_APP_PERSONA = "dana"
_APP_PERSONAS_BY_ID = {p["id"]: p for p in APP_PERSONAS}


def all_personas():
    """Personas for both surfaces, as sent to the browser."""
    return {"marketing": MARKETING_PERSONAS, "app": APP_PERSONAS}


def context_for(persona_id):
    """Return the LaunchDarkly Context for an app persona (default: Dana)."""
    persona = _APP_PERSONAS_BY_ID.get(persona_id) or _APP_PERSONAS_BY_ID[DEFAULT_APP_PERSONA]
    return Context.from_dict(persona["context"])
