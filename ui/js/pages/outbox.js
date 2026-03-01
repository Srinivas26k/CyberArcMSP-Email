/**
 * pages/outbox.js — Campaign control: send config, outbox queue, email preview
 */
import { leadsAPI, accountsAPI, campaignsAPI } from '../api.js';
import { esc } from '../utils.js';
import { toast } from '../toast.js';

let _selectedIds  = new Set();
let _sortable     = null;
let _dragOrder    = [];
let _running      = false;

export const isCampaignRunning = () => _running;

export function init(register) {
  document.getElementById('start-campaign-btn')?.addEventListener('click',  startSending);
  document.getElementById('stop-campaign-btn')?.addEventListener('click',   stopCampaign);
  document.getElementById('outbox-select-all')?.addEventListener('change', (e) => toggleAll(e.target.checked));

  // SSE progress ticks — refresh outbox silently while running
  document.addEventListener('srv:stat', () => { if (_running) refreshOutboxSilently(); });

  // SSE campaign progress bar
  document.addEventListener('srv:progress', (e) => {
    const { sent, total } = e.detail || {};
    if (sent != null && total != null) _updateProgress(sent, total);
  });

  register('outbox', {
    onEnter: () => { loadOutbox(); populateAccountSelect(); },
    onLeave: () => {},
  });
}

async function loadOutbox() {
  const wrap = document.getElementById('outbox-list-body');
  if (!wrap) return;

  try {
    const r     = await leadsAPI.list();
    const leads = r.leads || [];
    const badge   = document.getElementById('outbox-count-badge');
    const pending = leads.filter((l) => l.status === 'pending').length;
    if (badge) badge.textContent = `${pending} pending`;

    if (!leads.length) {
      wrap.innerHTML = `<div class="empty-state" style="padding:40px 0;"><div class="empty-state__icon">📤</div><p class="empty-state__text">Outbox is empty — search for leads or upload a CSV first.</p></div>`;
      _dragOrder = [];
      return;
    }

    _dragOrder = leads.map((l) => l.id);
    wrap.innerHTML = `
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th style="width:32px;"><input type="checkbox" id="outbox-select-all-hdr"></th>
            <th style="width:20px;"></th>
            <th>Email</th><th>Company</th><th>Role</th><th>Status</th><th>Sent from</th>
          </tr></thead>
          <tbody id="outbox-tbody">
            ${leads.map((l) => `
              <tr data-id="${l.id}">
                <td class="cb-cell"><input type="checkbox" class="lead-cb" value="${l.id}" ${_selectedIds.has(l.id) ? 'checked' : ''}></td>
                <td class="drag-handle" title="Drag to reorder" style="cursor:grab;color:var(--muted);">&#10783;</td>
                <td>${esc(l.email)}</td>
                <td>${esc(l.company || '—')}</td>
                <td class="td--muted">${esc(l.role || '—')}</td>
                <td><span class="status-badge ${esc(l.status)}">${esc(l.status)}</span></td>
                <td class="td--mono" style="font-size:11px;">${esc(l.sent_from || '—')}</td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>`;

    document.getElementById('outbox-select-all-hdr')?.addEventListener('change', (e) => toggleAll(e.target.checked));

    wrap.querySelectorAll('.lead-cb').forEach((cb) => {
      cb.addEventListener('change', () => {
        const id = parseInt(cb.value);
        if (cb.checked) _selectedIds.add(id); else _selectedIds.delete(id);
      });
    });

    const tbody = document.getElementById('outbox-tbody');
    if (_sortable) _sortable.destroy();
    if (window.Sortable && tbody) {
      _sortable = Sortable.create(tbody, {
        handle: '.drag-handle',
        animation: 150,
        onEnd: () => {
          _dragOrder = [...tbody.querySelectorAll('tr[data-id]')].map((r) => parseInt(r.dataset.id));
        },
      });
    }
  } catch (e) {
    toast('Could not load outbox: ' + e.message, 'error');
  }
}

async function refreshOutboxSilently() {
  try {
    const r = await leadsAPI.list();
    const leads = r.leads || [];
    const tbody = document.getElementById('outbox-tbody'); // rendered inside outbox-list-body
    if (!tbody) return;
    leads.forEach((l) => {
      const row = tbody.querySelector(`tr[data-id="${l.id}"]`);
      if (!row) return;
      const badge = row.querySelector('.status-badge');
      if (badge) { badge.className = `status-badge ${l.status}`; badge.textContent = l.status; }
    });
  } catch (_) {}
}

function toggleAll(checked) {
  document.querySelectorAll('.lead-cb').forEach((cb) => {
    cb.checked = checked;
    const id = parseInt(cb.value);
    if (checked) _selectedIds.add(id); else _selectedIds.delete(id);
  });
}

function _setRunning(running) {
  _running = running;

  const bar      = document.getElementById('campaign-bar');
  const pill     = document.getElementById('campaign-pill');
  const startBtn = document.getElementById('start-campaign-btn');
  const stopBtn  = document.getElementById('stop-campaign-btn');

  if (bar)      bar.style.display      = running ? '' : 'none';
  if (pill)     pill.style.display     = running ? '' : 'none';
  if (startBtn) startBtn.style.display = running ? 'none' : '';
  if (stopBtn)  stopBtn.style.display  = running ? '' : 'none';

  document.dispatchEvent(new CustomEvent('campaign:state', { detail: { running } }));
}

function _updateProgress(sent, total) {
  const fill     = document.getElementById('campaign-bar-fill');
  const pillText = document.getElementById('campaign-pill-text');
  if (fill && total > 0) fill.style.width = `${Math.round((sent / total) * 100)}%`;
  if (pillText) pillText.textContent = `Sending… ${sent}/${total}`;
}

async function populateAccountSelect() {
  const sel = document.getElementById('outbox-account-select');
  if (!sel) return;
  try {
    const r = await accountsAPI.list();
    sel.innerHTML = '<option value="">🔄 Round-Robin (auto-cycle all accounts)</option>' +
      (r.accounts || []).map((a) =>
        `<option value="${a.id}">${esc(a.display_name || a.email)} &lt;${esc(a.email)}&gt;</option>`
      ).join('');
  } catch (_) {}
}

async function startSending() {
  const btn    = document.getElementById('start-campaign-btn');
  const delay  = parseInt(document.getElementById('outbox-delay-input')?.value) || 65;
  const selAcc = document.getElementById('outbox-account-select');
  const accId  = selAcc?.value ? parseInt(selAcc.value) : null;

  const lead_ids = _selectedIds.size > 0
    ? _dragOrder.filter((id) => _selectedIds.has(id))
    : [];

  btn.innerHTML = '<span class="spinner"></span> Starting…';
  btn.disabled  = true;

  try {
    const body = { strategy: 'round_robin', delay_seconds: delay };
    if (lead_ids.length) body.lead_ids          = lead_ids;
    if (accId)           body.active_account_id  = accId;

    const r = await campaignsAPI.start(body);
    toast(`Campaign started — ${lead_ids.length || r.lead_count || 0} leads queued`, 'success');
    _setRunning(true);
    setTimeout(() => loadOutbox(), 3000);
  } catch (e) {
    toast('Start failed: ' + e.message, 'error');
  } finally {
    btn.innerHTML = '▶ Start Sending';
    btn.disabled  = false;
  }
}

async function stopCampaign() {
  try {
    await campaignsAPI.stop();
    toast('Campaign stopping…', 'info');
    _setRunning(false);
  } catch (e) { toast(e.message, 'error'); }
}

