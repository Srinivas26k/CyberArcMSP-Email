/**
 * router.js — Hash-based SPA router
 *
 * Maps URL hash (#dashboard, #leads, …) to page IDs.
 * Page modules register lifecycle hooks via `registerPage(id, { onEnter, onLeave })`.
 * The router calls them automatically on navigation.
 */

export const PAGE_META = {
  dashboard: 'Dashboard',
  search:    'Find Leads',
  leads:     'All Leads',
  outbox:    'Send Emails',
  replies:   'Replies',
  inboxes:   'Sender Accounts',
  settings:  'Settings',
  persona:   'Brand Identity',
  records:   'Records & Backup',
};

const _hooks   = {};   // { pageId: { onEnter?, onLeave? } }
let   _current = null;

/** Register lifecycle hooks for a page. Called once per module init. */
export function registerPage(id, hooks = {}) {
  _hooks[id] = hooks;
}

/** Navigate to a page (updates hash → triggers hashchange handler). */
export function navigate(id) {
  location.hash = id;
}

/** Called internally on hash change and at init time. */
function _activate(rawId) {
  const id = PAGE_META[rawId] ? rawId : 'dashboard';

  // ── Deactivate all pages / nav items ──────────────────────
  document.querySelectorAll('.page').forEach((p) => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach((n) => n.classList.remove('active'));

  // ── Show target page ───────────────────────────────────────
  const pg = document.getElementById(`page-${id}`);
  if (pg) pg.classList.add('active');

  // ── Mark nav item active ───────────────────────────────────
  const nav = document.querySelector(`.nav-item[data-page="${id}"]`);
  if (nav) nav.classList.add('active');

  // ── Update topbar title ────────────────────────────────────
  const titleEl = document.getElementById('topbar-title');
  if (titleEl) titleEl.textContent = PAGE_META[id] || id;

  // ── Lifecycle hooks ────────────────────────────────────────
  if (_current && _current !== id && _hooks[_current]?.onLeave) {
    try { _hooks[_current].onLeave(); } catch (_) {}
  }

  _current = id;

  if (_hooks[id]?.onEnter) {
    try { _hooks[id].onEnter(); } catch (_) {}
  }
}

/** Initialise the router. Call once after all page modules have been registered. */
export function initRouter() {
  // Wire up sidebar nav buttons → hash navigation
  document.querySelectorAll('.nav-item[data-page]').forEach((btn) => {
    btn.addEventListener('click', () => {
      location.hash = btn.dataset.page;
    });
  });

  window.addEventListener('hashchange', () => {
    const id = location.hash.replace('#', '') || 'dashboard';
    _activate(id);
  });

  // Handle initial load
  const id = location.hash.replace('#', '') || 'dashboard';
  _activate(id);
}

/** Wire up beforeunload warning while a campaign is running. */
export function guardUnload(isRunningFn) {
  window.addEventListener('beforeunload', (e) => {
    if (isRunningFn()) {
      e.preventDefault();
      return 'A campaign is running. Closing will stop it.';
    }
  });
}
