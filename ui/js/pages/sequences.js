/**
 * pages/sequences.js — Follow-up sequence builder and enrollment manager
 *
 * Sequences allow you to automatically send follow-up emails to leads
 * on a schedule (e.g. Day 3, Day 7, Day 14) with AI-generated content.
 * A sequence stops automatically when a lead replies or unsubscribes.
 */
import { toast } from '../toast.js';

const BASE = '/api/sequences';

// ── API helpers ──────────────────────────────────────────────────────────────

async function _apiFetch(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText);
  }
  return res.status === 204 ? null : res.json();
}

const seqAPI = {
  list:   ()         => _apiFetch('/'),
  create: (body)     => _apiFetch('/', { method: 'POST', body: JSON.stringify(body) }),
  update: (id, body) => _apiFetch(`/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  remove: (id)       => _apiFetch(`/${id}`, { method: 'DELETE' }),
  enrollments: ()    => _apiFetch('/enrollments/all'),
  enroll: (id, body) => _apiFetch(`/${id}/enroll`, { method: 'POST', body: JSON.stringify(body) }),
  stopEnroll: (id)   => _apiFetch(`/enrollments/${id}/stop`, { method: 'POST' }),
};

// ── State ────────────────────────────────────────────────────────────────────

let _sequences   = [];
let _enrollments = [];
let _editingId   = null;  // null = new, number = editing existing

// ── Init ─────────────────────────────────────────────────────────────────────

export function init(register) {
  // New sequence button
  document.getElementById('seq-new-btn')?.addEventListener('click', () => _showForm(null));
  document.getElementById('seq-cancel-btn')?.addEventListener('click', _hideForm);
  document.getElementById('seq-save-btn')?.addEventListener('click', _saveSequence);
  document.getElementById('seq-add-step-btn')?.addEventListener('click', () => _addStep());

  register('sequences', {
    onEnter: loadSequences,
    onLeave: () => {},
  });
}

// ── Load data ─────────────────────────────────────────────────────────────────

export async function loadSequences() {
  try {
    const [sq, en] = await Promise.all([seqAPI.list(), seqAPI.enrollments()]);
    _sequences   = sq.sequences   || [];
    _enrollments = en.enrollments || [];
    _renderList();
    _renderStats();
  } catch (err) {
    console.error('sequences load error', err);
  }
}

// ── Render list ───────────────────────────────────────────────────────────────

function _renderList() {
  const body  = document.getElementById('seq-list-body');
  const badge = document.getElementById('seq-count-badge');
  if (badge) badge.textContent = `${_sequences.length}`;

  if (!_sequences.length) {
    body.innerHTML = `<div class="empty-state">
      <div class="empty-state__icon">🔄</div>
      <p class="empty-state__text">No sequences yet. Create one to start automated follow-ups.</p>
    </div>`;
    return;
  }

  body.innerHTML = _sequences.map(s => {
    const activeCount = _enrollments.filter(e => e.sequence_id === s.id && e.status === 'active').length;
    const stepsCount  = (s.steps || []).length;
    return `
    <div class="outbox-row" style="display:flex;align-items:center;gap:12px;padding:14px 16px;border-bottom:1px solid var(--border);">
      <div style="flex:1;min-width:0;">
        <div style="font-weight:600;font-size:14px;color:var(--fg);">${_esc(s.name)}</div>
        <div style="font-size:12px;color:var(--muted);margin-top:2px;">${_esc(s.description || '')}</div>
        <div style="margin-top:6px;display:flex;gap:8px;flex-wrap:wrap;">
          <span class="badge badge--secondary">${stepsCount} step${stepsCount !== 1 ? 's' : ''}</span>
          ${s.steps.map((st, i) => `<span class="badge badge--secondary" title="${_esc(st.instructions || '')}">Day ${_cumulativeDays(s.steps, i)}: ${_esc(st.subject_hint || `Step ${i + 1}`)}</span>`).join('')}
        </div>
      </div>
      <div style="text-align:right;min-width:90px;">
        <div style="font-size:22px;font-weight:700;color:var(--brand);">${activeCount}</div>
        <div style="font-size:11px;color:var(--muted);">active</div>
      </div>
      <div style="display:flex;gap:6px;">
        <button class="btn btn--ghost btn--sm" onclick="seqEdit(${s.id})">✏️</button>
        <button class="btn btn--danger btn--sm" onclick="seqDelete(${s.id})">🗑</button>
      </div>
    </div>`;
  }).join('');
}

function _cumulativeDays(steps, upToIndex) {
  let total = 0;
  for (let i = 0; i <= upToIndex; i++) total += (steps[i]?.delay_days ?? 3);
  return total;
}

function _renderStats() {
  const active  = _enrollments.filter(e => e.status === 'active').length;
  const done    = _enrollments.filter(e => e.status === 'completed').length;
  const replied = _enrollments.filter(e => e.status === 'replied').length;

  const setText = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  setText('seq-stat-active',  active);
  setText('seq-stat-done',    done);
  setText('seq-stat-replied', replied);

  // Update nav badge
  const badge = document.getElementById('seq-badge');
  if (badge) {
    badge.textContent = active;
    badge.style.display = active > 0 ? '' : 'none';
  }
}

// ── Form (create / edit) ──────────────────────────────────────────────────────

function _showForm(seq) {
  _editingId = seq ? seq.id : null;
  document.getElementById('seq-form-title').textContent = seq ? `Edit: ${seq.name}` : 'New Sequence';
  document.getElementById('seq-name-input').value = seq?.name || '';
  document.getElementById('seq-desc-input').value = seq?.description || '';

  // Clear + rebuild steps
  const container = document.getElementById('seq-steps-container');
  container.innerHTML = '';
  const steps = seq?.steps || [
    { delay_days: 3, subject_hint: 'Quick follow-up', instructions: 'Short 2-line follow-up. Mention you reached out last week.' },
    { delay_days: 5, subject_hint: 'Last touch',       instructions: 'Brief break-up email. No hard sell. Leave the door open.' },
  ];
  steps.forEach(st => _addStep(st));

  document.getElementById('seq-form-panel').style.display = '';
  document.getElementById('seq-form-panel').scrollIntoView({ behavior: 'smooth' });
}

function _hideForm() {
  document.getElementById('seq-form-panel').style.display = 'none';
  _editingId = null;
}

function _addStep(step = {}) {
  const container = document.getElementById('seq-steps-container');
  const idx       = container.children.length + 1;
  const div       = document.createElement('div');
  div.className   = 'panel';
  div.style.cssText = 'padding:12px;background:var(--surface-2,#f8f9fa);border-radius:8px;';
  div.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
      <strong style="font-size:13px;">Step ${idx}</strong>
      <button class="btn btn--ghost btn--sm" style="padding:2px 8px;" onclick="this.closest('div.panel').remove();_renumberSteps()">✕</button>
    </div>
    <div style="display:grid;grid-template-columns:100px 1fr;gap:10px;margin-bottom:10px;">
      <label style="margin:0;">Wait (days)<input type="number" class="step-delay" value="${step.delay_days ?? 3}" min="1" max="30" /></label>
      <label style="margin:0;">Subject hint<input type="text" class="step-subject" placeholder="e.g. Re: or Quick question" value="${_esc(step.subject_hint || '')}" /></label>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
      <label style="margin:0;">
        ✍️ AI Instructions
        <span style="font-size:11px;color:var(--muted);margin-left:4px;">what angle / tone to use</span>
        <textarea class="step-instructions" rows="4" placeholder="e.g. Short 2-line follow-up. Mention their industry pain point. Be direct, no fluff.">${_esc(step.instructions || '')}</textarea>
      </label>
      <label style="margin:0;">
        📧 Sample Email
        <span style="font-size:11px;color:var(--muted);margin-left:4px;">AI mirrors this style</span>
        <textarea class="step-sample" rows="4" placeholder="Paste a real follow-up email you like. The AI will match its length, tone and structure — not copy the content.">${_esc(step.sample_email || '')}</textarea>
      </label>
    </div>`;
  container.appendChild(div);
}

function _renumberSteps() {
  document.querySelectorAll('#seq-steps-container .panel strong').forEach((el, i) => {
    el.textContent = `Step ${i + 1}`;
  });
}

// Make these accessible from inline onclick handlers
window.seqEdit   = (id) => _showForm(_sequences.find(s => s.id === id));
window.seqDelete = async (id) => {
  if (!confirm('Delete this sequence? All active enrollments will be stopped.')) return;
  try {
    await seqAPI.remove(id);
    toast('Sequence deleted', 'success');
    loadSequences();
  } catch (err) { toast(err.message, 'error'); }
};
window._renumberSteps = _renumberSteps;

async function _saveSequence() {
  const name  = document.getElementById('seq-name-input').value.trim();
  if (!name) { toast('Please enter a sequence name', 'error'); return; }

  const stepEls = document.querySelectorAll('#seq-steps-container .panel');
  const steps = Array.from(stepEls).map(el => ({
    delay_days:   parseInt(el.querySelector('.step-delay')?.value || '3', 10),
    subject_hint: el.querySelector('.step-subject')?.value.trim() || '',
    instructions: el.querySelector('.step-instructions')?.value.trim() || '',
    sample_email: el.querySelector('.step-sample')?.value.trim() || '',
  }));

  if (!steps.length) { toast('Add at least one step', 'error'); return; }

  const body = {
    name,
    description: document.getElementById('seq-desc-input').value.trim(),
    steps,
    is_active: true,
  };

  try {
    if (_editingId) {
      await seqAPI.update(_editingId, body);
      toast('Sequence updated ✓', 'success');
    } else {
      await seqAPI.create(body);
      toast('Sequence created ✓', 'success');
    }
    _hideForm();
    loadSequences();
  } catch (err) {
    toast(err.message, 'error');
  }
}

// ── Utility ───────────────────────────────────────────────────────────────────

function _esc(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
