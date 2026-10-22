// Marketing site behavior (/).
//
// The hero is behind the `landing-hero` flag (string), with three variants:
//   control         the existing hero (in the page markup, and the fallback)
//   roi-calculator  interactive churn/ROI calculator (<template id="hero-roi-calculator">)
//   social-proof    customer stats and a testimonial (<template id="hero-social-proof">)
// Which one a visitor sees is decided by targeting in LaunchDarkly: individual
// targets, rules on context attributes, then a percentage rollout.

import { initDemoPanel } from './demo-panel.js';
import { FLAGS, METRICS, variation, onFlagChange, onStatusChange, track } from './ld.js';

const hero = document.getElementById('hero');

// The control markup is captured at load, so we can swap back to it.
const variants = {
  control: hero.querySelector('.container').cloneNode(true),
  'roi-calculator': document.getElementById('hero-roi-calculator'),
  'social-proof': document.getElementById('hero-social-proof'),
};

// Longest the hero stays hidden waiting for flags (anti-flicker).
const MAX_PENDING_MS = 1000;

// ---------- Hero variants ----------

// Show the hero for a flag value. Unknown values fall back to control, so a
// typo in a new variation can never blank the hero.
function renderHero(value) {
  if (!(value in variants)) {
    console.warn(`landing-hero returned unknown variation ${JSON.stringify(value)}; showing "control". ` +
      `Expected one of: ${Object.keys(variants).join(', ')}. Check the variation values in LaunchDarkly.`);
  }
  const name = value in variants ? value : 'control';
  if (hero.dataset.variant === name) return;

  const source = variants[name];
  const content = source instanceof HTMLTemplateElement
    ? source.content.firstElementChild.cloneNode(true)
    : source.cloneNode(true);

  hero.dataset.variant = name;
  hero.replaceChildren(content);
  hero.classList.remove('hero-swap');
  void hero.offsetWidth; // restart the fade-in animation
  hero.classList.add('hero-swap');

  if (name === 'roi-calculator') initRoiCalculator(hero.querySelector('[data-roi]'));
}

// Reveal the hero once flag data has arrived (or LaunchDarkly is unavailable).
function revealHero() {
  hero.classList.remove('hero-pending');
}

// ---------- ROI calculator ----------

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

// Assumed churn reduction with Pulse. Illustrative, and footnoted on the page.
// This kind of claim is why regulated industries are held on "control" (rule 2).
const CHURN_REDUCTION = 0.2;

// Recalculate the results whenever an input changes.
function initRoiCalculator(form) {
  const update = () => {
    const accounts = Math.max(0, Number(form.accounts.value) || 0);
    const arr = Math.max(0, Number(form.arr.value) || 0);
    const churn = Math.min(100, Math.max(0, Number(form.churn.value) || 0)) / 100;

    const lost = accounts * arr * churn;
    form.querySelector('[data-out="lost"]').textContent = usd.format(lost);
    form.querySelector('[data-out="saved"]').textContent = usd.format(lost * CHURN_REDUCTION);
  };
  form.addEventListener('input', update);
  form.addEventListener('submit', (e) => e.preventDefault()); // Enter shouldn't reload the page
  update();
}

// ---------- Call to action ----------

// Show a short confirmation message at the bottom of the screen.
function showToast(message) {
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.setAttribute('role', 'status');
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2500);
}

// One delegated handler covers the CTA in every variant, plus the Pricing
// link. Each click is sent to LaunchDarkly as a custom event; the experiment's
// metrics count them per variation. The demo request itself is simulated;
// there is no backend form.
document.addEventListener('click', (e) => {
  if (e.target.closest('[data-cta="demo"]')) {
    track(METRICS.DEMO_REQUEST_CLICKED); // primary metric
    showToast('Thanks! A Pulse specialist will be in touch (simulated).');
  } else if (e.target.closest('[data-track="pricing"]')) {
    track(METRICS.PRICING_PAGE_VIEWED); // secondary (guardrail) metric
  }
});

// ---------- LaunchDarkly wiring ----------

// The LISTENER: re-render the hero whenever landing-hero changes for this
// visitor, whether targeting was edited in LaunchDarkly or the persona changed.
onFlagChange(FLAGS.LANDING_HERO, renderHero);

// Reveal as soon as the SDK has settled, whether it connected, timed out,
// or isn't configured.
onStatusChange((status) => {
  if (status.state !== 'starting') revealHero();
});
setTimeout(revealHero, MAX_PENDING_MS);

renderHero(variation(FLAGS.LANDING_HERO));

// The persona picks which visitor (LaunchDarkly context) we simulate.
initDemoPanel({ surface: 'marketing', flags: [FLAGS.LANDING_HERO] })
  .catch((err) => {
    console.warn('Demo panel unavailable:', err);
    revealHero();
  });
