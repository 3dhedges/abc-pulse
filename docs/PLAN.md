# ABC Pulse — Build Plan

LaunchDarkly SE take-home. Target submission: Sat Oct 24, 2026.
Deliverable: public GitHub repo with detailed setup/run README, commented code, and a walkthrough video.

---

## 1. Concept

ABC Company sells **Pulse**, a customer-success platform for B2B SaaS companies. CS teams use it
to track account health, product adoption, and renewal risk.

| Surface | Route | Assignment parts |
|---|---|---|
| Marketing site (≈40k visitors/day in the story) | `/` | Part 2: Target · Extra credit: Experimentation |
| Pulse app (logged-in CSMs) | `/app` | Part 1: Release & Remediate · Extra credit: AI Configs |

Business story: ABC must ship faster without risking quality for enterprise customers.
LaunchDarkly lets them test in production, release gradually, roll back instantly, target
precisely, measure impact, and govern AI behavior at runtime.

---

## 2. Architecture

- **Backend:** Python + Flask. Serves static pages and a JSON API.
  - `GET /api/accounts`, `GET /api/accounts/<id>`
  - `GET /api/health` (error-rate signal for the watchdog)
  - `POST /api/assistant` (AI Config–driven account summary)
- **Frontend:** plain HTML/CSS/JS + LaunchDarkly JavaScript client SDK (streaming, change listeners).
- **Server SDKs:** LaunchDarkly Python server SDK, Python AI SDK.
- **Data:** `scripts/seed_data.py` (stdlib only) → `data/accounts.json`.

### Repo layout
```
abc-pulse/
├── README.md
├── CLAUDE.md
├── docs/PLAN.md
├── .env.example        # LD_SDK_KEY, LD_CLIENT_SIDE_ID, LD_API_TOKEN, LD_PROJECT_KEY,
│                       # LD_ENVIRONMENT_KEY, LD_TRIGGER_URL, LLM_API_KEY (optional)
├── .gitignore
├── requirements.txt
├── docker-compose.yml  # optional
├── app.py
├── flags.py
├── assistant.py        # AI Config + LLM/mock provider
├── static/
│   ├── index.html      # marketing site
│   ├── app.html        # Pulse app
│   ├── js/ld.js        # shared SDK init, persona switcher, flag key constants
│   ├── js/marketing.js
│   ├── js/app.js
│   └── css/styles.css
├── data/accounts.json
├── scripts/
│   ├── seed_data.py
│   ├── setup_launchdarkly.py   # creates flags, variations, metric via REST API
│   ├── kill-switch.sh
│   ├── watchdog.py
│   └── simulate_traffic.py
└── .github/workflows/code-refs.yml
```

---

## 3. Data model (fictional accounts, ~50)

- Identity: `id`, `name`, `industry`, `plan` (Starter/Growth/Enterprise), `seats`, `arr`,
  `renewalDate`, `csmOwner`
- Usage: `weeklyActiveUsers`, `seatUtilization` (%), `featureAdoption` {feature: %},
  `loginsTrend30d` (list of ints)
- Success: `nps`, `openTickets`, `timeToValueDays`, `qbrCompleted`
- Derived: `healthScore` (0–100, simple weighted formula), `renewalLikelihood` (low/med/high),
  `riskDrivers` (list of strings)

---

## 4. Contexts

| Surface | Kind(s) | Attributes |
|---|---|---|
| Marketing | `user` (anonymous) | `key` (UUID), `anonymous: true`, `industry`, `companySize`, `country`, `referrer`, `device` |
| App | multi-context `user` + `organization` | user: `key`, `name`, `email`, `role` (CSM / CS Manager / Exec), `region`, `betaTester` · org: `key`, `name`, `plan`, `seats` |

Both surfaces get a **persona switcher** dropdown that calls `identify()` so targeting changes are visible live.

Marketing personas (examples): Enterprise SaaS visitor (US, 2,000 employees), Mid-market fintech
(US, 300), German startup (DE, 40), QA tester (`qa-tester-01`), Sales demo (`sales-demo`), Random visitor.

App personas (examples): Dana (CSM, beta tester, @abc.com), Marco (CS Manager), Priya (Exec),
External customer user (no beta).

---

## 5. Part 1 — Release & Remediate (`/app`)

**Flag `account-health-panel` (boolean)**
- Off: plain usage-stats table (old code).
- On: new Account Health panel (score gauge, renewal badge, adoption bars, risk drivers).
- Test in prod: target `betaTester = true` and `email endsWith @abc.com` first, then release to all.

**Listener:** `ldClient.on('change:account-health-panel', ...)` re-renders without reload.

**Remediation**
- Flag `health-score-v2-calc` (boolean) switches to a deliberately buggy scoring algorithm
  (some accounts → NaN score / API 500s).
- Create a **flag trigger** (generic, "turn off") on `account-health-panel` in the dashboard.
- `scripts/kill-switch.sh` → `curl -X POST "$LD_TRIGGER_URL"`.
- Bonus: `scripts/watchdog.py` polls `/api/health`; above an error-rate threshold it calls the
  trigger automatically ("same pattern as Datadog/New Relic triggers").

**Done when:** toggle on/off swaps UI live; buggy v2 visibly breaks; curl or watchdog kills the panel live.

---

## 6. Part 2 — Target (`/`)

**Flag `landing-hero` (string):** `control` · `roi-calculator` · `social-proof` (optional)

**Individual targeting:** `qa-tester-01`, `sales-demo` → `roi-calculator`

**Rules (document the business reason for each in README):**
1. `companySize >= 500` → `roi-calculator` (enterprise buyers care about ROI)
2. `industry in [Fintech, Healthcare]` → `control` (compliance review of copy pending)
3. `country in [DE, FR]` → `control` (localization not ready)
4. Default rule: percentage rollout (e.g. 10% `roi-calculator`) — limit blast radius at 40k/day

**Done when:** switching personas changes the hero live and each rule/target is demonstrable.

---

## 7. Extra credit — Experimentation (`/`)

- Hypothesis: ROI-calculator hero increases demo requests.
- Metric: `demo-request-clicked` (custom conversion, `track()` on CTA). Secondary: `pricing-page-viewed`.
- Experiment on `landing-hero` default rule: 50/50 `control` vs `roi-calculator`.
- `scripts/simulate_traffic.py` (Python server SDK): N anonymous visitors with random attributes,
  evaluate flag, fire conversions at configurable per-variation rates (e.g. 4.0% vs 5.2%). Flush on exit.
- Note in README: individually targeted contexts are not in the experiment; traffic is **simulated**.
- Deliverable: results screenshots + short decision memo in README.

**Run while the trial is active.** Trial converts to the free Developer plan when it ends.

---

## 8. Extra credit — AI Configs (`/app`)

- AI Config `account-assistant`; "Summarize this account" button → `POST /api/assistant`.
- Variations:
  - `exec-brief` — smaller/faster model, 3 bullets on renewal risk
  - `csm-deep-dive` — larger model, detailed summary + recommended next actions
- Targeting: `role = Exec` → `exec-brief`; `role = CSM` → `csm-deep-dive`.
- Track tokens, latency, success/error via AI SDK tracker; thumbs up/down feedback.
- Optional experiment: prompt variants vs thumbs-up rate.
- Mock provider when `LLM_API_KEY` is absent (canned summaries).
- Verify current naming/API in docs (AI Configs may appear as "AgentControl").

---

## 9. Extra credit — Integrations

- `ld-find-code-refs` GitHub Action on push (`.github/workflows/code-refs.yml`).
- Optional: Slack notifications for flag changes.

---

## 10. Phases (stop and commit after each)

- [x] **Phase 0 — Scaffold:** repo layout, `.gitignore`, `.env.example`, `requirements.txt`,
      Flask app serving both pages, `seed_data.py`, README skeleton.
- [x] **Phase 1 — LD wiring:** SDK init (server + client), flag constants, fallbacks, persona switchers.
- [ ] **Phase 2 — Part 1:** health panel, listener, buggy v2 calc, `/api/health`, kill-switch, watchdog.
- [ ] **Phase 3 — Part 2:** marketing site, hero variants, contexts, document targeting setup.
- [ ] **Phase 4 — Experiment:** `track()` events, metric, `simulate_traffic.py`, run it, capture results.
- [ ] **Phase 5 — AI Config:** assistant endpoint, variations, tracking, mock provider.
- [ ] **Phase 6 — Setup automation & integrations:** `setup_launchdarkly.py`, code-refs Action.
- [ ] **Phase 7 — Polish:** full README, screenshots, fresh-clone test on a clean machine, video.

---

## 11. README outline

1. What this demonstrates (business framing per part)
2. Prerequisites & assumptions (OS, Python version, Docker optional, LD trial, optional LLM key)
3. LaunchDarkly setup — automated (`setup_launchdarkly.py`) and manual (exact keys, variations, rules, trigger, metric, experiment, AI Config), with screenshots
4. Run instructions
5. Demo script per part ("do X, watch Y")
6. Troubleshooting
7. Design decisions & what I'd do in production (guarded rollouts, observability, governance)

## 12. Video outline (8–10 min)

1. Business framing (30s)
2. Part 1: beta → release → rollback → buggy v2 → trigger/watchdog kill
3. Part 2: personas → individual targets → rules → percentage rollout
4. Experiment: setup → results → decision
5. AI Configs: Exec vs CSM → live prompt edit
6. Next steps with a real customer
