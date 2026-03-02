/**
 * pages/outbox.js — Campaign control: send config, outbox queue, email preview
 */
import { leadsAPI, accountsAPI, campaignsAPI, settingsAPI } from '../api.js';
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

  // Lead timeline drawer
  document.getElementById('ltd-close')?.addEventListener('click',          closeLeadDetailDrawer);
  document.getElementById('lead-detail-overlay')?.addEventListener('click', closeLeadDetailDrawer);
  document.getElementById('ltd-retry-btn')?.addEventListener('click',       _ltdRetry);
  document.getElementById('ltd-craft-retry-btn')?.addEventListener('click', _ltdCraftRetry);

  // SSE progress ticks — refresh outbox silently while running
  document.addEventListener('srv:stat', () => { if (_running) refreshOutboxSilently(); });

  // SSE campaign progress bar
  document.addEventListener('srv:progress', (e) => {
    const { sent, total } = e.detail || {};
    if (sent != null && total != null) _updateProgress(sent, total);
  });

  register('outbox', {
    onEnter: () => {
      loadOutbox();
      populateAccountSelect();
      _loadDailyLimit();
    },
    onLeave: () => { closeEmailDrawer(); closeLeadDetailDrawer(); },
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
            <th style="width:100px;"></th>
            <th>Email</th><th>Company</th><th>Role</th><th>Status</th>
          </tr></thead>
          <tbody id="outbox-tbody">
            ${leads.map((l) => {
              const isFailed = l.status === 'failed';
              const errTip   = isFailed && l.last_error ? ` title="${esc(l.last_error)}"` : '';
              return `
              <tr data-id="${l.id}" class="outbox-row" style="cursor:pointer;">
                <td class="cb-cell" onclick="event.stopPropagation()"><input type="checkbox" class="lead-cb" value="${l.id}" ${_selectedIds.has(l.id) ? 'checked' : ''}></td>
                <td class="drag-handle" title="Drag to reorder" style="cursor:grab;color:var(--muted);" onclick="event.stopPropagation()">&#10783;</td>
                <td onclick="event.stopPropagation()" style="white-space:nowrap;display:flex;gap:4px;align-items:center;">
                  <button class="btn btn--ghost btn--sm craft-email-btn" data-id="${l.id}" data-name="${esc(((l.first_name||'') + ' ' + (l.last_name||'')).trim())}" data-email="${esc(l.email)}" data-company="${esc(l.company||'')}" style="font-size:11px;padding:4px 10px;white-space:nowrap;">&#9998; Craft</button>
                  ${isFailed ? `<button class="btn btn--sm retry-btn" data-id="${l.id}" style="font-size:11px;padding:4px 8px;background:#fef2f2;color:#be123c;border:1px solid #fecdd3;">↺</button>` : ''}
                </td>
                <td>${esc(l.email)}</td>
                <td>${esc(l.company || '\u2014')}</td>
                <td class="td--muted">${esc(l.role || '\u2014')}</td>
                <td>
                  <span class="status-badge ${esc(l.status)}"${errTip}>${esc(l.status)}</span>
                  ${isFailed && l.last_error ? `<div style="font-size:10px;color:#be123c;max-width:180px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px;" title="${esc(l.last_error)}">${esc(l.last_error.substring(0, 60))}${l.last_error.length > 60 ? '…' : ''}</div>` : ''}
                </td>
              </tr>`;
            }).join('')}
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

    // Wire Retry buttons (quick reset)
    wrap.querySelectorAll('.retry-btn').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const id = parseInt(btn.dataset.id);
        btn.disabled = true;
        btn.textContent = '…';
        try {
          await leadsAPI.retry(id);
          toast('Lead reset to pending — Craft or Start Sending to resend', 'success');
          await loadOutbox();
        } catch (e) {
          toast('Retry failed: ' + e.message, 'error');
          btn.disabled = false;
          btn.textContent = '↺';
        }
      });
    });

    // Wire row click → open lead timeline drawer
    wrap.querySelectorAll('.outbox-row').forEach((row) => {
      row.addEventListener('click', () => {
        const id   = parseInt(row.dataset.id);
        const lead = leads.find((l) => l.id === id);
        if (lead) openLeadDetailDrawer(lead);
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
    sel.innerHTML = '<option value="">↻ Round-Robin (auto-cycle all accounts)</option>' +
      (r.accounts || []).map((a) =>
        `<option value="${a.id}">${esc(a.display_name || a.email)} &lt;${esc(a.email)}&gt;</option>`
      ).join('');
  } catch (_) {}
}

async function startSending() {
  const btn       = document.getElementById('start-campaign-btn');
  const delay     = parseInt(document.getElementById('outbox-delay-input')?.value) || 65;
  const maxLeads  = parseInt(document.getElementById('outbox-max-leads')?.value)  || 50;
  const selAcc    = document.getElementById('outbox-account-select');
  const accId     = selAcc?.value ? parseInt(selAcc.value) : null;

  const lead_ids = _selectedIds.size > 0
    ? _dragOrder.filter((id) => _selectedIds.has(id))
    : [];

  btn.innerHTML = '<span class="spinner"></span> Starting…';
  btn.disabled  = true;

  try {
    const body = { strategy: 'round_robin', delay_seconds: delay, daily_limit: maxLeads };
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


// ─────────────────────────────────────────────────────────────────────────────
// DAILY LIMIT HELPER
// ─────────────────────────────────────────────────────────────────────────────

async function _loadDailyLimit() {
  try {
    const s   = await settingsAPI.get();
    const lim = s.daily_limit ?? s.batch_size ?? 50;
    const inp = document.getElementById('outbox-max-leads');
    if (inp && lim) inp.value = lim;
  } catch (_) {}
}


// ─────────────────────────────────────────────────────────────────────────────
// LEAD DETAIL / TIMELINE DRAWER
// ─────────────────────────────────────────────────────────────────────────────

let _ltdCurrentLead = null;  // lead object currently open in detail drawer

function openLeadDetailDrawer(leadSnapshot) {
  _ltdCurrentLead = leadSnapshot;
  _ltdRenderProfile(leadSnapshot);

  const overlay = document.getElementById('lead-detail-overlay');
  const drawer  = document.getElementById('lead-detail-drawer');
  if (overlay) { overlay.style.display = 'block'; overlay.classList.add('open'); }
  if (drawer)  { drawer.classList.add('open'); drawer.setAttribute('aria-hidden', 'false'); }

  // Show spinner while fetching timeline
  const timelineEl = document.getElementById('ltd-timeline');
  if (timelineEl) timelineEl.innerHTML = `<div style="text-align:center;padding:24px;color:var(--muted);font-size:12px;"><span class="spinner spinner--sm"></span> Loading history…</div>`;

  leadsAPI.timeline(leadSnapshot.id).then((r) => {
    _ltdRenderTimeline(r.history || [], r.lead);
  }).catch(() => {
    const tl = document.getElementById('ltd-timeline');
    if (tl) tl.innerHTML = `<p style="color:var(--danger);font-size:12px;padding:16px;">Could not load send history.</p>`;
  });
}

function closeLeadDetailDrawer() {
  const overlay = document.getElementById('lead-detail-overlay');
  const drawer  = document.getElementById('lead-detail-drawer');
  if (overlay) { overlay.style.display = 'none'; overlay.classList.remove('open'); }
  if (drawer)  { drawer.classList.remove('open'); drawer.setAttribute('aria-hidden', 'true'); }
  _ltdCurrentLead = null;
}

function _ltdRenderProfile(lead) {
  // Avatar initials
  const initials = ((lead.first_name?.[0] || '') + (lead.last_name?.[0] || '')).toUpperCase()
    || lead.email[0].toUpperCase();
  const av = document.getElementById('ltd-avatar');
  if (av) av.textContent = initials;

  // Name / sub
  const fullName = [lead.first_name, lead.last_name].filter(Boolean).join(' ') || lead.email;
  const nameEl   = document.getElementById('ltd-name');
  const subEl    = document.getElementById('ltd-sub');
  if (nameEl) nameEl.textContent = fullName;
  if (subEl)  subEl.textContent  = [lead.role, lead.company].filter(Boolean).join(' @ ');

  // Status badge
  const sb = document.getElementById('ltd-status-badge');
  if (sb) { sb.className = `status-badge ${lead.status}`; sb.textContent = lead.status; }

  // Error alert
  const errBox = document.getElementById('ltd-error-box');
  const errMsg = document.getElementById('ltd-error-msg');
  if (lead.status === 'failed' && lead.last_error) {
    if (errBox) errBox.style.display = '';
    if (errMsg) errMsg.textContent   = lead.last_error;
    document.getElementById('ltd-retry-btn')?.setAttribute('data-id', lead.id);
    document.getElementById('ltd-craft-retry-btn')?.setAttribute('data-id', lead.id);
  } else {
    if (errBox) errBox.style.display = 'none';
  }

  // Profile grid
  const profileEl = document.getElementById('ltd-profile');
  if (!profileEl) return;
  const fields = [
    ['Email',      lead.email],
    ['Company',    lead.company],
    ['Role',       lead.role],
    ['Location',   lead.location],
    ['Industry',   lead.industry || lead.org_industry],
    ['Employees',  lead.employees],
    ['Seniority',  lead.seniority],
    ['LinkedIn',   lead.linkedin ? `<a href="${esc(lead.linkedin)}" target="_blank" style="color:var(--brand);">View profile</a>` : ''],
    ['Website',    lead.website  ? `<a href="${esc(lead.website)}"  target="_blank" style="color:var(--brand);">${esc(lead.website)}</a>`  : ''],
    ['Phone',      lead.phone],
    ['ICP Score',  lead.lead_score ? `<strong>${lead.lead_score}/100</strong>` : ''],
    ['Added',      lead.created_at ? new Date(lead.created_at).toLocaleDateString() : ''],
  ].filter(([, v]) => v);

  profileEl.innerHTML = fields.map(([label, val]) => `
    <div>
      <div style="font-size:10px;color:var(--muted-2);text-transform:uppercase;letter-spacing:.05em;margin-bottom:2px;">${label}</div>
      <div style="font-size:12.5px;color:var(--text);word-break:break-word;">${val}</div>
    </div>`).join('');
}

function _ltdRenderTimeline(history, lead) {
  const tl      = document.getElementById('ltd-timeline');
  const countEl = document.getElementById('ltd-history-count');
  if (countEl) countEl.textContent = history.length ? `(${history.length} email${history.length > 1 ? 's' : ''})` : '';

  // IDs section
  const idsSection = document.getElementById('ltd-ids-section');
  const idsEl      = document.getElementById('ltd-ids');
  if (history.length && idsEl && idsSection) {
    const latest = history[history.length - 1];
    idsSection.style.display = '';
    idsEl.innerHTML = [
      latest.tracking_id  ? `<div><span style="color:var(--muted-2);">Tracking ID:</span> ${esc(latest.tracking_id)}</div>` : '',
      latest.thread_id    ? `<div><span style="color:var(--muted-2);">Thread ID:</span>   ${esc(latest.thread_id)}</div>`   : '',
      lead?.unsubscribe_token ? `<div><span style="color:var(--muted-2);">Unsub token:</span> ${esc(lead.unsubscribe_token)}</div>` : '',
    ].filter(Boolean).join('');
  } else if (idsSection) {
    idsSection.style.display = 'none';
  }

  if (!history.length) {
    if (tl) tl.innerHTML = `<div class="empty-state" style="padding:20px 0;"><p class="empty-state__text">No emails sent yet for this lead.</p></div>`;
    return;
  }

  // Render git-graph-style vertical timeline
  const items = history.map((c, idx) => {
    const isFailed  = !!c.error_message;
    const isOpened  = !!c.opened_at;
    const stepLabel = c.sequence_step === 0 ? 'Initial Email' : `Follow-up #${c.sequence_step}`;
    const dotColor  = isFailed ? '#be123c' : isOpened ? '#16a34a' : '#2563eb';
    const dotIcon   = isFailed ? '✕' : isOpened ? '✓' : '→';
    const sentDate  = c.sent_at ? new Date(c.sent_at).toLocaleString() : 'Pending';
    const isLast    = idx === history.length - 1;

    return `
    <div style="display:flex;gap:0;position:relative;">
      <div style="display:flex;flex-direction:column;align-items:center;flex-shrink:0;width:32px;">
        <div style="width:22px;height:22px;border-radius:50%;background:${dotColor};display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:#fff;flex-shrink:0;z-index:1;">${dotIcon}</div>
        ${!isLast ? `<div style="width:2px;flex:1;background:var(--border);margin:2px 0;min-height:20px;"></div>` : ''}
      </div>
      <div style="flex:1;padding:0 0 20px 10px;">
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:4px;">
          <strong style="font-size:12.5px;">${esc(stepLabel)}</strong>
          ${isOpened ? `<span style="font-size:10px;background:#dcfce7;color:#15803d;padding:2px 6px;border-radius:10px;font-weight:600;">👁 Opened${c.open_count > 1 ? ` ×${c.open_count}` : ''}</span>` : ''}
          ${isFailed ? `<span style="font-size:10px;background:#fef2f2;color:#dc2626;padding:2px 6px;border-radius:10px;font-weight:600;">✕ Failed</span>` : ''}
        </div>
        ${c.subject ? `<div style="font-size:12px;color:var(--muted);margin-bottom:4px;">Subject: <em>${esc(c.subject)}</em></div>` : ''}
        <div style="font-size:11px;color:var(--muted-2);">${sentDate}</div>
        ${c.opened_at ? `<div style="font-size:11px;color:#16a34a;margin-top:2px;">Opened: ${new Date(c.opened_at).toLocaleString()}</div>` : ''}
        ${isFailed    ? `<div style="font-size:11px;color:#dc2626;margin-top:4px;line-height:1.4;word-break:break-word;">Error: ${esc(c.error_message)}</div>` : ''}
        <div style="font-size:10px;color:var(--muted-2);font-family:monospace;margin-top:4px;opacity:.7;">Campaign #${c.id} · ${esc(c.tracking_id?.slice(0,12))}…</div>
      </div>
    </div>`;
  }).join('');

  if (tl) tl.innerHTML = `<div style="padding:16px 16px 4px;">${items}</div>`;
}

async function _ltdRetry() {
  const id = _ltdCurrentLead?.id;
  if (!id) return;
  const btn = document.getElementById('ltd-retry-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Resetting…'; }
  try {
    await leadsAPI.retry(id);
    toast('Lead reset to pending — draft cleared. Start Sending or Craft to resend.', 'success');
    closeLeadDetailDrawer();
    await loadOutbox();
  } catch (e) {
    toast('Retry failed: ' + e.message, 'error');
    if (btn) { btn.disabled = false; btn.textContent = '↺ Reset & Retry'; }
  }
}

async function _ltdCraftRetry() {
  const lead = _ltdCurrentLead;
  if (!lead) return;
  try {
    await leadsAPI.retry(lead.id);
    closeLeadDetailDrawer();
    const name    = [lead.first_name, lead.last_name].filter(Boolean).join(' ') || lead.email;
    openEmailDrawer(lead.id, name, lead.company || '');
  } catch (e) {
    toast('Could not reset lead: ' + e.message, 'error');
  }
}
