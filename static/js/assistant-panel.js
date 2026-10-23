// Account assistant UI: "Summarize this account" plus thumbs up/down.
//
// The server (assistant.py) asks the LaunchDarkly AI Config which model and
// prompt to use for the signed-in user, calls the model (or the mock), and
// returns the text plus metadata. Feedback goes back to LaunchDarkly, where
// it appears on the AI Config's Monitoring tab.

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// Append text to a node, turning **bold** spans into <strong>. Text-only, so
// model output can never inject HTML.
function appendInline(node, text) {
  text.split(/(\*\*[^*]+\*\*)/).forEach((part) => {
    if (/^\*\*[^*]+\*\*$/.test(part)) node.append(el('strong', '', part.slice(2, -2)));
    else if (part) node.append(part);
  });
}

// Minimal Markdown: "#"-headings, "-"/"*" bullet lists, paragraphs, and **bold**.
function renderText(text) {
  const out = el('div', 'assistant-text');
  let list = null;
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line) { list = null; continue; }
    const heading = line.match(/^#{1,6}\s+(.*)/);
    const bullet = line.match(/^[-*•]\s+(.*)/);
    if (heading) {
      list = null;
      out.append(el('h5', '', heading[1]));
    } else if (bullet) {
      if (!list) { list = el('ul'); out.append(list); }
      const li = el('li');
      appendInline(li, bullet[1]);
      list.append(li);
    } else {
      list = null;
      const p = el('p', line.startsWith('[Mock') ? 'muted' : '');
      appendInline(p, line);
      out.append(p);
    }
  }
  return out;
}

// "exec-brief · claude-haiku-5-5 · 0.6s · 332 tokens (est.) · mock"
function metaLine(r) {
  const tokens = `${r.tokens.total.toLocaleString()} tokens${r.provider === 'mock' ? ' (est.)' : ''}`;
  return [r.variation, r.model, `${(r.durationMs / 1000).toFixed(1)}s`, tokens, r.provider].join(' · ');
}

/**
 * Create the assistant panel inside `container`.
 *   api(path, options) is app.js's fetch wrapper (it adds the X-Persona header).
 * Returns { show(account) }: call it whenever the selected account changes.
 */
export function createAssistantPanel(container, api) {
  let account = null;
  let requestId = 0; // ignore responses for an account that's no longer selected

  const post = (path, body) => api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  // Thumbs up/down for one response; one vote, then a thank-you.
  function feedbackRow(token) {
    const row = el('div', 'assistant-feedback');
    row.append(el('span', 'muted', 'Was this helpful?'));
    for (const [label, positive] of [['👍', true], ['👎', false]]) {
      const btn = el('button', 'btn btn-secondary btn-small', label);
      btn.type = 'button';
      btn.setAttribute('aria-label', positive ? 'Helpful' : 'Not helpful');
      btn.addEventListener('click', async () => {
        row.querySelectorAll('button').forEach((b) => { b.disabled = true; });
        const res = await post('/api/assistant/feedback', { token, positive }).catch(() => null);
        row.replaceChildren(el('span', 'muted', res?.ok ? 'Thanks for the feedback.' : 'Couldn’t send feedback.'));
      });
      row.append(btn);
    }
    return row;
  }

  async function summarize(button, result) {
    const id = ++requestId;
    button.disabled = true;
    result.replaceChildren(el('p', 'muted', 'Summarizing…'));

    let res;
    let body;
    try {
      res = await post('/api/assistant', { accountId: account.id });
      body = await res.json();
    } catch {
      body = { error: 'Couldn’t reach the server.' };
    }
    if (id !== requestId) return; // the user moved on to another account
    button.disabled = false;

    if (!res?.ok || body.error) {
      result.replaceChildren(el('p', 'error', body.error || `Request failed (HTTP ${res?.status}).`));
    } else if (!body.enabled) {
      result.replaceChildren(el('p', 'muted', body.message));
    } else {
      result.replaceChildren(
        el('p', 'assistant-meta mono', metaLine(body)),
        renderText(body.text),
        feedbackRow(body.feedbackToken),
      );
    }
  }

  function show(selected) {
    account = selected;
    requestId += 1; // cancel any in-flight request for the previous account

    const head = el('div', 'assistant-head');
    head.append(el('h4', '', 'Account assistant'), el('span', 'pill pill-new', 'AI'));
    const button = el('button', 'btn btn-primary btn-small', 'Summarize this account');
    button.type = 'button';
    const result = el('div', 'assistant-result');
    button.addEventListener('click', () => summarize(button, result));

    container.replaceChildren(head, button, result);
  }

  return { show };
}
