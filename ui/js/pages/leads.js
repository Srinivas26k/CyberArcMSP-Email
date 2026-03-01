/**
 * pages/leads.js — All Leads: table, CSV upload/export, delete
 */
import { leadsAPI } from '../api.js';
import { esc, formatDate } from '../utils.js';
import { toast } from '../toast.js';

export function init(register) {
  document.getElementById('clear-leads-btn')?.addEventListener('click',   clearAllLeads);
  document.getElementById('csv-upload-input')?.addEventListener('change', (e) => uploadCSV(e.target));

  register('leads', {
    onEnter: loadLeads,
    onLeave: () => {},
  });
}

async function loadLeads() {
  const wrap = document.getElementById('leads-table-body');
  if (!wrap) return;
  wrap.innerHTML = `
    <div style="padding:16px;display:flex;flex-direction:column;gap:8px;">
      ${Array.from({ length: 5 }, () => '<div class="skeleton skeleton--line" style="width:100%;height:36px;"></div>').join('')}
    </div>`;

  try {
    const r     = await leadsAPI.list();
    const leads = r.leads || [];

    const totalBadge = document.getElementById('leads-total-badge');
    const navBadge   = document.getElementById('leads-count-badge');
    if (totalBadge) totalBadge.textContent = `${leads.length} leads`;
    if (navBadge)   { navBadge.textContent = leads.length; navBadge.style.display = leads.length ? '' : 'none'; }

    if (!leads.length) {
      wrap.innerHTML = `<div class="empty-state" style="padding:40px 0;"><div class="empty-state__icon">👥</div><p class="empty-state__text">No leads yet — search Apollo or upload a CSV to get started.</p></div>`;
      return;
    }

    wrap.innerHTML = `
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>Email</th><th>Name</th><th>Company</th><th>Role</th><th>Location</th><th>Status</th>
          </tr></thead>
          <tbody>
            ${leads.map((l) => `
              <tr>
                <td>${esc(l.email)}</td>
                <td style="font-weight:500;">${esc(((l.first_name || '') + ' ' + (l.last_name || '')).trim()) || '—'}</td>
                <td>${esc(l.company || '—')}</td>
                <td class="td--muted">${esc(l.role || '—')}</td>
                <td class="td--muted">${esc(l.location || '—')}</td>
                <td><span class="status-badge ${esc(l.status)}">${esc(l.status)}</span></td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
  } catch (e) {
    wrap.innerHTML = `<div style="color:var(--danger);padding:24px;text-align:center;">Failed to load leads: ${esc(e.message)}</div>`;
    toast(e.message, 'error');
  }
}

async function clearAllLeads() {
  if (!confirm('Delete ALL leads? This cannot be undone.')) return;
  try {
    const r = await leadsAPI.clear();
    toast(`Deleted ${r.deleted} leads`, 'info');
    loadLeads();
  } catch (e) { toast(e.message, 'error'); }
}

async function uploadCSV(input) {
  if (!input.files.length) return;
  const fd = new FormData();
  fd.append('file', input.files[0]);
  try {
    const r = await leadsAPI.csv(fd);
    toast(`Imported ${r.added} leads (${r.skipped} skipped)`, 'success');
    loadLeads();
  } catch (e) {
    toast('CSV upload failed: ' + e.message, 'error');
  }
  input.value = '';
}

