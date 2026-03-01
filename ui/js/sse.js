/**
 * sse.js — Server-Sent Events manager
 *
 * Connects to /api/stream, auto-reconnects on drop, and dispatches
 * typed CustomEvents on `document` so any page module can subscribe
 * without knowing about EventSource directly.
 *
 * Emitted events:
 *   srv:connected            — initial connection established
 *   srv:disconnected         — connection lost (reconnect pending)
 *   srv:stat       {detail}  — campaign/stats update → triggers stats refresh
 *   srv:reply      {detail}  — new reply detected
 *   srv:progress   {detail}  — email-send progress tick
 *   srv:refresh-stats        — convenience alias for any stats-invalidating event
 */

let _es = null;
let _reconnectTimer = null;
let _connected = false;

export function connectSSE() {
  if (_es) return;
  _connect();
}

export function disconnectSSE() {
  if (_reconnectTimer) clearTimeout(_reconnectTimer);
  if (_es) { _es.close(); _es = null; }
  _connected = false;
}

export const isConnected = () => _connected;

function _connect() {
  _es = new EventSource('/api/stream');

  _es.onopen = () => {
    _connected = true;
    document.dispatchEvent(new CustomEvent('srv:connected'));
  };

  _es.onmessage = (e) => {
    let data;
    try { data = JSON.parse(e.data); } catch (_) { return; }

    if (data.type === 'connected') return;

    // Dispatch typed event
    document.dispatchEvent(new CustomEvent(`srv:${data.type}`, { detail: data }));

    // Generic stats-refresh for any stat-bearing event
    if (data.type === 'stat' || data.type === 'progress' || data.type === 'reply') {
      document.dispatchEvent(new CustomEvent('srv:refresh-stats'));
    }
  };

  _es.onerror = () => {
    _connected = false;
    _es?.close();
    _es = null;
    document.dispatchEvent(new CustomEvent('srv:disconnected'));
    _reconnectTimer = setTimeout(_connect, 5000);
  };
}
