/**
 * pages/dashboard.js — Dashboard: live stats, campaign health, quick actions
 */
import { healthAPI } from '../api.js';
import { setText } from '../utils.js';
import { isConnected } from '../sse.js';

let _timer = null;

export function init(register) {
  // Manual refresh button
  document.getElementById('dash-refresh-btn')?.addEventListener('click', loadStats);

  // SSE-triggered refresh
  document.addEventListener('srv:refresh-stats', () => {
    if (document.getElementById('page-dashboard')?.classList.contains('active')) {
      loadStats();
    }
  });

  // Update SSE connection indicator on events
  document.addEventListener('srv:connected',    _updateSseIndicator.bind(null, true));
  document.addEventListener('srv:disconnected', _updateSseIndicator.bind(null, false));

  register('dashboard', {
    onEnter: () => {
      loadStats();
      _timer = setInterval(loadStats, 30_000);
    },
    onLeave: () => {
      clearInterval(_timer);
      _timer = null;
    },
  });
}

export async function loadStats() {
  try {
    const [h, s] = await Promise.all([healthAPI.status(), healthAPI.stats()]);

    // ── Stat cards ──────────────────────────────────────────
    setText('s-leads',   String(s.total_leads   ?? 0));
    setText('s-sent',    String(s.sent          ?? 0));
    setText('s-replies', String(s.replied       ?? 0));
    setText('s-inboxes', String(h.active_accounts ?? 0));

    // ── Nav badges ──────────────────────────────────────────
    _setBadge('leads-count-badge',   s.total_leads);
    _setBadge('replies-count-badge', s.replied);
    _setBadge('inboxes-count-badge', h.active_accounts);

    // ── Progress bar ─────────────────────────────────────────
    const sent   = s.sent        ?? 0;
    const total  = s.total_leads ?? 0;
    const failed = s.failed      ?? 0;
    const pending = s.pending    ?? (total - sent - failed);
    const pct = total > 0 ? Math.round((sent / total) * 100) : 0;

    const fillEl = document.getElementById('d-progress-fill');
    if (fillEl) fillEl.style.width = `${pct}%`;
    setText('d-progress-label', `${sent} / ${total} emails delivered`);

    const pendBadge = document.getElementById('d-pending-badge');
    if (pendBadge && pending > 0) {
      pendBadge.textContent = `${pending} pending`;
      pendBadge.style.display = '';
    } else if (pendBadge) {
      pendBadge.style.display = 'none';
    }

    // ── System health panel ──────────────────────────────────
    _setHealthBadge('d-server-badge', 'Online', 'sent');
    _setHealthBadge('d-sse-badge',    isConnected() ? 'Connected' : 'Reconnecting…', isConnected() ? 'sent' : 'pending');
    _setHealthBadge('d-model-badge',  h.model || 'Not set', h.model ? 'sent' : 'pending');

    // ── Topbar badges ────────────────────────────────────────
    const modelBadge = document.getElementById('model-badge');
    if (modelBadge) {
      modelBadge.textContent = h.model ? `⚡ ${h.model}` : '';
      modelBadge.style.display = h.model ? '' : 'none';
    }

    const inboxBadge = document.getElementById('inboxes-topbar-badge');
    if (inboxBadge) {
      inboxBadge.textContent = `📬 ${h.active_accounts} inbox${h.active_accounts !== 1 ? 'es' : ''}`;
      inboxBadge.style.display = h.active_accounts ? '' : 'none';
    }

    // ── Sidebar SSE dot ──────────────────────────────────────
    _updateSseIndicator(isConnected());

    // ── Version ──────────────────────────────────────────────
    const ver = document.getElementById('app-version');
    if (ver && h.version) ver.textContent = `v${h.version}`;

  } catch (e) {
    _setHealthBadge('d-server-badge', 'Offline', 'error');
    _setSseDot(false);
    setText('sse-label', 'Server offline');
  }
}

function _setBadge(id, count) {
  const el = document.getElementById(id);
  if (!el) return;
  if (count > 0) {
    el.textContent = count;
    el.style.display = '';
  } else {
    el.style.display = 'none';
  }
}

function _setHealthBadge(id, label, status) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = label;
  el.className   = `status-badge ${status}`;
}

function _setSseDot(online) {
  const dot   = document.getElementById('sse-dot');
  const label = document.getElementById('sse-label');
  if (dot)   dot.className = `status-dot status-dot--${online ? 'online' : 'offline'}`;
  if (label) label.textContent = online ? 'Live' : 'Connecting…';
}

function _updateSseIndicator(online) {
  _setSseDot(online);
  const sseBadge = document.getElementById('d-sse-badge');
  if (sseBadge) _setHealthBadge('d-sse-badge', online ? 'Connected' : 'Reconnecting…', online ? 'sent' : 'pending');
}

