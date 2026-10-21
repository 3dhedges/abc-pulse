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

_Each phase adds its flags here, with exact keys, variations, and targeting:_
`account-health-panel` and `health-score-v2-calc` (Phase 2), `landing-hero` (Phase 3).
Automated setup with `scripts/setup_launchdarkly.py` is coming in Phase 6.

> **Important for every flag the browser reads:** in the flag's settings, under **Client-side
> SDK availability**, check **SDKs using Client-side ID**. Without it, the browser SDK can't
> see the flag and serves the fallback.

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
- **Flags (live):** the current value of each flag on this page. A value flashes when it
  changes in LaunchDarkly.

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

_Coming in Phases 2–5:_ a "do X, watch Y" walkthrough for each part.

- 5.1 Release & Remediate: _Coming in Phase 2_
- 5.2 Target: _Coming in Phase 3_
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
├── requirements.txt
├── .env.example         # Every setting the app reads, with setup notes
├── data/accounts.json   # Generated fictional accounts
├── scripts/
│   └── seed_data.py     # Generates data/accounts.json (stdlib only)
├── static/
│   ├── index.html       # Marketing site
│   ├── app.html         # Pulse app
│   ├── css/styles.css
│   ├── js/
│   │   ├── ld.js          # LaunchDarkly browser SDK setup, flag keys, fallbacks
│   │   ├── demo-panel.js  # Demo controls: persona switcher, status, live flag values
│   │   ├── marketing.js
│   │   └── app.js
│   └── vendor/launchdarkly/ # Self-hosted JS SDK (unmodified npm build + license)
└── docs/PLAN.md         # Build plan
```

All company, account, and person names in this project are fictional.
