/**
 * pages/inboxes.js — Sender accounts: cards, test, delete
 */
import { accountsAPI } from '../api.js';
import { esc } from '../utils.js';
import { toast } from '../toast.js';

export function init(register) {
  document.getElementById('test-all-btn')?.addEventListener('click', testAll);

  register('inboxes', {
    onEnter: loadInboxes,
    onLeave: () => {},
  });
}

async function loadInboxes() {
  const grid  = document.getElementById('inboxes-grid');
  const empty = document.getElementById('inboxes-empty');
  if (!grid) return;
  grid.innerHTML = `<div style="color:var(--muted);font-size:13px;padding:8px;">Loading accounts…</div>`;
  if (empty) empty.style.display = 'none';

  try {
    const r = await accountsAPI.list();
    const accounts = r.accounts || [];

    const topbarBadge = document.getElementById('inboxes-topbar-badge');
    const navBadge    = document.getElementById('inboxes-count-badge');
    if (topbarBadge) { topbarBadge.textContent = `${accounts.length} inboxes`; topbarBadge.style.display = accounts.length ? '' : 'none'; }
    if (navBadge)    { navBadge.textContent = accounts.length; navBadge.style.display = accounts.length ? '' : 'none'; }

    if (!accounts.length) {
      grid.innerHTML = '';
      if (empty) empty.style.display = '';
      return;
    }

    grid.innerHTML = accounts.map((a) => `
      <div class="inbox-card inbox-card--connected" id="inbox-card-${a.id}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
          <div>
            <div class="inbox-card__email">${esc(a.email)}</div>
            <div class="inbox-card__meta">${esc(a.display_name || a.email)} · ${esc(a.provider)}</div>
          </div>
          <span class="badge badge--success" id="inbox-status-${a.id}">Active</span>
        </div>
        <div class="inbox-card__row">
          <button class="btn btn--ghost btn--sm" data-test="${a.id}">Test</button>
          <button class="btn btn--danger btn--sm" data-delete="${a.id}">Remove</button>
        </div>
      </div>`).join('');

    grid.querySelectorAll('[data-test]').forEach((btn) => {
      btn.addEventListener('click', () => testAccount(parseInt(btn.dataset.test)));
    });
    grid.querySelectorAll('[data-delete]').forEach((btn) => {
      btn.addEventListener('click', () => deleteAccount(parseInt(btn.dataset.delete)));
    });
  } catch (e) {
    grid.innerHTML = `<div style="color:var(--danger);">Failed to load: ${esc(e.message)}</div>`;
  }
}

async function testAccount(id) {
  const badge = document.getElementById(`inbox-status-${id}`);
  if (badge) { badge.textContent = '⏳'; badge.className = 'badge badge--muted'; }

  try {
    const r = await accountsAPI.test(id);
    if (badge) {
      badge.textContent  = r.ok ? '✓ Connected' : '✗ Failed';
      badge.className    = `badge ${r.ok ? 'badge--success' : 'badge--danger'}`;
    }
    toast(r.message || (r.ok ? 'Connection OK' : 'Connection failed'), r.ok ? 'success' : 'error');
  } catch (e) {
    if (badge) { badge.textContent = '✗ Failed'; badge.className = 'badge badge--danger'; }
    toast('Test failed: ' + e.message, 'error');
  }
}

async function deleteAccount(id) {
  if (!confirm('Remove this account?')) return;
  try {
    await accountsAPI.delete(id);
    toast('Account removed', 'info');
    loadInboxes();
  } catch (e) { toast(e.message, 'error'); }
}

async function testAll() {
  await loadInboxes(); // re-render so badges exist
  try {
    const r = await accountsAPI.list();
    const accounts = r.accounts || [];
    let okCount = 0;
    for (const a of accounts) {
      const badge = document.getElementById(`inbox-status-${a.id}`);
      if (badge) { badge.textContent = '⏳'; badge.className = 'badge badge--muted'; }
      try {
        const res = await accountsAPI.test(a.id);
        if (badge) { badge.textContent = res.ok ? '✓ OK' : '✗ Fail'; badge.className = `badge ${res.ok ? 'badge--success' : 'badge--danger'}`; }
        if (res.ok) okCount++;
      } catch (_) {
        if (badge) { badge.textContent = '✗ Fail'; badge.className = 'badge badge--danger'; }
      }
    }
    toast(`${okCount}/${accounts.length} accounts connected`, okCount === accounts.length ? 'success' : 'warning');
  } catch (e) { toast(e.message, 'error'); }
}
