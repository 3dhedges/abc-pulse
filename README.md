# ABC Pulse: a LaunchDarkly sample app

ABC Company sells **Pulse**, a customer-success platform for B2B SaaS companies. Customer
success managers (CSMs) use it to track account health, product adoption, and renewal risk.

ABC's competitors are catching up, and leadership wants features shipped faster. ABC's
enterprise customers expect high quality, so shipping faster can't mean shipping riskier.
This sample app shows how LaunchDarkly helps ABC meet both goals. Teams can **test in
production, release gradually, roll back instantly, target precisely, measure impact, and
manage AI behavior at runtime**, all without redeploying.

> **Status:** work in progress. Sections marked _Coming in Phase N_ are being built.

---

## 1. What this demonstrates

| Surface | URL | Scenario |
|---|---|---|
| Marketing site (about 40k visitors/day in the story) | `http://localhost:5000/` | **Target**: individual and rule-based targeting of a new landing-page hero · **Experimentation**: does the new hero increase demo requests? |
| Pulse app (signed-in CSMs) | `http://localhost:5000/app` | **Release & Remediate**: a new Account Health panel behind a flag, live toggling, and a trigger-based kill switch · **AI Configs**: an account-summary assistant whose model and prompt change by role |

_Detailed business framing for each part: Coming in Phase 7._

---

## 2. Prerequisites & assumptions

- **OS:** Windows 10/11, macOS, or Linux. Commands are given for PowerShell (Windows) and bash/zsh (macOS/Linux).
- **Python 3.11 or newer** on your `PATH`. Check with `python --version` (on some macOS/Linux systems, `python3 --version`).
- **git**, to clone the repo.
- A modern browser (Chrome, Edge, Firefox, or Safari).
- **A LaunchDarkly account.** A [free trial](https://launchdarkly.com/start-trial/) works. You don't need it for the first run below. It's required from the LaunchDarkly setup step onward.
- _Optional:_ an LLM API key for the AI assistant. Without one, the app uses a built-in mock.
- Port **5000** must be free (see [Troubleshooting](#6-troubleshooting)).

---

## 3. LaunchDarkly setup

The app runs without LaunchDarkly: every flag then serves its **fallback value** (the
existing, safe experience). Connect it to see flags, targeting, and live updates.

### 3.1 Connect the SDKs

1. Sign in to LaunchDarkly (a [trial account](https://launchdarkly.com/start-trial/) works).
2. Create a project, e.g. **ABC Pulse** (key `abc-pulse`). It comes with **Test** and
   **Production** environments. Use **Test** for this demo.
3. Open **Project settings → Environments → Test**, then copy two values into your `.env`
   (see step 4.3):

   | `.env` variable | LaunchDarkly value | Used by | Secret? |
   |---|---|---|---|
   | `LD_SDK_KEY` | **SDK key** (starts with `sdk-`) | Python server SDK ([ld.py](ld.py)) | **Yes**: never put it in browser code |
   | `LD_CLIENT_SIDE_ID` | **Client-side ID** | JavaScript SDK in the browser ([static/js/ld.js](static/js/ld.js)) | No: designed to be public |

4. Restart `python app.py`. The **Demo controls** panel (bottom-right) should show both
   SDKs as **Connected**.

### 3.2 Flags

Create these flags in your project (**Flags → Create flag**) with **exactly** these keys.
Automated setup with `scripts/setup_launchdarkly.py` is coming in Phase 6.

> **Client-side availability matters.** Anything the browser can read, anyone with your
> (public) client-side ID can read. So expose a flag to client-side SDKs only if the browser
> needs it, and never check **SDKs using Mobile key** here: there's no mobile app.

#### `account-health-panel`: the new Account Health experience (Part 1)

| Setting | Value |
|---|---|
| Name / key | Account health panel / `account-health-panel` |
| Type | Boolean: `true` (new panel), `false` (legacy usage stats) |
| Temporary or permanent | **Temporary.** It's a release flag; remove it once fully rolled out |
| Client-side availability | ✅ **SDKs using Client-side ID** (the browser renders it and listens for changes) |
| Variation served when off | `false` |
| Targeting rule 1 | **If** context kind `user`, attribute `betaTester` **is one of** `true` (boolean) → serve `true` |
| Default rule | `false` to start. Change it to `true` to release to everyone |

If `betaTester` isn't in the attribute dropdown yet, type it in. LaunchDarkly lists attributes
only after it has received contexts that use them.

#### `health-score-v2-calc`: the new (buggy) scoring algorithm (Part 1 remediation)

| Setting | Value |
|---|---|
| Name / key | Health score v2 calculation / `health-score-v2-calc` |
| Type | Boolean: `true` (v2 algorithm), `false` (v1) |
| Temporary or permanent | **Temporary** |
| Client-side availability | ☐ **Leave unchecked.** Evaluated only on the server ([app.py](app.py)) |
| Variation served when off | `false` |
| Targeting rule 1 | Same beta-tester rule as above → serve `true` |
| Default rule | `false` |

The demo panel still shows this flag's value. The browser reads it from `/api/server-flags`
(tagged `server`), polled every 3 seconds. In production you'd push it instead (SSE or
WebSocket). The client-side flag above uses the SDK's real streaming listener.

#### Flag trigger: the remediation kill switch

1. Open `health-score-v2-calc` and go to its **Triggers** settings, in the **Test** environment.
2. Add a trigger. Choose **Generic trigger** as the tool and **Turn the flag off** as the action.
3. Copy the generated URL into `.env` as `LD_TRIGGER_URL`. **LaunchDarkly shows it only once.**
   If you lose it, reset the URL from the trigger's menu. Treat it like a password: anyone with
   the URL can flip the flag.

> Flag triggers are only available on some LaunchDarkly plans; trials normally include them.
> Without triggers, you can still demo the same failure and recovery by turning the flag off
> in the dashboard. `watchdog.py --dry-run` still detects the error spike.

#### `landing-hero`: the marketing-site hero (Part 2)

| Setting | Value |
|---|---|
| Name / key | Landing hero / `landing-hero` |
| Type | **String**, with three variations whose **values** are exactly `control`, `roi-calculator`, `social-proof`. The names can be anything. LaunchDarkly pre-fills new string variations with placeholder values like "Variation 1"; replace them, or the page won't recognize the value and will show `control` |
| Temporary or permanent | **Temporary.** Roll out the winning variant, then remove the flag |
| Client-side availability | ✅ **SDKs using Client-side ID** (the browser renders the hero) |
| Variation served when off | `control` |

**Individual targeting:** serve `roi-calculator` to the `user` contexts `qa-tester-01` and
`sales-demo`. Individual targets are checked **before** any rule. That lets QA and Sales preview
the new hero even when their attributes would otherwise hold them on `control`.

**Rules: add them in this order.** LaunchDarkly serves the **first** rule that matches, so
restrictions come first. An opportunity rule (like rule 4) can then never override a compliance or
localization hold.

| # | If (context kind `user`) | Serve | Business reason |
|---|---|---|---|
| 1 | `country` **is one of** `DE`, `FR` | `control` | Localization isn't ready, so non-English markets keep the current page |
| 2 | `industry` **is one of** `Fintech`, `Healthcare` | `control` | The new copy makes ROI claims that compliance hasn't approved for regulated industries |
| 3 | `referrer` **is one of** `linkedin` | `social-proof` | Visitors from social channels respond best to peer validation |
| 4 | `companySize` **≥** `500` (number) | `roi-calculator` | Enterprise buyers need a business case for budget approval |
| Default | **Percentage rollout:** `roi-calculator` 10%, `control` 90% | | About 40,000 visitors a day: limit the blast radius while the new hero proves itself |

All attribute values are case-sensitive. Use `≥` ("greater than or equal") with the number
`500`, not text. The default rule's percentage rollout buckets by context key, so each visitor
always lands in the same bucket.

### 3.3 How the app talks to LaunchDarkly

- **Browser:** [static/js/ld.js](static/js/ld.js) starts the JavaScript SDK
  (`@launchdarkly/js-client-sdk` v4) with a **streaming** connection and a **change listener**.
  When a flag changes in LaunchDarkly, the page updates instantly, with no reload.
  The SDK is **self-hosted** under `static/vendor/`, copied unmodified from the npm package, as
  LaunchDarkly recommends for production instead of a public CDN.
- **Server:** [ld.py](ld.py) starts the Python server SDK once per process. All server-side
  evaluations go through `ld.evaluate()`, which applies the fallbacks from [flags.py](flags.py).
- **Contexts:** the "who" that flags are evaluated for. They're defined once in
  [personas.py](personas.py) and used by both the browser and the server:
  - **Marketing site:** a `user` context per visitor, with `industry`, `companySize`,
    `country`, `referrer`, and `device`. Anonymous visitors are marked `anonymous`.
  - **Pulse app:** a **multi-context** of `user` (`role`, `region`, `betaTester`, `email`)
    plus `organization` (the customer company: `plan`, `seats`). `email` is a **private
    attribute**: it can still be used in targeting rules, but its value is never sent to
    LaunchDarkly in analytics events.

### 3.4 The Demo controls panel

Both pages have a dark **Demo controls** card in the bottom-right corner. It is **not part of
the product**. It stands in for real visitors and logged-in users:

- **Persona:** switches the LaunchDarkly context with `identify()`, so targeting changes appear
  live. Choose **Random visitor**, then **↻ New random visitor**, to see percentage rollouts
  bucket different visitors.
- **Connection:** status of the browser and server SDKs. Hover over a status for details.
- **Flags (live):** the current value of each flag on this page, plus the **reason**
  LaunchDarkly gave for it (e.g. *Individual target*, *Rule 2*, *Default rule*, *Flag off*).
  A value flashes when it changes. Server-only flags are tagged `server`.

Click the panel's title to collapse it.

---

## 4. Run the app

### 4.1 Clone and create a virtual environment

**Windows (PowerShell)**
```powershell
git clone https://github.com/3dhedges/abc-pulse.git
cd abc-pulse
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
> If PowerShell blocks the activation script, run
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try again.

**macOS / Linux**
```bash
git clone https://github.com/3dhedges/abc-pulse.git
cd abc-pulse
python3 -m venv .venv
source .venv/bin/activate
```

### 4.2 Install dependencies
```bash
pip install -r requirements.txt
```

### 4.3 Create your `.env`
**Windows:** `Copy-Item .env.example .env`  ·  **macOS/Linux:** `cp .env.example .env`

You can leave every value blank for now. The app runs without LaunchDarkly keys and shows
its default (flag-off) experience.

### 4.4 (Optional) Regenerate the sample data
`data/accounts.json` ships with the repo. To regenerate it:
```bash
python scripts/seed_data.py
```
The script uses a fixed random seed, so it always produces the same 50 fictional accounts.

### 4.5 Start the server
```bash
python app.py
```
Open:
- **http://localhost:5000/**: marketing site
- **http://localhost:5000/app**: Pulse app

Stop the server with `Ctrl+C`.

---

## 5. Demo script

Each part is a "do X, watch Y" walkthrough. Keep the LaunchDarkly dashboard and the app side by
side, with the **Demo controls** panel open.

### 5.1 Release & Remediate (Part 1): `/app`

**Scenario:** ABC wants to ship a new Account Health experience faster without risking quality.
The plan: test it in production with internal beta testers, release it to everyone, and
make sure any bad change can be turned off in seconds.

**Before you start:** both flags exist with the beta-tester rule and default `false`, both flags
are **on**, and the trigger URL is in `.env` (section 3.2).

| # | Do | Watch |
|---|---|---|
| 1 | Pick **Marco Rossi** (no beta) in the demo panel | Legacy **usage-stats table**: the existing experience |
| 2 | Switch to **Dana Whitfield** (beta tester) | Instantly: a **Health** column and the new **Account health** panel. **Testing in production:** only beta testers see it |
| 3 | In LaunchDarkly, set `account-health-panel`'s default rule to `true` and save. Switch to Marco | Marco now has the new panel too, with no reload. **Released** to everyone |
| 4 | Toggle `account-health-panel` **off** | Every open session snaps back to the legacy table within a second. **Instant rollback** with no deploy |
| 5 | Toggle it back **on**. Turn on `health-score-v2-calc`, as Dana | Within about 3 seconds, the panel says **Scoring v2**, and 5 accounts show **Error** (HTTP 500). Sort the **Health** column to bring them to the top. **The bug is real:** v2 divides by open tickets, which is zero for some accounts |
| 6 | **Remediate manually:** run `./scripts/kill-switch.sh` (Git Bash/macOS/Linux) or `Invoke-RestMethod -Method Post -Uri <LD_TRIGGER_URL>` (PowerShell) | The trigger turns v2 **off**. Within about 3 seconds the errors clear and **Scoring v1** returns. The panel stays: only the bad change was removed. The flag's **History** in LaunchDarkly shows the trigger and its message |
| 7 | **Remediate automatically:** turn v2 back on, then run `python scripts/watchdog.py` in a second terminal. Reload `/app` as Dana, or click a few accounts | The watchdog prints the error rate every 5 seconds. Once it passes **5%** (with at least 20 requests in the last minute) it fires the trigger and exits, and the app recovers on its own |

**What the watchdog stands in for:** in production this is a Datadog or New Relic alert whose
webhook calls the LaunchDarkly trigger URL. Nobody has to be awake for the rollback.
`python scripts/watchdog.py --help` lists the threshold, minimum-request, and interval options.
`--dry-run` reports a breach without firing.

### 5.2 Target (Part 2): `/`

**Scenario:** several teams are revamping the landing page, which gets about 40,000 visitors a day.
This team owns the **hero**. They want to show each audience the hero that fits them, keep
restricted audiences on the current page, and limit everyone else's exposure.

**Before you start:** `landing-hero` is set up as in section 3.2, and the flag is **on**.

Under **Flags (live)**, the demo panel shows each flag's value **and the reason** LaunchDarkly
returned for it (*Individual target*, *Rule N*, *Default rule*). That makes every targeting
decision visible.

| # | Do: pick persona | Watch: hero | Panel reason | Why |
|---|---|---|---|---|
| 1 | **Enterprise SaaS visitor** (US · SaaS · 2,000 employees) | ROI calculator | Rule 4 | Enterprise buyer, no restrictions |
| 2 | **Mid-market fintech visitor** (US · Fintech · from LinkedIn) | Control | Rule 2 | Matches rule 2 *and* rule 3. The first match wins, so compliance beats channel |
| 3 | **German startup visitor** (DE) | Control | Rule 1 | Localization hold |
| 4 | **LinkedIn visitor** (US · Retail) | Social proof | Rule 3 | Social-channel audience |
| 5 | **QA tester** (`qa-tester-01`, based in DE) | ROI calculator | Individual target | Individual targeting beats the DE rule, so QA can test the new hero |
| 6 | **Sales demo** (`sales-demo`, Fintech) | ROI calculator | Individual target | Sales can demo it despite the compliance hold |
| 7 | **Random visitor**, then click **↻ New random visitor** several times | Usually Control, sometimes ROI calculator | Default rule (or a rule, if the random attributes match one) | The 10% percentage rollout. A visitor keeps its bucket across reloads |

**Live targeting change:** with the **German startup visitor** selected, remove `DE` from rule 1
in LaunchDarkly and save. Without a reload, the hero changes as the visitor falls through to the
default rollout.

Try the ROI calculator's inputs too: the results update as you type.

- 5.3 Experimentation: _Coming in Phase 4_
- 5.4 AI Configs: _Coming in Phase 5_

---

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `Address already in use` or nothing loads on port 5000 (common on macOS, where AirPlay Receiver uses 5000) | Set `PORT=5050` in `.env`, restart, and open `http://localhost:5050`. |
| `Missing .../data/accounts.json` on startup | Run `python scripts/seed_data.py`. |
| `ModuleNotFoundError: No module named 'flask'` | Activate the virtual environment (step 4.1), then `pip install -r requirements.txt`. |
| `python` not found on macOS/Linux | Use `python3`. |
| Demo panel shows **Not configured** | `LD_SDK_KEY` / `LD_CLIENT_SIDE_ID` is missing from `.env`. Add it and restart the server. |
| Server SDK shows **Error: HTTP 401** | The SDK key is wrong or belongs to another environment. Copy it again from **Project settings → Environments**. |
| Browser SDK shows **Failed** or **Timed out** | Check `LD_CLIENT_SIDE_ID`. Ad blockers and privacy extensions often block `*.launchdarkly.com`; allow the site or try a private window. |
| A flag always shows its fallback in the browser | Enable **SDKs using Client-side ID** in the flag's settings, and check that the flag key matches exactly. |
| Changes in the code don't show up | Stop **every** running copy of `python app.py`. On Windows, a second server can quietly share port 5000 with an old one. |
| `kill-switch.sh`: `LD_TRIGGER_URL is not set` | Add the trigger URL to `.env` (section 3.2). |
| Trigger call returns HTTP 404 | The trigger URL was reset or the trigger was deleted. Create or reset it and update `.env`. |
| `bash: ./scripts/kill-switch.sh: Permission denied` | Run `bash scripts/kill-switch.sh`, or `chmod +x scripts/kill-switch.sh`. |
| Demo panel shows `"Variation 1"` (etc.) and the hero never changes | The flag still has LaunchDarkly's placeholder **values**. Set them to `control`, `roi-calculator` and `social-proof` on the flag's Variations tab. Targeting stays attached to the same variations. |
| A persona gets the "wrong" hero | Compare the panel's reason with the table in 5.2. Usually the rules are in a different order, a value has the wrong case, or `companySize` was entered as text instead of a number. |
| Hero briefly shows the old version | Expected for up to 1 second while flags load (anti-flicker). Production would bootstrap flag values from the server instead. |
| Watchdog never fires | It needs at least 20 health requests in the last minute. Reload `/app` as a persona who gets v2 (e.g. Dana), and check that `health-score-v2-calc` is on. |

---

## 7. Design decisions & production considerations

_Coming in Phase 7._

---

## Project layout

```
abc-pulse/
├── app.py               # Flask server: pages + JSON API
├── ld.py                # LaunchDarkly server SDK setup + evaluate() helper
├── flags.py             # Flag keys and fallback values (server side)
├── personas.py          # Demo personas = LaunchDarkly contexts (shared with the browser)
├── scoring.py           # Health score v1 (trusted) and v2 (intentionally buggy)
├── health_monitor.py    # Rolling error rate behind /api/health
├── requirements.txt
├── .env.example         # Every setting the app reads, with setup notes
├── data/accounts.json   # Generated fictional accounts
├── scripts/
│   ├── seed_data.py     # Generates data/accounts.json (stdlib only)
│   ├── kill-switch.sh   # Manual remediation: POST the flag trigger URL
│   └── watchdog.py      # Automatic remediation: fire the trigger on an error spike
├── static/
│   ├── index.html       # Marketing site
│   ├── app.html         # Pulse app
│   ├── css/styles.css
│   ├── js/
│   │   ├── ld.js          # LaunchDarkly browser SDK setup, flag keys, fallbacks
│   │   ├── demo-panel.js  # Demo controls: persona switcher, status, live flag values
│   │   ├── health-panel.js # NEW Account Health experience (behind account-health-panel)
│   │   ├── marketing.js
│   │   └── app.js
│   └── vendor/launchdarkly/ # Self-hosted JS SDK (unmodified npm build + license)
└── docs/PLAN.md         # Build plan
```

All company, account, and person names in this project are fictional.
