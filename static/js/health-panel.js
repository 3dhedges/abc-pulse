// The NEW Account Health experience, released behind the `account-health-panel` flag.
//
// Kept in its own module so the new code is easy to review, and once the flag
// is fully released and removed, the old usage-stats path in app.js can be
// deleted cleanly.
//
// Health scores come from /api/accounts/<id>/health. The server picks the
// scoring algorithm (v1, or the buggy v2 behind `health-score-v2-calc`), and
// returns HTTP 500 when v2 fails. The UI degrades to an error state for that
// account instead of breaking the page.

const SVG_NS = 'http://www.w3.org/2000/svg';

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function svgEl(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attrs)) node.setAttribute(name, value);
  return node;
}

// Score bands, shared by the table pill and the gauge.
function tier(score) {
  if (score >= 70) return 'good';
  if (score >= 45) return 'warn';
  return 'bad';
}

/**
 * Fetch one account's health score.
 * Returns { status: 'ok', ...data } or { status: 'error', httpStatus, algorithm }.
 * `api` is app.js's fetch wrapper (it adds the X-Persona header).
 */
export async function fetchHealth(api, accountId) {
  try {
    const res = await api(`/api/accounts/${encodeURIComponent(accountId)}/health`);
    const body = await res.json().catch(() => ({}));
    if (!res.ok) return { status: 'error', httpStatus: res.status, algorithm: body.algorithm };
    return { status: 'ok', ...body };
  } catch {
    return { status: 'error', httpStatus: 0 };
  }
}

// Numeric sort/filter value: the score, -1 for an error, -2 while loading.
function scoreValue(health) {
  if (health?.status === 'ok') return health.healthScore;
  return health?.status === 'error' ? -1 : -2;
}

// Small colored pill for the accounts table.
function scorePill(health) {
  if (!health || health.status === 'loading') return el('span', 'muted', '…');
  if (health.status === 'error') {
    const pill = el('span', 'score-pill score-error', 'Error');
    pill.title = `Health score failed (HTTP ${health.httpStatus || 'network error'})`;
    return pill;
  }
  return el('span', `score-pill score-${tier(health.healthScore)}`, String(health.healthScore));
}

/**
 * Column definition for the accounts table (same shape as app.js's COLUMNS).
 * getHealth(accountId) returns the cached health result for an account.
 */
export function healthColumn(getHealth) {
  const score = (a) => scoreValue(getHealth(a.id));
  return {
    key: 'health',
    label: 'Health',
    num: true,
    cell: (a) => String(score(a)),
    render: (a) => scorePill(getHealth(a.id)),
    sortValue: score,
    filter: {
      type: 'range',
      options: [
        { label: 'Healthy (70+)', test: (a) => score(a) >= 70 },
        { label: 'At risk (45–69)', test: (a) => score(a) >= 45 && score(a) < 70 },
        { label: 'Critical (<45)', test: (a) => score(a) >= 0 && score(a) < 45 },
        { label: 'Error', test: (a) => score(a) === -1 },
      ],
    },
  };
}

// Ring gauge showing the score out of 100.
function gauge(score) {
  const radius = 50;
  const circumference = 2 * Math.PI * radius;
  const svg = svgEl('svg', { viewBox: '0 0 120 120', class: `gauge gauge-${tier(score)}`, role: 'img' });
  svg.setAttribute('aria-label', `Health score ${score} out of 100`);
  svg.append(
    svgEl('circle', { cx: 60, cy: 60, r: radius, class: 'gauge-track' }),
    svgEl('circle', {
      cx: 60, cy: 60, r: radius, class: 'gauge-value',
      'stroke-dasharray': circumference,
      'stroke-dashoffset': circumference * (1 - score / 100),
      transform: 'rotate(-90 60 60)',
    }),
  );
  const label = svgEl('text', { x: 60, y: 60, class: 'gauge-label' });
  label.textContent = String(score);
  const sub = svgEl('text', { x: 60, y: 80, class: 'gauge-sub' });
  sub.textContent = 'of 100';
  svg.append(label, sub);
  return svg;
}

// 30-day login trend as an SVG sparkline.
function sparkline(values) {
  const width = 300;
  const height = 56;
  const max = Math.max(...values, 1);
  const step = width / (values.length - 1);
  const points = values.map((v, i) => `${(i * step).toFixed(1)},${(height - (v / max) * (height - 4) - 2).toFixed(1)}`);

  const svg = svgEl('svg', { viewBox: `0 0 ${width} ${height}`, class: 'sparkline', preserveAspectRatio: 'none', role: 'img' });
  svg.setAttribute('aria-label', 'Daily logins over the last 30 days');
  svg.append(
    svgEl('polygon', { points: `0,${height} ${points.join(' ')} ${width},${height}`, class: 'sparkline-area' }),
    svgEl('polyline', { points: points.join(' '), class: 'sparkline-line' }),
  );
  return svg;
}

// One labeled horizontal bar per feature.
function adoptionBars(featureAdoption) {
  const list = el('div', 'bars');
  for (const [feature, pct] of Object.entries(featureAdoption)) {
    const fill = el('div', 'bar-fill');
    fill.style.width = `${pct}%`;
    const bar = el('div', 'bar');
    bar.append(fill);
    list.append(el('span', 'bar-label', feature), bar, el('span', 'bar-value', `${pct}%`));
  }
  return list;
}

function section(title, ...children) {
  const node = el('section', 'health-section');
  node.append(el('h4', '', title), ...children);
  return node;
}

/**
 * Render the Account Health panel for one account.
 *   health: result of fetchHealth() (or { status: 'loading' })
 *   fmt:    { formatDate, money } formatters from app.js
 */
export function renderHealthPanel(container, account, health, fmt) {
  const head = el('div', 'health-head');
  head.append(el('h3', '', 'Account health'), el('span', 'pill pill-new', 'New'));
  if (health?.algorithm) head.append(el('span', 'muted health-algo', `Scoring ${health.algorithm}`));

  // Score summary: gauge + renewal outlook, or an error/loading state.
  const summary = el('div', 'health-summary');
  if (health?.status === 'ok') {
    const outlook = el('div', 'health-outlook');
    outlook.append(
      el('span', 'muted', 'Renewal likelihood'),
      el('span', `renewal renewal-${health.renewalLikelihood}`, health.renewalLikelihood),
      el('span', 'muted', `Renews ${fmt.formatDate(account.renewalDate)} · ${fmt.money.format(account.arr)} ARR`),
    );
    summary.append(gauge(health.healthScore), outlook);
  } else if (health?.status === 'error') {
    summary.append(el('p', 'error',
      `Couldn't calculate this account's health score (HTTP ${health.httpStatus || 'network error'}). ` +
      'The usage data below is still accurate.'));
  } else {
    summary.append(el('p', 'muted', 'Calculating health score…'));
  }

  const totalLogins = account.loginsTrend30d.reduce((s, v) => s + v, 0);
  const drivers = health?.status === 'ok' ? health.riskDrivers : account.riskDrivers;
  const risk = drivers.length ? el('ul', 'risk-list') : el('p', 'muted', 'No risk drivers detected.');
  drivers.forEach((d) => risk.append(el('li', '', d)));

  container.replaceChildren(
    head,
    summary,
    section('Feature adoption', adoptionBars(account.featureAdoption)),
    section(`Logins, last 30 days (${totalLogins.toLocaleString()} total)`, sparkline(account.loginsTrend30d)),
    section('Risk drivers', risk),
  );
}
