/**
 * pages/settings.js — LLM provider slots, API keys, email defaults, sender accounts
 */
import { settingsAPI, accountsAPI } from '../api.js';
import { esc, getVal, setVal } from '../utils.js';
import { toast } from '../toast.js';

// ─────────────────────────────────────────────────────────────────────────────
// LLM PROVIDER CONFIG  (dropdown options + key placeholder hints only)
// No hardcoded default models — user types whatever model name they want.
// ─────────────────────────────────────────────────────────────────────────────

const LLM_PROVIDERS = [
  { value: 'groq',       label: 'Groq',         ph: 'gsk_…',      hint: 'console.groq.com' },
  { value: 'openrouter', label: 'OpenRouter',    ph: 'sk-or-v1-…', hint: 'openrouter.ai/keys' },
  { value: 'openai',     label: 'OpenAI',        ph: 'sk-proj-…',  hint: 'platform.openai.com/api-keys' },
  { value: 'anthropic',  label: 'Anthropic',     ph: 'sk-ant-…',   hint: 'console.anthropic.com' },
  { value: 'gemini',     label: 'Google Gemini', ph: 'AIzaSy…',    hint: 'aistudio.google.com' },
];

const MAX_SLOTS = 5;

// In-memory state: array of {provider, api_key, model}
let _slots = [];

// ─────────────────────────────────────────────────────────────────────────────
// MODULE INIT
// ─────────────────────────────────────────────────────────────────────────────

export function init(register) {
  // ── Event delegation on the page container ────────────────────────────────
  // Using delegation (rather than getElementById at boot-time) means the
  // listener is always active regardless of caching or module-load timing.
  document.getElementById('page-settings')?.addEventListener('click', (e) => {
    const btn = e.target.closest('button');
    if (!btn) return;
    switch (btn.id) {
      case 'save-settings-btn':   saveSettings();  break;
      case 'add-llm-slot-btn':    addSlot();       break;
      case 'add-account-btn':     addAccount();    break;
      case 'detect-provider-btn': detectProvider(); break;
    }
  });

  // ── Input/change listeners (don't bubble in a useful way via delegation) ──
  document.getElementById('acc-provider')?.addEventListener('change', (e) => updateProviderHint(e.target.value));
  document.getElementById('acc-email')?.addEventListener('input',     (e) => autoDetect(e.target.value));

  register('settings', {
    onEnter: loadSettings,
    onLeave: () => {},
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// LOAD
// ─────────────────────────────────────────────────────────────────────────────

async function loadSettings() {
  updateProviderHint(document.getElementById('acc-provider')?.value || 'gmail');
  try {
    const s = await settingsAPI.get();

    // LLM provider slots
    if (Array.isArray(s.llm_providers) && s.llm_providers.length > 0) {
      _slots = s.llm_providers.map((p) => ({
        provider: p.provider || 'groq',
        api_key:  p.api_key  || '',
        model:    p.model    || '',
      }));
    } else if (s.groq_key || s.openrouter_key) {
      // Migrate legacy individual keys into slot format
      _slots = [];
      if (s.groq_key)       _slots.push({ provider: 'groq',       api_key: s.groq_key,       model: '' });
      if (s.openrouter_key) _slots.push({ provider: 'openrouter', api_key: s.openrouter_key, model: s.openrouter_model || '' });
    } else {
      _slots = [];
    }
    renderSlots();

    if (s.apollo_key) setVal('st-apollo-key', s.apollo_key);
    if (s.batch_size) setVal('st-daily-limit', s.batch_size);
  } catch (e) {
    toast('Could not load settings: ' + e.message, 'error');
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// SLOT RENDERING  — pure DOM construction, no innerHTML for inputs
// ─────────────────────────────────────────────────────────────────────────────

function providerDef(name) {
  return LLM_PROVIDERS.find((p) => p.value === name) || LLM_PROVIDERS[0];
}

function _makeSelect(idx, currentProvider) {
  const sel = document.createElement('select');
  sel.className = 'slot-provider';
  sel.dataset.idx = String(idx);
  sel.style.cssText = 'width:130px;flex-shrink:0;font-size:0.8rem;';
  LLM_PROVIDERS.forEach((p) => {
    const opt = document.createElement('option');
    opt.value = p.value;
    opt.textContent = p.label;
    if (p.value === currentProvider) opt.selected = true;
    sel.appendChild(opt);
  });
  return sel;
}

function _makeInput(type, idx, cls, placeholder, value) {
  const inp = document.createElement('input');
  inp.type = type;
  inp.dataset.idx = String(idx);
  inp.className = cls;
  inp.placeholder = placeholder;
  inp.value = value || '';
  inp.style.cssText = 'flex:1;min-width:0;font-size:0.8rem;';
  if (type === 'password') inp.autocomplete = 'off';
  return inp;
}

function _makeBtn(label, title, extraStyle) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'btn btn--ghost btn--sm';
  btn.textContent = label;
  btn.title = title || '';
  btn.style.cssText = 'flex-shrink:0;padding:5px 9px;font-size:0.75rem;' + (extraStyle || '');
  return btn;
}

function renderSlots() {
  const container = document.getElementById('llm-slots-container');
  if (!container) return;

  // Clear previous content
  while (container.firstChild) container.removeChild(container.firstChild);

  const addBtn = document.getElementById('add-llm-slot-btn');

  if (_slots.length === 0) {
    const msg = document.createElement('p');
    msg.style.cssText = 'font-size:0.8rem;color:var(--muted-2);padding:4px 0;margin:0;';
    msg.innerHTML = 'No providers yet. Click <strong>+ Add Provider</strong> above.';
    container.appendChild(msg);
    if (addBtn) addBtn.style.display = '';
    return;
  }

  _slots.forEach((slot, i) => {
    const def = providerDef(slot.provider);

    // ── Outer wrapper ──────────────────────────────────────────────────────
    const wrap = document.createElement('div');
    wrap.dataset.slotIndex = String(i);
    wrap.style.cssText = 'margin-bottom:12px;border:1px solid var(--border,#e5e7eb);border-radius:8px;padding:10px 12px;';

    // ── Row 1: badge | provider select | api key | remove ─────────────────
    const row1 = document.createElement('div');
    row1.style.cssText = 'display:flex;align-items:center;gap:6px;';

    const badge = document.createElement('span');
    badge.style.cssText = 'min-width:20px;font-size:0.7rem;font-weight:700;color:var(--muted-2);text-align:center;flex-shrink:0;';
    badge.textContent = String(i + 1);
    row1.appendChild(badge);

    const sel = _makeSelect(i, slot.provider);
    row1.appendChild(sel);

    const keyInp = _makeInput('password', i, 'slot-key', def.ph, slot.api_key);
    row1.appendChild(keyInp);

    const removeBtn = _makeBtn('✕', 'Remove this provider', 'color:var(--danger,#ef4444);');
    row1.appendChild(removeBtn);
    wrap.appendChild(row1);

    // ── Row 2: model name | test button | status ───────────────────────────
    const row2 = document.createElement('div');
    row2.style.cssText = 'display:flex;align-items:center;gap:6px;margin-top:8px;';

    const modelInp = _makeInput('text', i, 'slot-model', 'Model name  (e.g. llama-3.3-70b-versatile)', slot.model);
    row2.appendChild(modelInp);

    const testBtn = _makeBtn('🔌 Test', 'Verify this API key + model works');
    row2.appendChild(testBtn);

    const statusEl = document.createElement('span');
    statusEl.style.cssText = 'font-size:0.72rem;flex-shrink:0;white-space:nowrap;';
    row2.appendChild(statusEl);
    wrap.appendChild(row2);

    // ── Hint line ──────────────────────────────────────────────────────────
    const hintEl = document.createElement('p');
    hintEl.style.cssText = 'font-size:0.71rem;color:var(--muted-2);margin:5px 0 0;';
    hintEl.textContent = 'API key from ' + def.hint;
    wrap.appendChild(hintEl);

    container.appendChild(wrap);

    // ── Wire events (closures capture the live DOM elements) ───────────────
    sel.addEventListener('change', () => {
      _slots[i].provider = sel.value;
      const d = providerDef(sel.value);
      keyInp.placeholder = d.ph;
      hintEl.textContent = 'API key from ' + d.hint;
    });

    keyInp.addEventListener('input', () => { _slots[i].api_key = keyInp.value; });
    modelInp.addEventListener('input', () => { _slots[i].model  = modelInp.value; });

    removeBtn.addEventListener('click', () => {
      _slots.splice(i, 1);
      renderSlots();
    });

    testBtn.addEventListener('click', () => testSlot(i, testBtn, statusEl, keyInp, modelInp, sel));
  });

  if (addBtn) addBtn.style.display = _slots.length >= MAX_SLOTS ? 'none' : '';
}

function addSlot() {
  if (_slots.length >= MAX_SLOTS) {
    toast('Maximum ' + MAX_SLOTS + ' provider slots allowed', 'warning');
    return;
  }
  _slots.push({ provider: 'groq', api_key: '', model: '' });
  renderSlots();
  // Focus the new slot's key input
  const allKeys = document.querySelectorAll('#llm-slots-container .slot-key');
  if (allKeys.length) allKeys[allKeys.length - 1].focus();
}

// ─────────────────────────────────────────────────────────────────────────────
// TEST CONNECTION
// ─────────────────────────────────────────────────────────────────────────────

async function testSlot(idx, btn, statusEl, keyInp, modelInp, selEl) {
  // Sync DOM → state first
  _slots[idx].api_key  = keyInp.value.trim();
  _slots[idx].model    = modelInp.value.trim();
  _slots[idx].provider = selEl.value;

  const slot = _slots[idx];
  if (!slot.api_key) {
    toast('Enter an API key first', 'warning');
    return;
  }

  const orig = btn.textContent;
  btn.disabled = true;
  btn.textContent = '…';
  statusEl.textContent = '';
  statusEl.style.color = '';

  try {
    const res = await settingsAPI.testLLM({
      provider: slot.provider,
      api_key:  slot.api_key,
      model:    slot.model || '',
    });
    if (res.ok) {
      statusEl.textContent = '✓ Connected';
      statusEl.style.color = 'var(--success,#10b981)';
      toast('✓ ' + slot.provider + ' connected' + (res.model_used ? ' · ' + res.model_used : ''), 'success');
    } else {
      statusEl.textContent = '✗ Failed';
      statusEl.style.color = 'var(--danger,#ef4444)';
      toast(slot.provider + ' failed: ' + (res.error || 'Unknown error'), 'error');
    }
  } catch (e) {
    statusEl.textContent = '✗ Error';
    statusEl.style.color = 'var(--danger,#ef4444)';
    toast('Test error: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = orig;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// SAVE
// ─────────────────────────────────────────────────────────────────────────────

async function saveSettings() {
  const btn = document.getElementById('save-settings-btn');
  btn.innerHTML = '<span class="spinner"></span> Saving…';
  btn.disabled = true;

  // Sync any typed-but-not-event-fired values from DOM → _slots
  const container = document.getElementById('llm-slots-container');
  if (container) {
    container.querySelectorAll('[data-slot-index]').forEach((wrap) => {
      const i      = +wrap.dataset.slotIndex;
      if (_slots[i] === undefined) return;
      const selEl  = wrap.querySelector('.slot-provider');
      const keyEl  = wrap.querySelector('.slot-key');
      const modEl  = wrap.querySelector('.slot-model');
      if (selEl) _slots[i].provider = selEl.value;
      if (keyEl) _slots[i].api_key  = keyEl.value.trim();
      if (modEl) _slots[i].model    = modEl.value.trim();
    });
  }

  const validSlots = _slots.filter((s) => s.api_key.trim());
  const body = { llm_providers: validSlots };

  const apollo = getVal('st-apollo-key');
  const limit  = getVal('st-daily-limit');
  if (apollo) body.apollo_key = apollo;
  if (limit)  body.batch_size = parseInt(limit);

  try {
    await settingsAPI.update(body);
    toast('✓ Saved — ' + validSlots.length + ' LLM provider' + (validSlots.length !== 1 ? 's' : '') + ' active', 'success');
  } catch (e) {
    toast('Save failed: ' + e.message, 'error');
  } finally {
    btn.innerHTML = 'Save Settings';
    btn.disabled  = false;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// EMAIL ACCOUNTS
// ─────────────────────────────────────────────────────────────────────────────

async function addAccount() {
  const email    = getVal('acc-email').trim();
  const password = getVal('acc-password').trim();
  const name     = getVal('acc-name').trim();
  const provider = getVal('acc-provider');

  if (!email || !password) { toast('Email and password are required', 'warning'); return; }

  const btn = document.getElementById('add-account-btn');
  btn.innerHTML = '<span class="spinner"></span> Adding…';
  btn.disabled  = true;

  try {
    await accountsAPI.add({ email, app_password: password, display_name: name, provider });
    toast('✓ ' + email + ' added (' + provider + ')', 'success');
    setVal('acc-email', '');
    setVal('acc-password', '');
    setVal('acc-name', '');
  } catch (e) {
    toast(e.message, 'error');
  } finally {
    btn.innerHTML = '+ Add Account';
    btn.disabled  = false;
  }
}

function updateProviderHint(provider) {
  const hint    = document.getElementById('provider-hint');
  const passInp = document.getElementById('acc-password');
  const label   = document.getElementById('acc-pass-label');

  const hints = {
    resend:  { label: 'Resend API Key (starts with re_)', ph: 're_xxxx…',            html: '⚡ Get at <a href="https://resend.com/api-keys" target="_blank">resend.com/api-keys</a>. Verify your sender domain for best deliverability.' },
    gmail:   { label: 'Gmail App Password (16 chars)',    ph: 'xxxx xxxx xxxx xxxx', html: '📧 Get at <a href="https://myaccount.google.com/apppasswords" target="_blank">myaccount.google.com/apppasswords</a>. Requires 2FA enabled.' },
    m365:    { label: 'M365 App Password (16 chars)',     ph: 'xxxx xxxx xxxx xxxx', html: '🏢 Microsoft 365 uses <strong>smtp.office365.com:587</strong>. Get App Password at <a href="https://mysignins.microsoft.com/security-info" target="_blank">mysignins.microsoft.com</a>.' },
    outlook: { label: 'Outlook App Password (16 chars)',  ph: 'xxxx xxxx xxxx xxxx', html: '📬 Outlook Personal uses <strong>smtp-mail.outlook.com:587</strong>. Get App Password at <a href="https://mysignins.microsoft.com/security-info" target="_blank">mysignins.microsoft.com</a>.' },
    smtp:    { label: 'SMTP Password',                   ph: 'your SMTP password',   html: '⚙️ Provide your SMTP server password. Make sure SMTP/SSL is enabled on your mail host.' },
  };
  const h = hints[provider] || hints.outlook;
  if (passInp) passInp.placeholder = h.ph;
  if (hint)    hint.innerHTML = h.html;
  if (label) {
    const tn = [...label.childNodes].find((n) => n.nodeType === Node.TEXT_NODE);
    if (tn) tn.nodeValue = h.label;
  }
}

function autoDetect(email) {
  if (!email.includes('@')) return;
  const domain = email.split('@')[1]?.toLowerCase() || '';
  const sel = document.getElementById('acc-provider');
  if (!sel) return;
  if (['gmail.com', 'googlemail.com'].includes(domain))                              { sel.value = 'gmail';   updateProviderHint('gmail');   }
  else if (['outlook.com', 'hotmail.com', 'live.com', 'msn.com'].includes(domain))  { sel.value = 'outlook'; updateProviderHint('outlook'); }
}

async function detectProvider() {
  const email = getVal('acc-email').trim();
  if (!email || !email.includes('@')) { toast('Enter an email first', 'warning'); return; }
  try {
    const r   = await accountsAPI.detect(email);
    const sel = document.getElementById('acc-provider');
    if (sel) { sel.value = r.provider; updateProviderHint(r.provider); }
    toast('Detected: ' + (r.label || r.provider), 'info');
  } catch (e) {
    toast('Could not detect provider: ' + e.message, 'warning');
  }
}
