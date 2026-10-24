// Pulse app behavior (/app).
//
// Loads accounts from the API and lists them in a sortable, filterable table,
// with details for the selected account.
//
// Feature flag `account-health-panel` picks the experience:
//   off (old code): plain usage-stats table
//   on  (new code): Health column + Account Health panel (static/js/health-panel.js)
// A flag change listener switches between them live, with no page reload.

import { initDemoPanel } from './demo-panel.js';
import { FLAGS, variation, onFlagChange } from './ld.js';
import { fetchHealth, healthColumn, renderHealthPanel } from './health-panel.js';
import { createAssistantPanel } from './assistant-panel.js';

const state = {
  accounts: [],
  persona: null, // current demo persona (signed-in user), from the demo panel
  selectedId: null,
  sort: { key: 'name', dir: 'asc' },
  filters: {}, // column key -> filter value ('' or missing means "any")
  health: {}, // account id -> health result (new experience only)
  healthLoadId: 0, // increments per reload, so stale responses are ignored
};

// Is the new Account Health experience released to the current user?
function healthEnabled() {
  return variation(FLAGS.ACCOUNT_HEALTH_PANEL) === true;
}

const money = new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 0,
});
const number = new Intl.NumberFormat('en-US');
// Always show the sign (+68, -12) so a score reads clearly as NPS.
const signed = new Intl.NumberFormat('en-US', { signDisplay: 'exceptZero' });

const PLAN_ORDER = { Starter: 0, Growth: 1, Enterprise: 2 };
const MS_PER_DAY = 24 * 60 * 60 * 1000;

// Below this width the layout is a single column (matches styles.css).
const narrowScreen = window.matchMedia('(max-width: 1099px)');

// Create an element with optional class and text. textContent keeps the data escaped.
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// Parse an ISO date (YYYY-MM-DD) as local midnight, avoiding timezone shifts.
function parseDate(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

// Format an ISO date as e.g. "Dec 2, 2026".
function formatDate(iso) {
  return parseDate(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  });
}

// Days from today until an ISO date (negative if it has passed).
function daysUntil(iso) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((parseDate(iso) - today) / MS_PER_DAY);
}

// Column definitions drive the header, sorting, filtering, and cells.
//   cell(a)      -> text shown in the table
//   sortValue(a) -> value to sort by (defaults to a[key])
//   filter.type  -> 'text'   : case-insensitive "contains" match on the cell text
//                   'select' : exact match; options come from the data unless listed
//                   'range'  : pick a bucket; each bucket has its own test(a)
const COLUMNS = [
  {
    key: 'name', label: 'Account', wrap: true,
    cell: (a) => a.name,
    filter: { type: 'text', placeholder: 'Search' },
  },
  {
    key: 'plan', label: 'Plan',
    cell: (a) => a.plan,
    sortValue: (a) => PLAN_ORDER[a.plan],
    filter: { type: 'select', options: ['Starter', 'Growth', 'Enterprise'] },
  },
  {
    key: 'arr', label: 'ARR', num: true,
    cell: (a) => money.format(a.arr),
    filter: {
      type: 'range',
      options: [
        { label: 'Under $25k', test: (a) => a.arr < 25000 },
        { label: '$25k–$100k', test: (a) => a.arr >= 25000 && a.arr < 100000 },
        { label: '$100k–$500k', test: (a) => a.arr >= 100000 && a.arr < 500000 },
        { label: '$500k+', test: (a) => a.arr >= 500000 },
      ],
    },
  },
  {
    key: 'seats', label: 'Seats', num: true,
    cell: (a) => number.format(a.seats),
    filter: {
      type: 'range',
      options: [
        { label: 'Under 50', test: (a) => a.seats < 50 },
        { label: '50–250', test: (a) => a.seats >= 50 && a.seats < 250 },
        { label: '250–1,000', test: (a) => a.seats >= 250 && a.seats < 1000 },
        { label: '1,000+', test: (a) => a.seats >= 1000 },
      ],
    },
  },
  {
    key: 'renewalDate', label: 'Renewal',
    cell: (a) => formatDate(a.renewalDate),
    filter: {
      type: 'range',
      // "Next N days" also includes renewals that are already overdue.
      options: [
        { label: 'Next 30 days', test: (a) => daysUntil(a.renewalDate) <= 30 },
        { label: 'Next 90 days', test: (a) => daysUntil(a.renewalDate) <= 90 },
        { label: 'Next 180 days', test: (a) => daysUntil(a.renewalDate) <= 180 },
        { label: 'Over 180 days', test: (a) => daysUntil(a.renewalDate) > 180 },
      ],
    },
  },
  {
    key: 'csmOwner', label: 'CSM', wrap: true,
    cell: (a) => a.csmOwner,
    filter: { type: 'select' }, // options built from the data
  },
];

// The Health column exists only in the new experience.
const HEALTH_COLUMN = healthColumn((id) => state.health[id]);

// Columns for the current flag value: Health goes right after Account.
function activeColumns() {
  return healthEnabled() ? [COLUMNS[0], HEALTH_COLUMN, ...COLUMNS.slice(1)] : COLUMNS;
}

// ---------- Filtering & sorting ----------

// True if the account passes every active column filter.
function matchesFilters(account) {
  return activeColumns().every((col) => {
    const value = state.filters[col.key];
    if (!value) return true;
    switch (col.filter.type) {
      case 'text': return col.cell(account).toLowerCase().includes(value.toLowerCase());
      case 'select': return account[col.key] === value;
      case 'range': return col.filter.options[Number(value)].test(account);
      default: return true;
    }
  });
}

// Compare two accounts by the current sort column and direction.
function compareAccounts(a, b) {
  const col = activeColumns().find((c) => c.key === state.sort.key);
  const value = col.sortValue || ((x) => x[col.key]);
  const va = value(a);
  const vb = value(b);
  const result = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
  return state.sort.dir === 'asc' ? result : -result;
}

// Accounts to show: filtered, then sorted.
function visibleAccounts() {
  return state.accounts.filter(matchesFilters).sort(compareAccounts);
}

function hasActiveFilters() {
  return Object.values(state.filters).some(Boolean);
}

// ---------- Header (sort buttons + filter controls) ----------

// Build the filter control for one column.
function buildFilterControl(col) {
  const current = state.filters[col.key] || '';
  let control;

  if (col.filter.type === 'text') {
    control = el('input', 'filter-input');
    control.type = 'search';
    control.placeholder = col.filter.placeholder || 'Filter';
    control.value = current;
    control.addEventListener('input', () => setFilter(col.key, control.value));
  } else {
    control = el('select', 'filter-input');
    control.append(new Option('All', ''));
    if (col.filter.type === 'range') {
      // Option values are bucket indexes into col.filter.options.
      col.filter.options.forEach((opt, i) => control.append(new Option(opt.label, String(i))));
    } else {
      const options = col.filter.options
        || [...new Set(state.accounts.map((a) => a[col.key]))].sort();
      options.forEach((opt) => control.append(new Option(opt, opt)));
    }
    control.value = current;
    control.addEventListener('change', () => setFilter(col.key, control.value));
  }

  control.setAttribute('aria-label', `Filter by ${col.label}`);
  return control;
}

// Render both header rows: column titles (click to sort) and filters.
function renderHeader() {
  const titleRow = el('tr');
  const filterRow = el('tr', 'filter-row');

  for (const col of activeColumns()) {
    const th = el('th', col.num ? 'num' : '');
    th.dataset.key = col.key;
    th.scope = 'col';
    const button = el('button', 'sort-btn');
    button.type = 'button';
    button.append(el('span', '', col.label), el('span', 'sort-icon'));
    button.addEventListener('click', () => setSort(col.key));
    th.append(button);
    titleRow.append(th);

    const filterCell = el('th', col.num ? 'num' : '');
    filterCell.append(buildFilterControl(col));
    filterRow.append(filterCell);
  }

  document.querySelector('#accounts-table thead').replaceChildren(titleRow, filterRow);
  updateSortIndicators();
}

// Mark the sorted column with aria-sort; the CSS draws the arrow from it.
function updateSortIndicators() {
  document.querySelectorAll('#accounts-table thead th[data-key]').forEach((th) => {
    if (th.dataset.key === state.sort.key) {
      th.setAttribute('aria-sort', state.sort.dir === 'asc' ? 'ascending' : 'descending');
    } else {
      th.removeAttribute('aria-sort');
    }
  });
}

// Clicking the sorted column flips direction; clicking another column sorts it ascending.
function setSort(key) {
  if (state.sort.key === key) {
    state.sort.dir = state.sort.dir === 'asc' ? 'desc' : 'asc';
  } else {
    state.sort = { key, dir: 'asc' };
  }
  updateSortIndicators();
  renderAccountList();
}

function setFilter(key, value) {
  state.filters[key] = value;
  renderAccountList();
}

function clearFilters() {
  state.filters = {};
  renderHeader(); // resets every control to "All"
  renderAccountList();
}

// ---------- Account list ----------

// Fill the table body with the visible accounts, one clickable row each.
function renderAccountList() {
  const rows = visibleAccounts();
  const tbody = document.querySelector('#accounts-table tbody');
  tbody.replaceChildren();

  for (const a of rows) {
    const row = el('tr');
    row.dataset.id = a.id;
    row.tabIndex = 0; // reachable by keyboard; Enter selects
    row.classList.toggle('selected', a.id === state.selectedId);
    for (const col of activeColumns()) {
      const classes = [col.num ? 'num' : '', col.wrap ? 'wrap' : ''].join(' ').trim();
      const td = el('td', classes);
      // render() returns a node (e.g. the health pill); otherwise plain text.
      if (col.render) td.append(col.render(a));
      else td.textContent = col.cell(a);
      row.append(td);
    }
    row.addEventListener('click', () => selectAccount(a.id, true));
    row.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') selectAccount(a.id, true);
    });
    tbody.append(row);
  }

  if (!rows.length) {
    const empty = el('td', 'empty', 'No accounts match these filters.');
    empty.colSpan = activeColumns().length;
    const tr = el('tr', 'empty-row');
    tr.append(empty);
    tbody.append(tr);
  }

  const total = state.accounts.length;
  document.getElementById('account-count').textContent =
    rows.length === total ? `${total} accounts` : `${rows.length} of ${total} accounts`;
  document.getElementById('clear-filters').hidden = !hasActiveFilters();
}

// ---------- Account detail ----------

// OLD CODE: plain usage-stats table, shown when `account-health-panel` is off.
function renderUsageStats(account) {
  const adoption = Object.values(account.featureAdoption);
  const avgAdoption = Math.round(adoption.reduce((s, v) => s + v, 0) / adoption.length);
  const rows = [
    ['Industry', account.industry],
    ['Seats', number.format(account.seats)],
    ['Weekly active users', number.format(account.weeklyActiveUsers)],
    ['Seat utilization', `${account.seatUtilization}%`],
    ['Avg. feature adoption', `${avgAdoption}%`],
    ['Logins (last 30 days)', number.format(account.loginsTrend30d.reduce((s, v) => s + v, 0))],
    ['NPS (−100 to +100)', signed.format(account.nps)],
    ['Open tickets', account.openTickets],
    ['Time to value', `${account.timeToValueDays} days`],
    ['QBR completed', account.qbrCompleted ? 'Yes' : 'No'],
    ['ARR', money.format(account.arr)],
    ['Renewal date', formatDate(account.renewalDate)],
  ];

  const table = el('table', 'kv');
  const tbody = el('tbody');
  for (const [label, value] of rows) {
    const tr = el('tr');
    tr.append(el('th', '', label), el('td', '', String(value)));
    tbody.append(tr);
  }
  table.append(tbody);
  document.getElementById('usage-stats').replaceChildren(el('h3', 'muted', 'Usage stats'), table);
}

// Show the selected account's details in whichever experience the flag selects.
function renderDetail() {
  const account = state.accounts.find((a) => a.id === state.selectedId);
  if (!account) return;
  const slot = document.getElementById('health-panel-slot');
  const usage = document.getElementById('usage-stats');
  const showNew = healthEnabled();

  slot.hidden = !showNew;
  usage.hidden = showNew;
  if (showNew) {
    renderHealthPanel(slot, account, state.health[account.id] || { status: 'loading' }, { formatDate, money });
  } else {
    renderUsageStats(account);
  }
}

// ---------- Health scores (new experience) ----------

// Fetch every account's health score in parallel, then re-render. Runs when
// the panel is released and whenever the scoring flag changes.
async function loadAllHealth() {
  const loadId = ++state.healthLoadId;
  state.health = {};
  renderAccountList();
  renderDetail();

  const results = await Promise.all(state.accounts.map((a) => fetchHealth(api, a.id)));
  if (loadId !== state.healthLoadId) return; // a newer reload started; drop these
  state.accounts.forEach((a, i) => { state.health[a.id] = results[i]; });
  renderAccountList();
  renderDetail();
}

// Refresh just the selected account's score (fresh data when a user opens an account).
async function refreshSelectedHealth() {
  const id = state.selectedId;
  const loadId = state.healthLoadId;
  const result = await fetchHealth(api, id);
  if (loadId !== state.healthLoadId) return;
  state.health[id] = result;
  renderAccountList();
  renderDetail();
}

// The flag LISTENERS: LaunchDarkly pushes a change, and the page switches
// between the old and new experience instantly, with no reload.
function onHealthPanelFlagChange() {
  if (!state.accounts.length) return; // init() renders once accounts load
  if (!healthEnabled()) {
    // Rolled back: drop health-only sort and filter state, and the cached
    // scores, which may belong to another persona or scoring algorithm.
    state.health = {};
    delete state.filters.health;
    if (state.sort.key === 'health') state.sort = { key: 'name', dir: 'asc' };
  }
  renderHeader();
  renderAccountList();
  renderDetail();
  if (healthEnabled() && !Object.keys(state.health).length) loadAllHealth();
}

let lastScoringValue = variation(FLAGS.HEALTH_SCORE_V2_CALC); // starts at the fallback
function onScoringFlagChange(useV2) {
  // v1 <-> v2 changed on the server (e.g. the trigger fired): rescore.
  if (useV2 === lastScoringValue) return; // listeners also fire on persona switches
  lastScoringValue = useV2;
  if (state.accounts.length && healthEnabled()) loadAllHealth();
}

// Highlight the chosen row and show that account's details. On narrow
// screens the detail panel sits below the list, so scroll it into view.
function selectAccount(id, fromUser) {
  state.selectedId = id;
  const account = state.accounts.find((a) => a.id === id);
  document.querySelectorAll('#accounts-table tbody tr').forEach((tr) => {
    tr.classList.toggle('selected', tr.dataset.id === id);
  });
  document.getElementById('detail-name').textContent = account.name;
  const plan = document.getElementById('detail-plan');
  plan.textContent = account.plan;
  plan.hidden = false;
  renderDetail();
  assistantPanel.show(account);
  if (fromUser && healthEnabled()) refreshSelectedHealth();

  if (fromUser && narrowScreen.matches) {
    document.getElementById('account-detail').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

// Show a load error in the detail panel.
function showError(message) {
  const usage = document.getElementById('usage-stats');
  usage.hidden = false;
  usage.replaceChildren(el('p', 'error', message));
}

// Call the API as the current persona. The server builds the same
// LaunchDarkly context from X-Persona, so server-side flags match the browser.
function api(path, options = {}) {
  const headers = { ...options.headers, ...(state.persona ? { 'X-Persona': state.persona.id } : {}) };
  return fetch(path, { ...options, headers });
}

// AI account assistant, below the account details. Its model and prompt come
// from the `account-assistant` AI Config, per signed-in user.
const assistantPanel = createAssistantPanel(document.getElementById('assistant-slot'), api);

// Show the signed-in user (the selected persona) in the header. A different
// user may get a different AI Config variation, so the assistant resets too.
function onPersonaChange(persona) {
  state.persona = persona;
  const { name, role } = persona.context.user;
  document.getElementById('signed-in-as').textContent = `Signed in as ${name} (${role})`;
  const account = state.accounts.find((a) => a.id === state.selectedId);
  if (account) assistantPanel.show(account);
}

// Start the demo panel and LaunchDarkly, fetch accounts, build the table,
// and select the first account.
async function init() {
  onFlagChange(FLAGS.ACCOUNT_HEALTH_PANEL, onHealthPanelFlagChange);
  onFlagChange(FLAGS.HEALTH_SCORE_V2_CALC, onScoringFlagChange);

  try {
    await initDemoPanel({
      surface: 'app',
      flags: [FLAGS.ACCOUNT_HEALTH_PANEL],
      serverFlags: [FLAGS.HEALTH_SCORE_V2_CALC], // evaluated on the server only
      onPersonaChange,
    });
  } catch (err) {
    // Without the panel the app still works, just without flags or personas.
    console.warn('Demo panel unavailable:', err);
  }

  try {
    const res = await api('/api/accounts');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    state.accounts = await res.json();
  } catch (err) {
    showError(`Could not load accounts (${err.message}). Is the server running?`);
    return;
  }
  document.getElementById('clear-filters').addEventListener('click', clearFilters);
  renderHeader();
  renderAccountList();
  const first = visibleAccounts()[0];
  if (first) selectAccount(first.id, false);
  if (healthEnabled()) loadAllHealth();
}

init();
