/**
 * utils.js — Pure utility helpers (no DOM side-effects at import time)
 */

// ── HTML escaping ─────────────────────────────────────────────────────────────
const ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ESC_MAP[c]);

// ── URL sanitiser ─────────────────────────────────────────────────────────────
export function safeUrl(raw) {
  const s = String(raw ?? '').trim();
  if (!s) return '';
  try {
    const u = new URL(s, location.origin);
    if (['http:', 'https:', 'mailto:'].includes(u.protocol)) return u.href;
  } catch (_) {}
  return '';
}

// ── HTML sanitiser (for user-generated preview HTML) ─────────────────────────
export function sanitizeHtml(input) {
  const tpl = document.createElement('template');
  tpl.innerHTML = String(input ?? '');
  tpl.content.querySelectorAll('script,iframe,object,embed,style,link').forEach((el) => el.remove());
  tpl.content.querySelectorAll('*').forEach((el) => {
    [...el.attributes].forEach((attr) => {
      const key = attr.name.toLowerCase();
      const val = attr.value || '';
      if (key.startsWith('on')) { el.removeAttribute(attr.name); return; }
      if (key === 'href' || key === 'src') {
        const clean = safeUrl(val);
        if (!clean) el.removeAttribute(attr.name);
        else el.setAttribute(attr.name, clean);
      }
    });
  });
  return tpl.innerHTML;
}

// ── Date helpers ──────────────────────────────────────────────────────────────
export function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export function relativeTime(iso) {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1)  return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ── Colour utilities (for white-label branding) ───────────────────────────────
export function hexToHsl(hex) {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!m) return null;
  let [, r, g, b] = m.map((x) => parseInt(x, 16) / 255);
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0;
  const l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break;
      case g: h = ((b - r) / d + 2) / 6; break;
      case b: h = ((r - g) / d + 4) / 6; break;
    }
  }
  return { h: Math.round(h * 360), s: Math.round(s * 100), l: Math.round(l * 100) };
}

export function applyBrandColor(hex) {
  if (!hex || !/^#[0-9a-f]{6}$/i.test(hex)) return;
  const hsl = hexToHsl(hex);
  if (!hsl) return;
  const root = document.documentElement;
  root.style.setProperty('--brand-h', hsl.h);
  root.style.setProperty('--brand-s', `${hsl.s}%`);
  root.style.setProperty('--brand-l', `${hsl.l}%`);
}

// ── Branding ──────────────────────────────────────────────────────────────────
export function applyBranding(profile) {
  if (!profile) return;
  const nameEl = document.getElementById('brand-name');
  if (nameEl && profile.name) nameEl.textContent = profile.name;

  const markEl = document.getElementById('brand-mark');
  if (markEl) {
    const initials = (profile.name || 'SR')
      .split(/\s+/)
      .map((w) => w[0]?.toUpperCase() || '')
      .slice(0, 2)
      .join('');
    if (profile.logo_url) {
      markEl.innerHTML = `<img src="${esc(profile.logo_url)}" style="width:100%;height:100%;object-fit:cover;" onerror="this.style.display='none'">`;
    } else {
      markEl.textContent = initials || 'SR';
    }
  }

  if (profile.primary_color) applyBrandColor(profile.primary_color);
}

// ── DOM helpers ───────────────────────────────────────────────────────────────
export const $  = (sel, ctx = document) => ctx.querySelector(sel);
export const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

export function setHtml(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

export function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = String(text ?? '');
}

export function setVal(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = String(val ?? '');
}

export function getVal(id) {
  return document.getElementById(id)?.value ?? '';
}
