// Marketing site behavior (/).
//
// Starts LaunchDarkly (via the demo panel) and handles the "Request a demo"
// button. Later phases add:
//   - rendering the hero variant chosen by the `landing-hero` flag
//   - track('demo-request-clicked') for the experiment metric

import { initDemoPanel } from './demo-panel.js';
import { FLAGS } from './ld.js';

// Show a short confirmation message at the bottom of the screen.
function showToast(message) {
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.setAttribute('role', 'status');
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2500);
}

// The demo request is simulated. There is no backend form.
function onDemoRequest() {
  showToast("Thanks! A Pulse specialist will be in touch (simulated).");
}

document.getElementById('demo-cta').addEventListener('click', onDemoRequest);

// The persona picks which anonymous visitor (LaunchDarkly context) we simulate.
initDemoPanel({ surface: 'marketing', flags: [FLAGS.LANDING_HERO] })
  .catch((err) => console.warn('Demo panel unavailable:', err));
