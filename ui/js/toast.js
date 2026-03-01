/**
 * toast.js — Non-blocking toast notification system
 */

const ICONS = {
  success: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`,
  error:   `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
  info:    `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
  warning: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
};

/**
 * Show a toast notification.
 * @param {string} message  - Text to display
 * @param {'info'|'success'|'error'|'warning'} type
 * @param {number} duration - Auto-dismiss in ms (default 4000)
 */
export function toast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const el = document.createElement('div');
  el.className = `toast toast--${type}`;
  el.innerHTML = `${ICONS[type] || ICONS.info}<span>${String(message ?? '')}</span>`;
  container.appendChild(el);

  const dismiss = () => {
    el.classList.add('toast--out');
    el.addEventListener('animationend', () => el.remove(), { once: true });
  };

  const timer = setTimeout(dismiss, duration);
  el.addEventListener('click', () => { clearTimeout(timer); dismiss(); });
}
