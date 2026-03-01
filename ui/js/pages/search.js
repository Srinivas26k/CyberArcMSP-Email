/**
 * pages/search.js — Apollo lead search with tag inputs
 */
import { leadsAPI } from '../api.js';
import { esc, safeUrl } from '../utils.js';
import { toast } from '../toast.js';

// Tag state
const tags = { titles: [], locations: [] };
// Maps tag-type → the actual input element id in HTML
const INPUT_ID = { titles: 'title-input', locations: 'location-input' };

export function init(register) {
  document.getElementById('title-input')?.addEventListener('keydown',    (e) => addTag(e, 'titles'));
  document.getElementById('location-input')?.addEventListener('keydown', (e) => addTag(e, 'locations'));
  document.getElementById('apollo-search-btn')?.addEventListener('click', runSearch);

  register('search', {
    onEnter: () => {},
    onLeave: () => {},
  });
}

function addTag(e, type) {
  if (e.key !== 'Enter') return;
  e.preventDefault();
  const input = document.getElementById(INPUT_ID[type]);
  if (!input) return;
  const val = input.value.trim();
  if (!val || tags[type].includes(val)) return;
  tags[type].push(val);
  renderTags(type);
  input.value = '';
}

function removeTag(type, idx) {
  tags[type].splice(idx, 1);
  renderTags(type);
}

function renderTags(type) {
  // Container holds tag chips only — the input stays in the DOM outside this container
  const container = document.getElementById(`${type}-tags`);
  if (!container) return;
  container.innerHTML = '';
  tags[type].forEach((t, i) => {
    const tag = document.createElement('div');
    tag.className = 'tag';
    tag.innerHTML = `${esc(t)} <span class="tag__remove" data-i="${i}" data-type="${type}" style="cursor:pointer;margin-left:4px;">✕</span>`;
    container.appendChild(tag);
  });
  container.querySelectorAll('.tag__remove').forEach((btn) => {
    btn.addEventListener('click', () => removeTag(btn.dataset.type, parseInt(btn.dataset.i)));
  });
}

async function runSearch() {
  const btn       = document.getElementById('apollo-search-btn');
  const resultsEl = document.getElementById('search-results-body');
  const industry  = document.getElementById('keywords-input')?.value.trim() || '';
  const limitVal     = parseInt(document.getElementById('search-limit-input')?.value) || 50;
  const perPage       = Math.max(1, Math.min(500, limitVal));
  const sizeVal       = document.getElementById('company-size-select')?.value || 'all';
  const companySizes  = sizeVal === 'all'
    ? ['101,250', '251,500', '501,1000', '1001,5000', '5001,1000000']
    : [sizeVal];

  if (!tags.titles.length) { toast('Add at least one job title', 'warning'); return; }

  btn.innerHTML = '<span class="spinner"></span> Searching…';
  btn.disabled  = true;
  resultsEl.innerHTML = `
    <div class="empty-state">
      <div class="spinner spinner--dark spinner--lg" style="margin:0 auto 16px;"></div>
      <div>Querying Apollo.io — usually 15–30 s…</div>
    </div>`;

  try {
    const res   = await leadsAPI.apollo({ titles: tags.titles, industry, locations: tags.locations, company_sizes: companySizes, target_count: perPage });
    const leads = res.leads || [];
    const badge = document.getElementById('search-count-badge');
    if (badge) badge.textContent = leads.length ? `${leads.length} found` : '';

    if (!leads.length) {
      resultsEl.innerHTML = `<div class="empty-state"><div class="empty-state__icon">🔍</div><p class="empty-state__text">No leads found. Try broader titles or fewer location filters.</p></div>`;
    } else {
      renderResults(leads);
      const added    = res.added        ?? 0;
      const skipped  = res.skipped      ?? 0;
      const credits  = res.credits_used ?? leads.length;
      const parts    = [];
      if (added   > 0) parts.push(`${added} new saved`);
      if (skipped > 0) parts.push(`${skipped} already in database`);
      toast(`Found ${leads.length} lead${leads.length !== 1 ? 's' : ''}${parts.length ? ' · ' + parts.join(', ') : ''}`, 'success');

      // Credits banner
      const banner = document.getElementById('credits-used-banner');
      if (banner) {
        banner.innerHTML = `⚡ <strong>${credits} Apollo credit${credits !== 1 ? 's' : ''} used</strong> this search &nbsp;·&nbsp; ${leads.length} lead${leads.length !== 1 ? 's' : ''} fetched, ${added} new saved, ${skipped} already in DB`;
        banner.style.display = '';
      }
    }
  } catch (e) {
    resultsEl.innerHTML = `
      <div style="padding:20px;">
        <div class="info-box info-box--red">
          <strong>⚠️ Apollo search failed</strong><br>
          ${esc(e.message)}<br><br>
          • Check your Apollo API key in Settings<br>
          • Make sure you have credits remaining<br>
          • Try reducing the result count
        </div>
      </div>`;
  } finally {
    btn.innerHTML = '🔍 Search Apollo';
    btn.disabled  = false;
  }
}

// Store last results so the drawer can access them
let _lastLeads = [];

function renderResults(leads) {
  _lastLeads = leads;
  const el = document.getElementById('search-results-body');
  if (!el) return;
  el.innerHTML = `
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>Name</th><th>Company</th><th>Role</th><th>Location</th><th></th>
        </tr></thead>
        <tbody>
          ${leads.map((l, i) => `
            <tr>
              <td style="font-weight:500;">${esc(((l.first_name || '') + ' ' + (l.last_name || '')).trim() || '—')}</td>
              <td>${esc(l.company || '—')}</td>
              <td class="td--muted">${esc(l.role || '—')}</td>
              <td class="td--muted">${esc(l.location || '—')}</td>
              <td><button class="btn btn--ghost btn--sm" data-idx="${i}">Details ›</button></td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>`;

  el.querySelectorAll('[data-idx]').forEach((btn) => {
    btn.addEventListener('click', () => openLeadDrawer(parseInt(btn.dataset.idx)));
  });
}

function openLeadDrawer(idx) {
  const l = _lastLeads[idx];
  if (!l) return;

  const name         = ((l.first_name || '') + ' ' + (l.last_name || '')).trim() || '—';
  const titleCompany = [l.role, l.company].filter(Boolean).join(' @ ') || '—';

  const setEl   = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val || '—'; };
  const showRow = (id, val) => { const el = document.getElementById(id); if (el) el.style.display = val ? '' : 'none'; };
  const setLink = (id, href) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (href) { el.href = href; el.style.display = ''; }
    else       { el.style.display = 'none'; }
  };

  // Header
  setEl('drawer-name',         name);
  setEl('drawer-title-company', titleCompany);

  // Status
  const statusEl = document.getElementById('drawer-status');
  if (statusEl) { statusEl.textContent = l.status || 'pending'; statusEl.className = `status-badge ${l.status || 'pending'}`; }

  // Quick-link buttons
  setLink('drawer-linkedin-btn', l.linkedin || '');
  setLink('drawer-twitter-btn',  l.twitter  || '');
  setLink('drawer-website-btn',  l.website  || '');

  // Contact section
  const emailEl = document.getElementById('drawer-email');
  if (emailEl) { emailEl.textContent = l.email || '—'; emailEl.href = l.email ? `mailto:${l.email}` : '#'; }

  setEl('drawer-phone',       l.phone);       showRow('dr-phone-row',    l.phone);
  setEl('drawer-location',    l.location);
  setEl('drawer-seniority',   l.seniority);   showRow('dr-seniority-row', l.seniority);
  setEl('drawer-departments', l.departments); showRow('dr-dept-row',      l.departments);
  setEl('drawer-headline',    l.headline);    showRow('dr-headline-row',  l.headline);

  // Company section
  setEl('drawer-company',      l.company);
  setEl('drawer-org-industry', l.org_industry || l.industry);
  setEl('drawer-employees',    l.employees);  showRow('dr-employees-row', l.employees);
  setEl('drawer-org-founded',  l.org_founded); showRow('dr-founded-row',  l.org_founded);
  setEl('drawer-org-funding',  l.org_funding); showRow('dr-funding-row',  l.org_funding);

  const descRow = document.getElementById('dr-desc-row');
  const descEl  = document.getElementById('drawer-org-description');
  if (descEl && l.org_description) { descEl.textContent = l.org_description; if (descRow) descRow.style.display = ''; }
  else if (descRow) descRow.style.display = 'none';

  const techRow = document.getElementById('dr-tech-row');
  const techEl  = document.getElementById('drawer-org-tech');
  if (techEl && l.org_tech_stack) {
    techEl.innerHTML = l.org_tech_stack.split(',').map(t => t.trim()).filter(Boolean)
      .map(t => `<span class="breakdown-pill breakdown-pill--pending" style="font-size:10.5px;">${esc(t)}</span>`).join('');
    if (techRow) techRow.style.display = '';
  } else if (techRow) techRow.style.display = 'none';

  // Add button
  const addBtn = document.getElementById('drawer-add-btn');
  if (addBtn) {
    addBtn.textContent = '+ Add to Leads';
    const handler = async () => {
      addBtn.removeEventListener('click', handler);
      try {
        await leadsAPI.add({
          email: l.email, first_name: l.first_name, last_name: l.last_name,
          company: l.company, role: l.role, industry: l.industry, location: l.location,
        });
        toast('Lead added!', 'success');
        window.closeLeadDrawer?.();
      } catch (e) { toast('Could not add lead: ' + e.message, 'error'); }
    };
    addBtn.addEventListener('click', handler);
  }

  const overlay = document.getElementById('lead-drawer-overlay');
  const drawer  = document.getElementById('lead-drawer');
  if (overlay) { overlay.style.display = 'block'; overlay.classList.add('open'); }
  if (drawer)  { drawer.classList.add('open'); drawer.setAttribute('aria-hidden', 'false'); }
}

window.closeLeadDrawer = () => {
  const overlay = document.getElementById('lead-drawer-overlay');
  const drawer  = document.getElementById('lead-drawer');
  if (overlay) { overlay.style.display = 'none'; overlay.classList.remove('open'); }
  if (drawer)  { drawer.classList.remove('open'); drawer.setAttribute('aria-hidden', 'true'); }
};
