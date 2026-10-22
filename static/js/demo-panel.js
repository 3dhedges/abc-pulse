// Demo controls panel: shared by both pages, and NOT part of the product.
//
// It stands in for "who is visiting". A persona switcher calls identify()
// with a different LaunchDarkly context, so targeting changes appear live.
// The panel also shows both SDKs' connection status and this page's flag
// values, updated by the SDK's change listener.
//
// Personas come from the server (/api/config, defined in personas.py), so
// the browser and server always agree on each context.

import {
  startLD, identify, variation, variationDetail, onFlagChange, onStatusChange, watchServerFlags,
} from './ld.js';

const STATUS_TEXT = {
  starting: 'Connecting',
  connected: 'Connected',
  connecting: 'Connecting',
  timeout: 'Timed out',
  failed: 'Failed',
  error: 'Error',
  'not-configured': 'Not configured',
};

// Random-visitor attribute pools. Repeats make common values more likely.
const RANDOM_POOLS = {
  industry: ['SaaS', 'SaaS', 'Fintech', 'Healthcare', 'Retail', 'Logistics', 'EdTech', 'Manufacturing'],
  companySize: [15, 40, 120, 300, 800, 2500, 10000],
  country: ['US', 'US', 'US', 'GB', 'CA', 'DE', 'FR', 'AU'],
  referrer: ['organic', 'google-ads', 'linkedin', 'direct', 'partner'],
  device: ['desktop', 'desktop', 'mobile', 'tablet'],
};

// localStorage can throw (private mode, blocked storage), so wrap every access.
const storage = {
  get(key) {
    try { return JSON.parse(localStorage.getItem(key)); } catch { return null; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* not persisted */ }
  },
};

const pick = (list) => list[Math.floor(Math.random() * list.length)];

// A brand-new anonymous visitor: random key and random attributes.
function newRandomVisitor() {
  const context = { kind: 'user', key: crypto.randomUUID(), anonymous: true };
  for (const [attr, pool] of Object.entries(RANDOM_POOLS)) context[attr] = pick(pool);
  storage.set('pulse.randomVisitor', context);
  return context;
}

// The saved random visitor, so reloads keep the same rollout bucket.
function randomVisitor() {
  return storage.get('pulse.randomVisitor') || newRandomVisitor();
}

function contextFor(persona) {
  return persona.id === 'random' ? randomVisitor() : persona.context;
}

// One-line summary of the persona, shown under the dropdown.
function describe(persona) {
  if (persona.id !== 'random') return persona.description;
  const c = randomVisitor();
  return `Anonymous · ${c.country} · ${c.industry} · ${c.companySize.toLocaleString()} employees · ${c.device}`;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// Build the panel's DOM and return the elements we update later.
// serverFlags are shown with a "server" tag: their values come from the server.
function buildPanel(personas, currentId, flags, serverFlags) {
  const panel = el('aside', 'demo-panel');
  panel.setAttribute('aria-label', 'Demo controls');

  const toggle = el('button', 'demo-panel-toggle', 'Demo controls');
  toggle.type = 'button';

  const body = el('div', 'demo-panel-body');
  body.id = 'demo-panel-body';
  toggle.setAttribute('aria-controls', body.id);

  const note = el('p', 'demo-panel-note', 'Not part of the product. Simulates who is using the page.');

  const label = el('label', 'demo-label', 'Persona');
  const select = el('select', 'filter-input');
  for (const p of personas) select.append(new Option(p.label, p.id));
  select.value = currentId;
  label.append(select);

  const desc = el('p', 'demo-persona-desc');
  const reroll = el('button', 'link-btn', '↻ New random visitor');
  reroll.type = 'button';

  const statusList = el('dl', 'demo-list');
  const browserStatus = el('dd');
  const serverStatus = el('dd');
  statusList.append(el('dt', '', 'Browser SDK'), browserStatus, el('dt', '', 'Server SDK'), serverStatus);

  const flagList = el('dl', 'demo-list demo-flags');
  const flagValues = {};
  for (const key of [...flags, ...serverFlags]) {
    const name = el('dt', 'mono', key);
    if (serverFlags.includes(key)) {
      const tag = el('span', 'demo-tag', 'server');
      tag.title = 'Evaluated on the server (not exposed to client-side SDKs)';
      name.append(' ', tag);
    }
    flagValues[key] = el('dd');
    flagValues[key].append(el('span', 'demo-value mono'), el('span', 'demo-reason'));
    flagList.append(name, flagValues[key]);
  }

  body.append(note, label, desc, reroll, el('h4', '', 'Connection'), statusList,
    el('h4', '', 'Flags (live)'), flagList);
  panel.append(toggle, body);
  document.body.append(panel);

  return { panel, toggle, select, desc, reroll, browserStatus, serverStatus, flagValues };
}

// Show a status as a colored dot plus text; the full detail goes in the tooltip.
function renderStatus(target, status) {
  target.replaceChildren(el('span', `dot dot-${status.state}`), STATUS_TEXT[status.state] || status.state);
  target.title = status.detail || '';
}

// Plain-English evaluation reason: why this context got this value.
// Rule numbers are 1-based, matching the rule order in the LaunchDarkly UI.
function reasonText(reason) {
  let text;
  switch (reason.kind) {
    case 'TARGET_MATCH': text = 'Individual target'; break;
    case 'RULE_MATCH': text = `Rule ${reason.ruleIndex + 1}`; break;
    case 'FALLTHROUGH': text = 'Default rule'; break;
    case 'OFF': text = 'Flag off'; break;
    case 'PREREQUISITE_FAILED': text = `Prerequisite ${reason.prerequisiteKey} not met`; break;
    case 'FALLBACK': text = 'Fallback (not configured)'; break;
    case 'ERROR':
      text = reason.errorKind === 'FLAG_NOT_FOUND'
        ? 'Fallback (flag not found)'
        : `Fallback (${(reason.errorKind || 'error').toLowerCase().replace(/_/g, ' ')})`;
      break;
    default: text = reason.kind || '';
  }
  return reason.inExperiment ? `${text} · in experiment` : text;
}

// Show a flag's value and reason, and briefly highlight the value when it changes.
function renderFlag(target, value, reason) {
  const text = JSON.stringify(value);
  const valueEl = target.querySelector('.demo-value');
  if (valueEl.textContent && valueEl.textContent !== text) {
    valueEl.classList.remove('flash');
    void valueEl.offsetWidth; // restart the animation
    valueEl.classList.add('flash');
  }
  valueEl.textContent = text;
  target.querySelector('.demo-reason').textContent = reason;
}

/**
 * Start LaunchDarkly and the demo panel for this page.
 *   surface:         'marketing' or 'app' (which persona list to use)
 *   flags:           client-side flag keys to show in the panel
 *   serverFlags:     server-only flag keys, polled from /api/server-flags
 *   onPersonaChange: called with the persona at startup and on every switch
 * Returns once the persona is known. LaunchDarkly keeps connecting in the
 * background, so the page never waits on it to render.
 */
export async function initDemoPanel({ surface, flags, serverFlags = [], onPersonaChange = () => {} }) {
  const config = await fetch('/api/config').then((r) => r.json());
  const personas = config.personas[surface];
  const storageKey = `pulse.persona.${surface}`;
  let persona = personas.find((p) => p.id === storage.get(storageKey)) || personas[0];

  const ui = buildPanel(personas, persona.id, flags, serverFlags);
  if (serverFlags.length) {
    // The server evaluates these for the current persona, sent as X-Persona.
    watchServerFlags(serverFlags, () => ({ 'X-Persona': persona.id }));
  }

  const showPersona = () => {
    ui.desc.textContent = describe(persona);
    ui.reroll.hidden = persona.id !== 'random';
  };
  showPersona();

  // Collapse/expand, remembered between visits.
  const setCollapsed = (collapsed) => {
    ui.panel.classList.toggle('collapsed', collapsed);
    ui.toggle.setAttribute('aria-expanded', String(!collapsed));
    storage.set('pulse.demoPanelCollapsed', collapsed);
  };
  // Default: collapsed on phones (it would cover most of the page), open elsewhere.
  const saved = storage.get('pulse.demoPanelCollapsed');
  setCollapsed(saved ?? window.matchMedia('(max-width: 700px)').matches);
  ui.toggle.addEventListener('click', () => setCollapsed(!ui.panel.classList.contains('collapsed')));

  // Live flag values, with the reason for client-side flags. The browser
  // can't see server-only flags' reasons, so those just say "Server".
  const showFlag = (key) => {
    if (serverFlags.includes(key)) {
      renderFlag(ui.flagValues[key], variation(key), 'Server-evaluated');
    } else {
      const { value, reason } = variationDetail(key);
      renderFlag(ui.flagValues[key], value, reasonText(reason));
    }
  };
  for (const key of [...flags, ...serverFlags]) {
    showFlag(key);
    onFlagChange(key, () => showFlag(key));
  }

  // Connection status: browser SDK live, server SDK fetched from the API.
  onStatusChange((status) => renderStatus(ui.browserStatus, status));
  fetch('/api/status').then((r) => r.json())
    .then((s) => renderStatus(ui.serverStatus, s.server))
    .catch(() => renderStatus(ui.serverStatus, { state: 'error', detail: 'Server unreachable' }));

  // Switch to another persona: re-identify, so flags re-evaluate for the new context.
  const switchTo = async (context) => {
    showPersona();
    onPersonaChange(persona);
    await identify(context);
  };
  ui.select.addEventListener('change', () => {
    persona = personas.find((p) => p.id === ui.select.value);
    storage.set(storageKey, persona.id);
    switchTo(contextFor(persona));
  });
  ui.reroll.addEventListener('click', () => switchTo(newRandomVisitor()));

  onPersonaChange(persona);
  startLD(config.clientSideId, contextFor(persona)); // not awaited: render now, update when data arrives
  return persona;
}
