/**
 * pages/replies.js — Reply inbox and check-all
 */
import { repliesAPI } from '../api.js';
import { esc, formatDate } from '../utils.js';
import { toast } from '../toast.js';

export function init(register) {
  document.getElementById('check-replies-btn')?.addEventListener('click', checkReplies);

  document.addEventListener('srv:reply', () => {
    if (document.getElementById('page-replies')?.classList.contains('active')) {
      loadReplies();
    }
    const badge = document.getElementById('replies-count-badge');
    if (badge) {
      const n = parseInt(badge.textContent || '0') + 1;
      badge.textContent = n;
      badge.style.display = '';
    }
  });

  register('replies', {
    onEnter: loadReplies,
    onLeave: () => {},
  });
}

async function loadReplies() {
  const wrap = document.getElementById('replies-list-body');
  if (!wrap) return;

  wrap.innerHTML = `<div style="padding:40px;text-align:center;"><span class="spinner spinner--dark"></span></div>`;

  try {
    const r       = await repliesAPI.list();
    const replies = r.replies || [];

    const totalBadge = document.getElementById('replies-total-badge');
    const navBadge   = document.getElementById('replies-count-badge');
    if (totalBadge) totalBadge.textContent = replies.length ? `${replies.length} replies` : '';
    if (navBadge)   { navBadge.textContent = replies.length; navBadge.style.display = replies.length ? '' : 'none'; }

    if (!replies.length) {
      wrap.innerHTML = `<div class="empty-state" style="padding:40px 0;"><div class="empty-state__icon"><svg class="icon" aria-hidden="true" width="40" height="40"><use href="#icon-message"/></svg></div><p class="empty-state__text">No replies yet. Click <em>Check Inboxes</em> to sync.</p></div>`;
      return;
    }

    wrap.innerHTML = `
      <div class="table-wrap">
        <table>
          <thead><tr><th>From</th><th>Subject</th><th>Inbox</th><th>Preview</th><th>Received</th></tr></thead>
          <tbody>
            ${replies.map((rep) => `
              <tr>
                <td style="font-weight:500;">${esc(rep.from_email)}</td>
                <td>${esc(rep.subject || '—')}</td>
                <td class="td--sm">${esc(rep.inbox_account || '—')}</td>
                <td class="td--muted" style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${esc(rep.snippet || '—')}</td>
                <td class="td--sm" style="white-space:nowrap;">${formatDate(rep.received_at)}</td>
              </tr>`).join('')}
          </tbody>
        </table>
      </div>`;
  } catch (e) {
    wrap.innerHTML = `<div style="text-align:center;color:var(--danger);padding:24px;">${esc(e.message)}</div>`;
  }
}

async function checkReplies() {
  const btn = document.getElementById('check-replies-btn');
  if (btn) { btn.innerHTML = '<span class="spinner"></span> Checking…'; btn.disabled = true; }

  try {
    const r = await repliesAPI.check();
    const n = r.new_replies || 0;
    toast(`${n} new ${n === 1 ? 'reply' : 'replies'} found`, n > 0 ? 'success' : 'info');
    loadReplies();
  } catch (e) {
    toast('Reply check failed: ' + e.message, 'error');
  } finally {
    if (btn) { btn.innerHTML = '↺ Check Inboxes'; btn.disabled = false; }
  }
}
