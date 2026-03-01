/**
 * pages/leads.js — All Leads: per-row selection, delete selected, CSV upload
 */
import { leadsAPI } from '../api.js';
import { esc } from '../utils.js';
import { toast } from '../toast.js';

// Tracks selected lead IDs across renders
const _selected = new Set();

export function init(register) {
  document.getElementById('csv-upload-input')?.addEventListener('change', (e) => uploadCSV(e.target));
  document.getElementById('delete-selected-btn')?.addEventListener('click', deleteSelected);

  register('leads', {
    onEnter: loadLeads,
    onLeave: () => { _selected.clear(); _updateSelectionUI(); },
  });
}

/** Show/hide the selection toolbar based on _selected size */
function _updateSelectionUI() {
  const count  = _selected.size;
  const label  = document.getElementById('leads-sel-label');
  const delBtn = document.getElementById('delete-selected-btn');
  if (label)  { label.textContent  = count ? `${count} lead${count !== 1 ? 's' : ''} selected` : ''; label.style.display  = count ? '' : 'none'; }
  if (delBtn) { delBtn.style.display = count ? '' : 'none'; }
}

export async function loadLeads() {
  _selected.clear();
  _updateSelectionUI();

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

    _renderTable(leads);
  } catch (e) {
    wrap.innerHTML = `<div style="color:var(--danger);padding:24px;text-align:center;">Failed to load leads: ${esc(e.message)}</div>`;
    toast(e.message, 'error');
  }
}

function _renderTable(leads) {
  const wrap = document.getElementById('leads-table-body');
  if (!wrap) return;

  wrap.innerHTML = `
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th style="width:36px;">
            <input type="checkbox" id="leads-select-all" title="Select / deselect all" style="cursor:pointer;" />
          </th>
          <th>Email</th><th>Name</th><th>Company</th><th>Role</th><th>Location</th><th>Status</th>
        </tr></thead>
        <tbody>
          ${leads.map((l) => `
            <tr data-id="${l.id}" class="lead-row">
              <td><input type="checkbox" class="lead-chk" data-id="${l.id}" style="cursor:pointer;" /></td>
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

  const selectAll = document.getElementById('leads-select-all');

  // ── Select-all header checkbox ──────────────────────────────────────────────
  selectAll?.addEventListener('change', () => {
    wrap.querySelectorAll('.lead-chk').forEach((chk) => {
      chk.checked = selectAll.checked;
      const id = parseInt(chk.dataset.id);
      selectAll.checked ? _selected.add(id) : _selected.delete(id);
      chk.closest('tr')?.classList.toggle('row--selected', selectAll.checked);
    });
    _updateSelectionUI();
  });

  // ── Individual row checkboxes ───────────────────────────────────────────────
  wrap.querySelectorAll('.lead-chk').forEach((chk) => {
    chk.addEventListener('change', () => {
      const id = parseInt(chk.dataset.id);
      if (chk.checked) _selected.add(id); else _selected.delete(id);
      chk.closest('tr')?.classList.toggle('row--selected', chk.checked);

      // Sync select-all indeterminate / checked state
      const all  = wrap.querySelectorAll('.lead-chk');
      const chkd = wrap.querySelectorAll('.lead-chk:checked');
      if (selectAll) {
        selectAll.checked       = chkd.length > 0 && chkd.length === all.length;
        selectAll.indeterminate = chkd.length > 0 && chkd.length < all.length;
      }
      _updateSelectionUI();
    });
  });
}

/** Delete only the manually selected leads */
async function deleteSelected() {
  if (!_selected.size) return;
  const count = _selected.size;
  if (!confirm(`Delete ${count} selected lead${count !== 1 ? 's' : ''}? This cannot be undone.`)) return;

  const btn = document.getElementById('delete-selected-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Deleting…'; }

  try {
    await Promise.all([..._selected].map((id) => leadsAPI.delete(id)));
    _selected.clear();
    toast(`Deleted ${count} lead${count !== 1 ? 's' : ''}`, 'info');
    loadLeads();
  } catch (e) {
    toast('Delete failed: ' + e.message, 'error');
    if (btn) { btn.disabled = false; btn.textContent = '🗑 Delete Selected'; }
  }
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

