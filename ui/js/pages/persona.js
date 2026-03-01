/**
 * pages/persona.js — Brand Identity profile + AI Knowledge Base pillars + Email Template editor
 */
import { setupAPI, settingsAPI } from '../api.js';
import { esc, getVal, setVal, applyBranding } from '../utils.js';
import { toast } from '../toast.js';

// ── Sample data injected into template preview ─────────────────────────────
const PREVIEW_SAMPLE = {
  BODY: `<p>Hi Jane,</p>
<p>As a rapidly scaling design agency, DesignCo faces increasing pressure to modernise its infrastructure without disrupting active client deliveries.</p>
<p>Here's how Acme Corp supports Creative & Design agencies like DesignCo:</p>
<ul>
  <li><strong>Cloud Migration —</strong> Zero-downtime lift-and-shift to AWS, typically cutting infra costs by 40%.</li>
  <li><strong>AI Automation —</strong> Automate repetitive workflows, freeing your team for high-value creative work.</li>
  <li><strong>DevSecOps CI/CD —</strong> Ship updates faster with security gates baked into every deployment pipeline.</li>
</ul>
<p>Beyond these, we also provide Custom SaaS Development & Compliance Advisory.</p>
<p>I'd love to explore how Acme Corp can help DesignCo align technical capabilities with creative ambitions. Let's schedule a conversation to discuss your priorities.</p>
<p>Looking forward to connecting.</p>
<p>Warm regards,</p>`,
  CTA_BUTTON: '<div style="margin:28px auto;text-align:center;"><a href="#" style="display:inline-block;padding:14px 32px;background:#0056b3;color:#ffffff;text-decoration:none;font-weight:700;border-radius:6px;font-size:15px;">&#128197; Book a 15-Minute Strategy Call</a></div>',
  SENDER_NAME:      'Brian Johnson',
  SENDER_TITLE:     'Client Engagement Officer',
  SENDER_EMAIL:     'brian@example.com',
  COMPANY_NAME:     'Acme Corp',
  COMPANY_TAGLINE:  'Enterprise solutions for modern business',
  COMPANY_LOGO:     '',
  COMPANY_WEBSITE:  'https://example.com',
  OFFICES:          'New York • London • Singapore',
  YEAR:             String(new Date().getFullYear()),
};

function _applyPreviewSample(tpl) {
  return tpl.replace(/\{\{([A-Z_]+)\}\}/g, (_, key) => PREVIEW_SAMPLE[key] ?? '');
}

export function init(register) {
  document.getElementById('add-pillar-btn')?.addEventListener('click', () => addPillar());
  document.getElementById('save-persona-btn')?.addEventListener('click', savePersona);

  // Template editor controls
  document.getElementById('tpl-upload')?.addEventListener('change', (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      setVal('p-custom-tpl', ev.target.result);
      toast('Template loaded from file — click Save to apply.', 'success');
    };
    reader.readAsText(file);
    e.target.value = '';
  });

  document.getElementById('tpl-preview-btn')?.addEventListener('click', () => {
    const tpl = getVal('p-custom-tpl').trim();
    if (!tpl) { toast('Enter a template first — or leave blank to use the default.', 'info'); return; }
    const rendered = _applyPreviewSample(tpl);
    const wrap  = document.getElementById('tpl-preview-wrap');
    const frame = document.getElementById('tpl-preview-frame');
    wrap.style.display = 'block';
    frame.srcdoc = rendered;
    wrap.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  document.getElementById('tpl-preview-close')?.addEventListener('click', () => {
    document.getElementById('tpl-preview-wrap').style.display = 'none';
  });

  document.getElementById('tpl-reset-btn')?.addEventListener('click', () => {
    if (!confirm('Clear the custom template and revert to the default branded layout?')) return;
    setVal('p-custom-tpl', '');
    document.getElementById('tpl-preview-wrap').style.display = 'none';
    toast('Custom template cleared — click Save to apply.', 'success');
  });

  register('persona', {
    onEnter: loadPersona,
    onLeave: () => {},
  });
}

async function loadPersona() {
  try {
    const [data, cfg] = await Promise.all([setupAPI.get(), settingsAPI.get()]);
    if (data?.profile) {
      const p = data.profile;
      setVal('p-name',     p.name        || '');
      setVal('p-tagline',  p.tagline     || '');
      setVal('p-website',  p.website     || '');
      setVal('p-logo',     p.logo_url    || '');
      setVal('p-title',    p.sender_title || '');
      setVal('p-calendar', p.calendly_url || '');
      setVal('p-color',    p.primary_color || '#2563EB');
      setVal('p-offices',  p.offices_json  || '[]');
    }
    // Load custom email template
    setVal('p-custom-tpl', cfg?.custom_email_template || '');

    const c = document.getElementById('pillars-container');
    if (!c) return;
    c.innerHTML = '';

    const kbs = data?.knowledge_base || [];
    if (kbs.length > 0) {
      kbs.forEach((kb) => addPillar(kb.title, kb.value_prop));
    } else {
      addPillar('', '');
    }
  } catch (e) {
    toast('Could not load identity profile: ' + e.message, 'error');
  }
}

function addPillar(title = '', prop = '') {
  const c = document.getElementById('pillars-container');
  if (!c) return;
  const div = document.createElement('div');
  div.className = 'pillar-card';
  div.innerHTML = `
    <div class="pillar-card__head">
      <label style="margin:0;font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);">Service / Capability Pillar</label>
      <button class="btn btn--ghost btn--sm" style="color:var(--danger);" onclick="this.closest('.pillar-card').remove()">✕ Remove</button>
    </div>
    <input type="text"     class="kb-title" placeholder="e.g. Cloud Migration"                          value="${esc(title)}">
    <label style="margin-top:8px;">Value Proposition — how does this solve the prospect's problem?</label>
    <textarea class="kb-prop" rows="2" placeholder="e.g. We seamlessly migrate legacy workloads to Azure with zero downtime…">${esc(prop)}</textarea>`;
  c.appendChild(div);
}

async function savePersona() {
  const btn = document.getElementById('save-persona-btn');
  btn.innerHTML = '<span class="spinner"></span> Saving…';
  btn.disabled  = true;

  const profile = {
    name:          getVal('p-name'),
    tagline:       getVal('p-tagline'),
    website:       getVal('p-website'),
    logo_url:      getVal('p-logo'),
    sender_title:  getVal('p-title'),
    calendly_url:  getVal('p-calendar'),
    primary_color: getVal('p-color'),
    offices_json:  getVal('p-offices') || '[]',
  };

  const knowledge_base = [];
  document.querySelectorAll('.pillar-card').forEach((div) => {
    const title = div.querySelector('.kb-title')?.value.trim();
    const prop  = div.querySelector('.kb-prop')?.value.trim();
    if (title && prop) knowledge_base.push({ title, value_prop: prop });
  });

  const customTpl = getVal('p-custom-tpl').trim();

  try {
    await Promise.all([
      setupAPI.save({ profile, knowledge_base }),
      settingsAPI.update({ custom_email_template: customTpl }),
    ]);
    toast('Identity saved & embedded to KnowledgeBase', 'success');
    applyBranding(profile);
    const banner = document.getElementById('onboarding-banner');
    if (banner) banner.style.display = 'none';
  } catch (e) {
    toast('Save failed: ' + e.message, 'error');
  } finally {
    btn.innerHTML = 'Save Identity &amp; Embed KnowledgeBase';
    btn.disabled  = false;
  }
}
