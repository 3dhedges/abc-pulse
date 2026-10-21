// Marketing site behavior (/).
//
// For now this only handles the "Request a demo" button. Later phases add:
//   - rendering the hero variant chosen by the `landing-hero` flag
//   - a persona switcher that re-identifies the visitor so targeting changes live
//   - ldClient.track('demo-request-clicked') for the experiment metric

(function () {
  'use strict';

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
})();
