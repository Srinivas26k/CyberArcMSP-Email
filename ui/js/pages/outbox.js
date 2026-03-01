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
let _emailDrawerLeadId = null;   // lead currently open in email editor drawer

export const isCampaignRunning = () => _running;

export function init(register) {
  document.getElementById('start-campaign-btn')?.addEventListener('click',  startSending);
  document.getElementById('stop-campaign-btn')?.addEventListener('click',   stopCampaign);
  document.getElementById('outbox-select-all')?.addEventListener('change', (e) => toggleAll(e.target.checked));

  // Email editor drawer
  document.getElementById('eed-close')?.addEventListener('click',    closeEmailDrawer);
  document.getElementById('email-editor-overlay')?.addEventListener('click', closeEmailDrawer);
  document.getElementById('eed-regen-btn')?.addEventListener('click', () => _eedGenerate(_emailDrawerLeadId));
  document.getElementById('eed-save-btn')?.addEventListener('click',  _eedSaveDraft);
  document.getElementById('eed-send-btn')?.addEventListener('click',  _eedSendLead);
  document.getElementById('eed-tab-preview')?.addEventListener('click', () => _eedSwitchTab('preview'));
  document.getElementById('eed-tab-edit')?.addEventListener('click',   () => _eedSwitchTab('edit'));

  // SSE progress ticks — refresh outbox silently while running
  document.addEventListener('srv:stat', () => { if (_running) refreshOutboxSilently(); });

  // SSE campaign progress bar
  document.addEventListener('srv:progress', (e) => {
    const { sent, total } = e.detail || {};
    if (sent != null && total != null) _updateProgress(sent, total);
  });

  register('outbox', {
    onEnter: () => { loadOutbox(); populateAccountSelect(); },
    onLeave: () => { closeEmailDrawer(); },
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
            <th style="width:72px;"></th>
            <th>Email</th><th>Company</th><th>Role</th><th>Status</th>
          </tr></thead>
          <tbody id="outbox-tbody">
            ${leads.map((l) => `
              <tr data-id="${l.id}">
                <td class="cb-cell"><input type="checkbox" class="lead-cb" value="${l.id}" ${_selectedIds.has(l.id) ? 'checked' : ''}></td>
                <td class="drag-handle" title="Drag to reorder" style="cursor:grab;color:var(--muted);">&#10783;</td>
                <td><button class="btn btn--ghost btn--sm craft-email-btn" data-id="${l.id}" data-name="${esc(((l.first_name||'') + ' ' + (l.last_name||'')).trim())}" data-email="${esc(l.email)}" data-company="${esc(l.company||'')}" style="font-size:11px;padding:4px 10px;white-space:nowrap;">&#9998; Craft</button></td>
                <td>${esc(l.email)}</td>
                <td>${esc(l.company || '\u2014')}</td>
                <td class="td--muted">${esc(l.role || '\u2014')}</td>
                <td><span class="status-badge ${esc(l.status)}">${esc(l.status)}</span></td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>`;

    document.getElementById('outbox-select-all-hdr')?.addEventListener('change', (e) => toggleAll(e.target.checked));

    // Wire Craft Email buttons
    wrap.querySelectorAll('.craft-email-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id      = parseInt(btn.dataset.id);
        const name    = btn.dataset.name?.trim() || btn.dataset.email;
        const company = btn.dataset.company;
        openEmailDrawer(id, name, company);
      });
    });

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


// ─────────────────────────────────────────────────────────────────────────────
// EMAIL EDITOR DRAWER
// ─────────────────────────────────────────────────────────────────────────────

function openEmailDrawer(leadId, name, company) {
  _emailDrawerLeadId = leadId;

  // Set header
  const nameEl = document.getElementById('eed-name');
  const subEl  = document.getElementById('eed-sub');
  if (nameEl) nameEl.textContent = name || 'Lead';
  if (subEl)  subEl.textContent  = company || '';

  // Show loading, hide content
  _eedSetLoading(true);
  _eedSetBtnsDisabled(true);

  // Open drawer
  const overlay = document.getElementById('email-editor-overlay');
  const drawer  = document.getElementById('email-editor-drawer');
  if (overlay) { overlay.style.display = 'block'; overlay.classList.add('open'); }
  if (drawer)  { drawer.classList.add('open'); drawer.setAttribute('aria-hidden', 'false'); }

  // Generate immediately
  _eedGenerate(leadId);
}

function closeEmailDrawer() {
  const overlay = document.getElementById('email-editor-overlay');
  const drawer  = document.getElementById('email-editor-drawer');
  if (overlay) { overlay.style.display = 'none'; overlay.classList.remove('open'); }
  if (drawer)  { drawer.classList.remove('open'); drawer.setAttribute('aria-hidden', 'true'); }
  _emailDrawerLeadId = null;
}

function _eedSetLoading(on) {
  const loading = document.getElementById('eed-loading');
  const content = document.getElementById('eed-content');
  if (loading) loading.style.display = on ? '' : 'none';
  if (content) content.style.display = on ? 'none' : 'flex';
}

function _eedSetBtnsDisabled(disabled) {
  ['eed-regen-btn', 'eed-save-btn', 'eed-send-btn'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = disabled;
  });
}

function _eedSwitchTab(tab) {
  const previewPane = document.getElementById('eed-preview-pane');
  const editPane    = document.getElementById('eed-edit-pane');
  const previewBtn  = document.getElementById('eed-tab-preview');
  const editBtn     = document.getElementById('eed-tab-edit');

  const isPreview = tab === 'preview';

  if (previewPane) previewPane.style.display = isPreview ? '' : 'none';
  if (editPane)    editPane.style.display    = isPreview ? 'none' : '';

  const activeStyle   = 'border-bottom:2px solid var(--primary);margin-bottom:-2px;color:var(--primary);';
  const inactiveStyle = 'border-bottom:none;margin-bottom:0;color:var(--muted);';
  if (previewBtn) previewBtn.style.cssText += isPreview ? activeStyle : inactiveStyle;
  if (editBtn)    editBtn.style.cssText    += isPreview ? inactiveStyle : activeStyle;

  // When switching to preview, sync textarea changes into iframe
  if (isPreview) {
    const html = document.getElementById('eed-body-html')?.value || '';
    _eedUpdatePreview(html);
  }
}

function _eedUpdatePreview(bodyHtml) {
  const iframe = document.getElementById('eed-iframe');
  if (!iframe) return;
  const doc = `<!DOCTYPE html><html><head><meta charset="UTF-8">
    <style>body{font-family:'Helvetica Neue',Arial,sans-serif;font-size:15px;line-height:1.7;
    color:#1a1a1a;padding:24px;max-width:600px;margin:0 auto;}
    p{margin:0 0 14px;}ul{margin:10px 0 16px;padding-left:22px;}li{margin-bottom:10px;}
    strong{color:#0056b3;}a{color:#0056b3;}</style></head>
    <body>${bodyHtml}</body></html>`;
  iframe.srcdoc = doc;
}

async function _eedGenerate(leadId) {
  if (!leadId) return;
  _eedSetLoading(true);
  _eedSetBtnsDisabled(true);

  try {
    const r = await leadsAPI.preview(leadId);
    document.getElementById('eed-subject').value = r.subject || '';
    document.getElementById('eed-body-html').value = r.body_html || '';
    _eedUpdatePreview(r.body_html || '');
    _eedSwitchTab('preview');
    _eedSetLoading(false);
    _eedSetBtnsDisabled(false);
    toast('Email generated — review and edit before sending', 'success');
  } catch (e) {
    _eedSetLoading(false);
    const msg = e.message || 'Unknown error';
    // If it's an LLM config problem, guide the user directly to Settings
    const isConfigErr = /provider|api.?key|settings|save/i.test(msg);
    toast(
      'Generation failed: ' + msg + (isConfigErr ? ' ← click Settings to fix' : ''),
      'error',
      isConfigErr ? 8000 : 4000,
    );
    if (isConfigErr) {
      // Leave drawer open but also show a non-dismissible banner inside it
      const loadEl = document.getElementById('eed-loading');
      if (loadEl) {
        loadEl.style.display = '';
        loadEl.innerHTML = `<div style="color:var(--danger,#ef4444);font-size:0.85rem;padding:20px;text-align:center;">
          <p style="margin:0 0 12px;font-size:1.1rem;">⚠️ LLM provider error</p>
          <p style="margin:0 0 12px;">${msg}</p>
          <button class="btn btn--sm" onclick="location.hash='settings';document.getElementById('email-editor-overlay').click()">
            → Go to Settings
          </button>
        </div>`;
      }
    }
  }
}

async function _eedSaveDraft() {
  const id      = _emailDrawerLeadId;
  const subject = document.getElementById('eed-subject')?.value || '';
  const body    = document.getElementById('eed-body-html')?.value || '';
  if (!id) return;

  const btn = document.getElementById('eed-save-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
  try {
    await leadsAPI.saveDraft(id, { draft_subject: subject, draft_body: body });
    toast('Draft saved', 'success');
  } catch (e) {
    toast('Save failed: ' + e.message, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '💾 Save Draft'; }
  }
}

async function _eedSendLead() {
  const id = _emailDrawerLeadId;
  if (!id) return;

  // Auto-save any edits first
  await _eedSaveDraft();

  const btn = document.getElementById('eed-send-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Sending…'; }
  try {
    const r = await leadsAPI.sendOne(id);
    toast(`Sent! Delivered from ${r.sent_from || 'account'}`, 'success');
    closeEmailDrawer();
    setTimeout(() => loadOutbox(), 1500);
  } catch (e) {
    toast('Send failed: ' + e.message, 'error');
    if (btn) { btn.disabled = false; btn.textContent = '📤 Send This Lead'; }
  }
}

