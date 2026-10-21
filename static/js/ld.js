// LaunchDarkly browser SDK setup, shared by the marketing site and the Pulse app.
//
// Other modules never touch the SDK client directly. They use the helpers
// below, so every flag read goes through one place with one set of fallback
// values, and the page works the same when LaunchDarkly isn't configured or
// can't be reached.
//
// The SDK (@launchdarkly/js-client-sdk v4) is vendored under static/vendor/,
// copied unmodified from the npm package. LaunchDarkly recommends
// self-hosting the SDK in production instead of loading it from a public CDN.

import { createClient, basicLogger } from '/static/vendor/launchdarkly/js-client-sdk@4.11.2/index.js';

// Flag keys: the browser's single source of truth (the server's is flags.py).
// LD SETUP: Each flag must exist in your LaunchDarkly project with exactly this
// key, and "SDKs using Client-side ID" must be checked in the flag's settings.
// Otherwise the browser can't see the flag and uses the fallback.
export const FLAGS = {
  ACCOUNT_HEALTH_PANEL: 'account-health-panel',
  HEALTH_SCORE_V2_CALC: 'health-score-v2-calc',
  LANDING_HERO: 'landing-hero',
};

// Value used when LaunchDarkly is unreachable, not configured, or the flag
// doesn't exist yet. Always the safe, existing experience.
export const FALLBACKS = {
  [FLAGS.ACCOUNT_HEALTH_PANEL]: false,
  [FLAGS.HEALTH_SCORE_V2_CALC]: false,
  [FLAGS.LANDING_HERO]: 'control',
};

// Seconds to wait for flag data before rendering with fallbacks.
const INIT_TIMEOUT_SECONDS = 5;

let client = null;
let status = { state: 'starting', detail: 'Connecting to LaunchDarkly…' };

const statusListeners = new Set();
const flagListeners = new Map(); // flag key -> Set of callbacks

function setStatus(state, detail) {
  status = { state, detail };
  statusListeners.forEach((cb) => cb(status));
}

// Call every callback registered for these flag keys.
function notifyFlags(keys) {
  for (const key of keys) {
    (flagListeners.get(key) || []).forEach((cb) => cb(variation(key)));
  }
}

/**
 * Start the SDK for the first context (the current visitor or user).
 * The client is created right away. The returned promise settles when the
 * first flag data arrives, or after INIT_TIMEOUT_SECONDS; either way the page
 * can render, because variation() serves fallbacks until data arrives.
 */
export async function startLD(clientSideId, context) {
  if (!clientSideId) {
    setStatus('not-configured', 'LD_CLIENT_SIDE_ID not set; using fallback values');
    return status;
  }

  client = createClient(clientSideId, context, {
    // Keep a live streaming connection so flag changes reach the page
    // instantly. This is what makes release and rollback work without a reload.
    streaming: true,
    logger: basicLogger({ level: 'warn' }),
  });

  // The "listener": LaunchDarkly pushes a change, then we re-read the flag
  // and notify whichever part of the page depends on it.
  client.on('change', (_context, changedKeys) => notifyFlags(changedKeys));
  client.on('error', (err) => console.warn('LaunchDarkly error:', err));

  const result = await client.start({ timeout: INIT_TIMEOUT_SECONDS });
  if (result.status === 'complete') {
    setStatus('connected', 'Streaming flag updates');
  } else if (result.status === 'timeout') {
    setStatus('timeout', `No response within ${INIT_TIMEOUT_SECONDS}s; using fallback values`);
  } else {
    setStatus('failed', `${result.error?.message || 'Initialization failed'}; using fallback values`);
  }
  // Re-render anything that read fallbacks before the data arrived.
  notifyFlags(flagListeners.keys());
  return status;
}

/**
 * Switch to a different context (another persona, or a user logging in).
 * LaunchDarkly re-evaluates every flag for the new context.
 */
export async function identify(context) {
  if (client) {
    const result = await client.identify(context);
    if (result.status === 'error' || result.status === 'timeout') {
      console.warn('LaunchDarkly identify did not complete:', result);
    }
  }
  // Re-render every flag-dependent part of the page for the new context.
  notifyFlags(flagListeners.keys());
}

/** Current value of a flag for the current context, or its fallback. */
export function variation(flagKey) {
  const fallback = FALLBACKS[flagKey];
  return client ? client.variation(flagKey, fallback) : fallback;
}

/** Run callback(newValue) whenever this flag's value may have changed. */
export function onFlagChange(flagKey, callback) {
  if (!flagListeners.has(flagKey)) flagListeners.set(flagKey, new Set());
  flagListeners.get(flagKey).add(callback);
}

/** Run callback(status) whenever the connection status changes. */
export function onStatusChange(callback) {
  statusListeners.add(callback);
  callback(status);
}

/** Send a custom event (used for experiment metrics in a later phase). */
export function track(eventKey, data, metricValue) {
  if (client) client.track(eventKey, data, metricValue);
}
