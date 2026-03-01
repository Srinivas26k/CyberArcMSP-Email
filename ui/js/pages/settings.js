/**
 * pages/settings.js — API keys, email defaults, add sender account
 */
import { settingsAPI, accountsAPI } from '../api.js';
import { esc, getVal, setVal } from '../utils.js';
import { toast } from '../toast.js';

export function init(register) {
  document.getElementById('save-settings-btn')?.addEventListener('click',   saveSettings);
  document.getElementById('add-account-btn')?.addEventListener('click',     addAccount);
  document.getElementById('acc-provider')?.addEventListener('change',       (e) => updateProviderHint(e.target.value));
  document.getElementById('acc-email')?.addEventListener('input',           (e) => autoDetect(e.target.value));
  document.getElementById('detect-provider-btn')?.addEventListener('click', detectProvider);

  register('settings', {
    onEnter: loadSettings,
    onLeave: () => {},
  });
}

async function loadSettings() {
  updateProviderHint(document.getElementById('acc-provider')?.value || 'gmail');
  try {
    const s = await settingsAPI.get();
    if (s.apollo_key)       setVal('st-apollo-key', s.apollo_key);
    if (s.openrouter_key)   setVal('st-openai-key', s.openrouter_key);
    else if (s.groq_key)    setVal('st-openai-key', s.groq_key);
    if (s.openrouter_model) setVal('st-model',      s.openrouter_model);
    if (s.batch_size)       setVal('st-daily-limit', s.batch_size);
  } catch (e) {
    toast('Could not load settings: ' + e.message, 'error');
  }
}

async function saveSettings() {
  const btn = document.getElementById('save-settings-btn');
  btn.innerHTML = '<span class="spinner"></span> Saving…';
  btn.disabled = true;

  const body   = {};
  const apollo = getVal('st-apollo-key');
  const llmKey = getVal('st-openai-key');
  const model  = getVal('st-model');
  const limit  = getVal('st-daily-limit');

  if (apollo)  body.apollo_key       = apollo;
  if (llmKey)  body.openrouter_key   = llmKey;
  if (model)   body.openrouter_model = model;
  if (limit)   body.batch_size       = parseInt(limit);

  try {
    await settingsAPI.update(body);
    toast('Settings saved', 'success');
  } catch (e) {
    toast('Save failed: ' + e.message, 'error');
  } finally {
    btn.innerHTML = 'Save Settings';
    btn.disabled = false;
  }
}

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
