/**
 * pages/settings.js — LLM provider slots, API keys, email defaults, sender accounts
 */
import { settingsAPI, accountsAPI } from '../api.js';
import { esc, getVal, setVal } from '../utils.js';
import { toast } from '../toast.js';

// ─────────────────────────────────────────────────────────────────────────────
// LLM PROVIDER CONFIG  (dropdown options + key placeholder hints only)
// ─────────────────────────────────────────────────────────────────────────────

const LLM_PROVIDERS = [
  { value: 'groq',       label: 'Groq',         ph: 'gsk_…',       hint: 'console.groq.com' },
  { value: 'openrouter', label: 'OpenRouter',    ph: 'sk-or-v1-…',  hint: 'openrouter.ai/keys' },
  { value: 'openai',     label: 'OpenAI',        ph: 'sk-proj-…',   hint: 'platform.openai.com/api-keys' },
  { value: 'anthropic',  label: 'Anthropic',     ph: 'sk-ant-…',    hint: 'console.anthropic.com' },
  { value: 'gemini',     label: 'Google Gemini', ph: 'AIzaSy…',     hint: 'aistudio.google.com' },
];

const MAX_SLOTS = 5;

// In-memory state: array of {provider, api_key, model}
let _slots = [];

// ─────────────────────────────────────────────────────────────────────────────
// MODULE INIT
// ─────────────────────────────────────────────────────────────────────────────

export function init(register) {
  document.getElementById('save-settings-btn')?.addEventListener('click',   saveSettings);
  document.getElementById('add-llm-slot-btn')?.addEventListener('click',    addSlot);
  document.getElementById('add-account-btn')?.addEventListener('click',     addAccount);
  document.getElementById('acc-provider')?.addEventListener('change',       (e) => updateProviderHint(e.target.value));
  document.getElementById('acc-email')?.addEventListener('input',           (e) => autoDetect(e.target.value));
  document.getElementById('detect-provider-btn')?.addEventListener('click', detectProvider);

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
      // Migrate legacy individual keys
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
// SLOT RENDERING  (pure DOM construction — no innerHTML for form elements)
// ─────────────────────────────────────────────────────────────────────────────

function providerDef(name) {
  return LLM_PROVIDERS.find((p) => p.value === name) || LLM_PROVIDERS[0];
}

function _makeSelect(idx, currentProvider) {
  const sel = document.createElement('select');
  sel.className = 'slot-provider';
  sel.dataset.idx = idx;
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

function _makeInput(type, idx, cls, placeholder, value, extraStyle) {
  const inp = document.createElement('input');
  inp.type = type;
  inp.dataset.idx = idx;
  inp.className = cls;
  inp.placeholder = placeholder;
  inp.value = value || '';
  inp.style.cssText = (extraStyle || '') + ';flex:1;min-width:0;font-size:0.8rem;';
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
  container.innerHTML = '';

  const addBtn = document.getElementById('add-llm-slot-btn');

  if (_slots.length === 0) {
    const msg = document.createElement('p');
    msg.style.cssText = 'font-size:0.8rem;color:var(--muted-2);padding:4px 0;margin:0;';
    msg.innerHTML = 'No providers yet. Click <strong>+ Add Provider</strong> to add one.';
    container.appendChild(msg);
    if (addBtn) addBtn.style.display = '';
    return;
  }

  _slots.forEach((slot, i) => {
    const def = providerDef(slot.provider);

    // Wrapper row
    const wrap = document.createElement('div');
    wrap.dataset.slotIndex = String(i);
    wrap.style.cssText = 'margin-bottom:10px;';

    // Top row: number | provider | api key | ✕
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:6px;';

    // Slot number badge
    const badge = document.createElement('span');
    badge.style.cssText = 'min-width:18px;font-size:0.7rem;font-weight:700;color:var(--muted-2);text-align:center;flex-shrink:0;';
    badge.textContent = String(i + 1);
    row.appendChild(badge);

    // Provider dropdown
    const sel = _makeSelect(i, slot.provider);
    sel.addEventListener('change', (e) => {
      _slots[i].provider = e.target.value;
      const d = providerDef(e.target.value);
      keyInp.placeholder = d.ph;
      hintEl.textContent = 'API key from ' + d.hint;
    });
    row.appendChild(sel);

    // API key input
    const keyInp = _makeInput('password', i, 'slot-key', def.ph, slot.api_key, '');
    keyInp.addEventListener('input', (e) => { _slots[i].api_key = e.target.value; });
    row.appendChild(keyInp);

    // Remove button
    const removeBtn = _makeBtn('✕', 'Remove this provider', 'color:var(--danger,#ef4444);');
    removeBtn.addEventListener('click', () => {
      _slots.splice(i, 1);
      renderSlots();
    });
    row.appendChild(removeBtn);
    wrap.appendChild(row);

    // Bottom row: model input + Test button
    const row2 = document.createElement('div');
    row2.style.cssText = 'display:flex;align-items:center;gap:6px;margin-top:5px;padding-left:24px;';

    const modelInp = _makeInput('text', i, 'slot-model',
      'Model name  (e.g. llama-3.3-70b-versatile)', slot.model, '');
    modelInp.addEventListener('input', (e) => { _slots[i].model = e.target.value; });
    row2.appendChild(modelInp);

    // Test connection button
    const testBtn = _makeBtn('🔌 Test', 'Verify this API key + model works');
    testBtn.addEventListener('click', () => testSlot(i, testBtn));
    row2.appendChild(testBtn);

    // Status indicator
    const statusEl = document.createElement('span');
    statusEl.className = 'slot-status-' + i;
    statusEl.style.cssText = 'font-size:0.72rem;flex-shrink:0;';
    row2.appendChild(statusEl);

    wrap.appendChild(row2);

    // Hint line
    const hintEl = document.createElement('p');
    hintEl.style.cssText = 'font-size:0.71rem;color:var(--muted-2);margin:3px 0 0 24px;';
    hintEl.textContent = 'API key from ' + def.hint;
    wrap.appendChild(hintEl);

    container.appendChild(wrap);
  });

  // Show/hide "+ Add Provider" based on limit
  if (addBtn) addBtn.style.display = _slots.length >= MAX_SLOTS ? 'none' : '';
}

function addSlot() {
  if (_slots.length >= MAX_SLOTS) {
    toast(`Maximum ${MAX_SLOTS} provider slots allowed`, 'warning');
    return;
  }
  _slots.push({ provider: 'groq', api_key: '', model: '' });
  renderSlots();
  // Focus the new key input
  const inputs = document.querySelectorAll('#llm-slots-container .slot-key');
  if (inputs.length) inputs[inputs.length - 1].focus();
}

// ─────────────────────────────────────────────────────────────────────────────
// TEST CONNECTION
// ─────────────────────────────────────────────────────────────────────────────

async function testSlot(idx, btn) {
  const slot = _slots[idx];

  // Collect latest values from DOM in case user hasn't triggered input events
  const container = document.getElementById('llm-slots-container');
  const wrap = container?.querySelector(`[data-slot-index="${idx}"]`);
  if (wrap) {
    const keyEl = wrap.querySelector('.slot-key');
    const modEl = wrap.querySelector('.slot-model');
    if (keyEl) slot.api_key = keyEl.value.trim();
    if (modEl) slot.model   = modEl.value.trim();
  }

  if (!slot.api_key) {
    toast('Enter an API key first', 'warning');
    return;
  }

  const statusEl = document.querySelector(`.slot-status-${idx}`);
  const orig = btn.textContent;
  btn.disabled = true;
  btn.textContent = '…';
  if (statusEl) { statusEl.textContent = ''; statusEl.style.color = ''; }

  try {
    const res = await settingsAPI.testLLM({
      provider: slot.provider,
      api_key:  slot.api_key,
      model:    slot.model || '',
    });
    if (res.ok) {
      if (statusEl) { statusEl.textContent = '✓ Connected'; statusEl.style.color = 'var(--success, #10b981)'; }
      toast(`✓ ${slot.provider} connected${res.model_used ? ' · ' + res.model_used : ''}`, 'success');
    } else {
      if (statusEl) { statusEl.textContent = '✗ Failed'; statusEl.style.color = 'var(--danger, #ef4444)'; }
      toast(`${slot.provider} test failed: ${res.error || 'Unknown error'}`, 'error');
    }
  } catch (e) {
    if (statusEl) { statusEl.textContent = '✗ Error'; statusEl.style.color = 'var(--danger, #ef4444)'; }
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

  // Collect latest DOM values (covers any typing without input events firing)
  const container = document.getElementById('llm-slots-container');
  if (container) {
    container.querySelectorAll('[data-slot-index]').forEach((wrap) => {
      const i = +wrap.dataset.slotIndex;
      if (_slots[i] === undefined) return;
      const selEl = wrap.querySelector('.slot-provider');
      const keyEl = wrap.querySelector('.slot-key');
      const modEl = wrap.querySelector('.slot-model');
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
    toast(`✓ Saved — ${validSlots.length} LLM provider${validSlots.length !== 1 ? 's' : ''} active`, 'success');
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
    toast(`✓ ${email} added (${provider})`, 'success');
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
  if (['gmail.com', 'googlemail.com'].includes(domain))                           { sel.value = 'gmail';   updateProviderHint('gmail');   }
  else if (['outlook.com', 'hotmail.com', 'live.com', 'msn.com'].includes(domain)) { sel.value = 'outlook'; updateProviderHint('outlook'); }
}

async function detectProvider() {
  const email = getVal('acc-email').trim();
  if (!email || !email.includes('@')) { toast('Enter an email first', 'warning'); return; }
  try {
    const r   = await accountsAPI.detect(email);
    const sel = document.getElementById('acc-provider');
    if (sel) { sel.value = r.provider; updateProviderHint(r.provider); }
    toast(`Detected: ${r.label || r.provider}`, 'info');
  } catch (e) {
    toast('Could not detect provider: ' + e.message, 'warning');
  }
}


// ─────────────────────────────────────────────────────────────────────────────
// LLM PROVIDER SLOT CONFIG
// ─────────────────────────────────────────────────────────────────────────────

const LLM_PROVIDERS = [
  { value: 'groq',       label: 'Groq',           ph: 'gsk_…',           defaultModel: 'llama-3.3-70b-versatile' },
  { value: 'openrouter', label: 'OpenRouter',      ph: 'sk-or-v1-…',     defaultModel: 'meta-llama/llama-3.3-70b-instruct:free' },
  { value: 'openai',     label: 'OpenAI',          ph: 'sk-proj-…',      defaultModel: 'gpt-4o-mini' },
  { value: 'anthropic',  label: 'Anthropic',       ph: 'sk-ant-…',       defaultModel: 'claude-3-5-haiku-20241022' },
  { value: 'gemini',     label: 'Google Gemini',   ph: 'AIzaSy…',        defaultModel: 'gemini-1.5-flash' },
];

const MAX_SLOTS = 5;

// In-memory state: array of {provider, api_key, model}
let _slots = [];

// ─────────────────────────────────────────────────────────────────────────────
// MODULE INIT
// ─────────────────────────────────────────────────────────────────────────────

export function init(register) {
  document.getElementById('save-settings-btn')?.addEventListener('click',   saveSettings);
  document.getElementById('add-llm-slot-btn')?.addEventListener('click',    addSlot);
  document.getElementById('add-account-btn')?.addEventListener('click',     addAccount);
  document.getElementById('acc-provider')?.addEventListener('change',       (e) => updateProviderHint(e.target.value));
  document.getElementById('acc-email')?.addEventListener('input',           (e) => autoDetect(e.target.value));
  document.getElementById('detect-provider-btn')?.addEventListener('click', detectProvider);

  register('settings', {
    onEnter: loadSettings,
    onLeave: () => {},
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// LOAD  (called each time the Settings page is opened)
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

    // Apollo + email defaults
    if (s.apollo_key)    setVal('st-apollo-key',   s.apollo_key);
    if (s.batch_size)    setVal('st-daily-limit',   s.batch_size);
  } catch (e) {
    toast('Could not load settings: ' + e.message, 'error');
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// SLOT RENDERING
// ─────────────────────────────────────────────────────────────────────────────

function providerDef(name) {
  return LLM_PROVIDERS.find((p) => p.value === name) || LLM_PROVIDERS[0];
}

function renderSlots() {
  const container = document.getElementById('llm-slots-container');
  if (!container) return;
  container.innerHTML = '';

  if (_slots.length === 0) {
    container.innerHTML = '<p style="font-size:0.8rem;color:var(--muted-2);padding:4px 0;">No providers added yet. Click <strong>+ Add Provider</strong> to add one.</p>';
    return;
  }

  _slots.forEach((slot, i) => {
    const def = providerDef(slot.provider);
    const options = LLM_PROVIDERS.map((p) =>
      `<option value="${p.value}"${p.value === slot.provider ? ' selected' : ''}>${p.label}</option>`
    ).join('');

    const row = document.createElement('div');
    row.style.cssText = 'display:flex;align-items:center;gap:8px;margin-bottom:10px;';
    row.dataset.slotIndex = i;
    row.innerHTML = `
      <span style="min-width:20px;font-size:0.75rem;font-weight:700;color:var(--muted-2);text-align:center;">${i + 1}</span>
      <select class="slot-provider" data-idx="${i}" style="width:140px;flex-shrink:0;">${options}</select>
      <input class="slot-key" type="password" data-idx="${i}"
             placeholder="${esc(def.ph)}" value="${esc(slot.api_key)}"
             autocomplete="off" style="flex:1;min-width:0;" />
      <input class="slot-model" type="text" data-idx="${i}"
             placeholder="Model (blank = ${esc(def.defaultModel)})" value="${esc(slot.model)}"
             style="flex:1;min-width:0;" />
      <button class="btn btn--ghost btn--sm slot-remove" data-idx="${i}"
              title="Remove slot" style="flex-shrink:0;padding:5px 9px;">✕</button>
    `;
    container.appendChild(row);
  });

  // Wire events
  container.querySelectorAll('.slot-provider').forEach((sel) => {
    sel.addEventListener('change', (e) => {
      const idx = +e.target.dataset.idx;
      _slots[idx].provider = e.target.value;
      const d = providerDef(e.target.value);
      const keyInp = container.querySelector(`.slot-key[data-idx="${idx}"]`);
      const modInp = container.querySelector(`.slot-model[data-idx="${idx}"]`);
      if (keyInp) keyInp.placeholder = d.ph;
      if (modInp) modInp.placeholder = `Model (blank = ${d.defaultModel})`;
    });
  });

  container.querySelectorAll('.slot-key').forEach((inp) => {
    inp.addEventListener('input', (e) => { _slots[+e.target.dataset.idx].api_key = e.target.value; });
  });

  container.querySelectorAll('.slot-model').forEach((inp) => {
    inp.addEventListener('input', (e) => { _slots[+e.target.dataset.idx].model = e.target.value; });
  });

  container.querySelectorAll('.slot-remove').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      _slots.splice(+e.target.dataset.idx, 1);
      renderSlots();
    });
  });

  // Show/hide the "+ Add Provider" button based on limit
  const addBtn = document.getElementById('add-llm-slot-btn');
  if (addBtn) addBtn.style.display = _slots.length >= MAX_SLOTS ? 'none' : '';
}

function addSlot() {
  if (_slots.length >= MAX_SLOTS) {
    toast(`Maximum ${MAX_SLOTS} provider slots allowed`, 'warning');
    return;
  }
  _slots.push({ provider: 'groq', api_key: '', model: '' });
  renderSlots();
  // Focus the new key input
  const inputs = document.querySelectorAll('#llm-slots-container .slot-key');
  inputs[inputs.length - 1]?.focus();
}

// ─────────────────────────────────────────────────────────────────────────────
// SAVE
// ─────────────────────────────────────────────────────────────────────────────

async function saveSettings() {
  const btn = document.getElementById('save-settings-btn');
  btn.innerHTML = '<span class="spinner"></span> Saving…';
  btn.disabled = true;

  // Collect latest values from DOM (in case user typed without triggering input events)
  const container = document.getElementById('llm-slots-container');
  if (container) {
    container.querySelectorAll('[data-slot-index]').forEach((row) => {
      const i       = +row.dataset.slotIndex;
      const selEl   = row.querySelector('.slot-provider');
      const keyEl   = row.querySelector('.slot-key');
      const modEl   = row.querySelector('.slot-model');
      if (_slots[i] !== undefined) {
        if (selEl) _slots[i].provider = selEl.value;
        if (keyEl) _slots[i].api_key  = keyEl.value.trim();
        if (modEl) _slots[i].model    = modEl.value.trim();
      }
    });
  }

  const body = {};

  // LLM providers — only include slots that have an api_key
  const validSlots = _slots.filter((s) => s.api_key.trim());
  body.llm_providers = validSlots;

  // Apollo + email defaults
  const apollo = getVal('st-apollo-key');
  const limit  = getVal('st-daily-limit');
  if (apollo) body.apollo_key  = apollo;
  if (limit)  body.batch_size  = parseInt(limit);

  try {
    await settingsAPI.update(body);
    toast(`✓ Settings saved (${validSlots.length} LLM provider${validSlots.length !== 1 ? 's' : ''})`, 'success');
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
    toast(`✓ ${email} added (${provider})`, 'success');
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
    resend:  { label: 'Resend API Key (starts with re_)', ph: 're_xxxx…',  html: '⚡ Get at <a href="https://resend.com/api-keys" target="_blank">resend.com/api-keys</a>. Verify your sender domain for best deliverability.' },
    gmail:   { label: 'Gmail App Password (16 chars)',   ph: 'xxxx xxxx xxxx xxxx', html: '📧 Get at <a href="https://myaccount.google.com/apppasswords" target="_blank">myaccount.google.com/apppasswords</a>. Requires 2FA enabled.' },
    m365:    { label: 'M365 App Password (16 chars)',    ph: 'xxxx xxxx xxxx xxxx', html: '🏢 Microsoft 365 uses <strong>smtp.office365.com:587</strong>. Get App Password at <a href="https://mysignins.microsoft.com/security-info" target="_blank">mysignins.microsoft.com</a>.' },
    outlook: { label: 'Outlook App Password (16 chars)', ph: 'xxxx xxxx xxxx xxxx', html: '📬 Outlook Personal uses <strong>smtp-mail.outlook.com:587</strong>. Get App Password at <a href="https://mysignins.microsoft.com/security-info" target="_blank">mysignins.microsoft.com</a>.' },
    smtp:    { label: 'SMTP Password',                  ph: 'your SMTP password',   html: '⚙️ Provide your SMTP server password. Make sure SMTP/SSL is enabled on your mail host.' },
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
  if (['gmail.com', 'googlemail.com'].includes(domain)) { sel.value = 'gmail'; updateProviderHint('gmail'); }
  else if (['outlook.com', 'hotmail.com', 'live.com', 'msn.com'].includes(domain)) { sel.value = 'outlook'; updateProviderHint('outlook'); }
}

async function detectProvider() {
  const email = getVal('acc-email').trim();
  if (!email || !email.includes('@')) { toast('Enter an email first', 'warning'); return; }
  try {
    const r   = await accountsAPI.detect(email);
    const sel = document.getElementById('acc-provider');
    if (sel) { sel.value = r.provider; updateProviderHint(r.provider); }
    toast(`Detected: ${r.label || r.provider}`, 'info');
  } catch (e) {
    toast('Could not detect provider: ' + e.message, 'warning');
  }
}
