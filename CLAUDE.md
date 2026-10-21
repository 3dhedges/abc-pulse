# CLAUDE.md — ABC Pulse (LaunchDarkly SE take-home)

## What this project is
A sample app for LaunchDarkly's Solutions Engineering take-home exercise. It must read as a
polished demo delivered to a **prospective customer** ("ABC Company"). Quality of the README,
setup instructions, and code comments matters as much as the code itself.

Full spec and phased task list: `docs/PLAN.md`. Read it before starting any phase.

## The product
ABC Company sells **Pulse**, a customer-success platform for B2B SaaS companies.
- `/` — public marketing landing page (Part 2 targeting + Experimentation)
- `/app` — logged-in Pulse app for CSMs (Part 1 release/remediate + AI Configs)

## Stack (keep it lean)
- Python 3.11+, Flask (only web dependency)
- LaunchDarkly Python server SDK + Python AI SDK (server side)
- LaunchDarkly JavaScript client SDK v4 (`@launchdarkly/js-client-sdk`), self-hosted at
  `static/vendor/launchdarkly/js-client-sdk@<version>/index.js` (unmodified npm ESM build,
  imported by `static/js/ld.js`). v4 has no UMD/global build, so all page JS is ES modules.
- Plain HTML/CSS/vanilla JS. No React, no build step.
- Personas = LD contexts, defined once in `personas.py`, served to the browser via `/api/config`.
  The app sends `X-Persona` on API calls so server-side evaluations use the same context.
- Data: generated JSON via stdlib `random`. No database.
- Prefer the standard library. Ask before adding any new dependency.

## Conventions
- All secrets come from `.env` (never commit it). Keep `.env.example` current.
- Every place a user must supply a key or recreate a flag gets a comment starting with
  `# LD SETUP:` (Python) or `// LD SETUP:` (JS), saying exactly what to do.
- Flag keys are defined once as constants (Python: `flags.py`; JS: top of `static/js/ld.js`).
- Every flag evaluation passes a safe fallback value; the app must run if LaunchDarkly is unreachable.
  Evaluate only through the helpers (`ld.evaluate()` in Python, `variation()` from `ld.js`),
  which apply the `FALLBACKS` maps.
- The app must run without an LLM API key (mock assistant provider).
- All company/account names are fictional.
- Before editing SDK code, check current LaunchDarkly docs (https://launchdarkly.com/docs) —
  APIs and naming (e.g. AI Configs) change; do not rely on memory.

## Flag / config keys
| Key | Type | Surface | Purpose |
|---|---|---|---|
| `account-health-panel` | boolean | app | Part 1 feature; listener + trigger kill switch |
| `health-score-v2-calc` | boolean | app | Deliberately buggy new scoring algorithm (remediation demo) |
| `landing-hero` | string (control / roi-calculator / social-proof) | marketing | Part 2 targeting + experiment |
| `account-assistant` | AI Config | app | Prompt/model variations by role |
| `demo-request-clicked` | metric (custom conversion) | marketing | Experiment primary metric |

## Run
```
cp .env.example .env   # fill in keys
pip install -r requirements.txt
python scripts/seed_data.py
python app.py          # http://localhost:5000
```

## Working style
- Work one phase of `docs/PLAN.md` at a time; stop at the end of each phase so it can be reviewed and committed.
- Keep functions small and commented for a reviewer reading the code cold.
- Update the README as features land, not at the end.
