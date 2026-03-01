/**
 * api.js — Centralised HTTP client
 *
 * Every fetch() call goes through here so that error handling,
 * base-URL changes, and future auth headers live in one place.
 *
 * CORRECT API PATHS (all were wrong in the old monolithic UI):
 *   /api/health          → GET health check
 *   /api/health/stats    → GET dashboard stats
 *   /api/leads/          → leads CRUD
 *   /api/leads/apollo/search → Apollo search (NOT /api/apollo/search)
 *   /api/accounts/       → accounts CRUD
 *   /api/campaigns/start → start (NOT /api/campaign/start)
 *   /api/campaigns/stop  → stop
 *   /api/database/…      → exports, backup, restore, info
 */

export class APIError extends Error {
  constructor(status, detail) {
    super(detail);
    this.status = status;
    this.name   = 'APIError';
  }
}

async function _request(path, { method = 'GET', body, signal } = {}) {
  const init = { method, headers: {} };
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  if (signal) init.signal = signal;

  const res = await fetch(path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new APIError(res.status, detail);
  }
  return res.json();
}

async function _upload(path, formData) {
  const res = await fetch(path, { method: 'POST', body: formData });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new APIError(res.status, detail);
  }
  return res.json();
}

const get    = (path, opts)       => _request(path, { ...opts, method: 'GET'    });
const post   = (path, body, opts) => _request(path, { ...opts, method: 'POST', body });
const patch  = (path, body, opts) => _request(path, { ...opts, method: 'PATCH', body });
const del    = (path, opts)       => _request(path, { ...opts, method: 'DELETE' });
const upload = (path, fd)         => _upload(path, fd);

// ── Typed API namespaces ──────────────────────────────────────────────

export const healthAPI = {
  status: ()     => get('/api/health'),
  stats:  ()     => get('/api/health/stats'),
};

export const leadsAPI = {
  list:      ()           => get('/api/leads/'),
  add:       (data)       => post('/api/leads/', data),
  csv:       (fd)         => upload('/api/leads/csv', fd),
  delete:    (id)         => del(`/api/leads/${id}`),
  clear:     ()           => del('/api/leads/'),
  apollo:    (data)       => post('/api/leads/apollo/search', data),
  // Email draft
  preview:   (id)         => post(`/api/leads/${id}/preview`),
  saveDraft: (id, data)   => patch(`/api/leads/${id}/draft`, data),
  sendOne:   (id)         => post(`/api/leads/${id}/send`),
};

export const accountsAPI = {
  list:   ()      => get('/api/accounts/'),
  add:    (data)  => post('/api/accounts/', data),
  delete: (id)    => del(`/api/accounts/${id}`),
  test:   (id)    => post(`/api/accounts/${id}/test`),
  detect: (email) => get(`/api/accounts/detect-provider?email=${encodeURIComponent(email)}`),
};

export const settingsAPI = {
  get:     ()     => get('/api/settings/'),
  update:  (data) => post('/api/settings/', data),
  testLLM: (data) => post('/api/settings/test-llm', data),
};

export const setupAPI = {
  get:  ()     => get('/api/setup'),
  save: (data) => post('/api/setup', data),
};

export const campaignsAPI = {
  start: (data) => post('/api/campaigns/start', data),
  stop:  ()     => post('/api/campaigns/stop'),
};

export const repliesAPI = {
  list:  ()  => get('/api/replies/'),
  check: ()  => post('/api/replies/check'),
};

export const databaseAPI = {
  info:    ()   => get('/api/database/info'),
  restore: (fd) => upload('/api/database/restore', fd),
  // Static download URLs (used as href values):
  LEADS_EXPORT:     '/api/database/leads/export',
  CAMPAIGNS_EXPORT: '/api/database/campaigns/export',
  REPLIES_EXPORT:   '/api/database/replies/export',
  BACKUP:           '/api/database/backup',
};
