/**
 * pages/persona.js — Brand Identity profile + AI Knowledge Base pillars
 */
import { setupAPI } from '../api.js';
import { esc, getVal, setVal, applyBranding } from '../utils.js';
import { toast } from '../toast.js';

export function init(register) {
  document.getElementById('add-pillar-btn')?.addEventListener('click', () => addPillar());
  document.getElementById('save-persona-btn')?.addEventListener('click', savePersona);

  register('persona', {
    onEnter: loadPersona,
    onLeave: () => {},
  });
}

async function loadPersona() {
  try {
    const data = await setupAPI.get();
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

  try {
    await setupAPI.save({ profile, knowledge_base });
    toast('Identity saved & embedded to KnowledgeBase', 'success');
    // Apply brand colour live
    applyBranding(profile);
    // Hide onboarding banner
    const banner = document.getElementById('onboarding-banner');
    if (banner) banner.style.display = 'none';
  } catch (e) {
    toast('Save failed: ' + e.message, 'error');
  } finally {
    btn.innerHTML = 'Save Identity & Embed KnowledgeBase';
    btn.disabled  = false;
  }
}
