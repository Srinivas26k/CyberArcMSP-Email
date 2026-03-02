/**
 * pages/records.js — Database summary, CSV exports, backup/restore
 */
import { healthAPI, databaseAPI } from '../api.js';
import { toast } from '../toast.js';
import { setText } from '../utils.js';

export function init(register) {
  document.getElementById('restore-input')?.addEventListener('change', handleRestoreInput);

  document.getElementById('copy-migration-prompt-btn')?.addEventListener('click', function () {
    const text = document.getElementById('migration-prompt')?.value ?? '';
    navigator.clipboard.writeText(text).then(() => {
      this.textContent = 'Copied!';
      setTimeout(() => { this.textContent = 'Copy'; }, 2000);
    }).catch(() => toast('Could not copy — please select and copy manually.', 'warning'));
  });

  register('records', {
    onEnter: () => { loadRecords(); loadDbInfo(); },
    onLeave: () => {},
  });
}

async function loadRecords() {
  try {
    const s = await healthAPI.stats();
    setText('rec-leads',    String(s.total_leads    ?? '—'));
    setText('rec-pending',  String(s.pending        ?? '—'));
    setText('rec-sent',     String(s.sent           ?? '—'));
    setText('rec-replies',  String(s.replied        ?? '—'));
    setText('rec-failed',   String(s.failed         ?? '—'));
    setText('rec-accounts', String(s.active_accounts ?? '—'));
  } catch (e) {
    toast('Stats unavailable: ' + e.message, 'error');
  }
}

async function loadDbInfo() {
  try {
    const info = await databaseAPI.info();
    setText('db-path', info.db_path ?? '—');
    // size_mb is returned as a pre-formatted string (e.g. "0.05") by the API
    const sizeMb = info.size_mb != null ? parseFloat(info.size_mb) : null;
    setText('db-size', sizeMb != null && !isNaN(sizeMb) ? sizeMb.toFixed(2) + ' MB' : '—');
  } catch (err) {
    setText('db-path', 'Error: ' + err.message);
    setText('db-size', '—');
  }
}

function handleRestoreInput(e) {
  const file = e.target.files?.[0];
  if (!file) return;
  if (!file.name.endsWith('.db')) {
    toast('Only .db files are accepted.', 'warning');
    e.target.value = '';
    return;
  }
  const ok = confirm(
    `⚠️ Restore database from "${file.name}"?\n\n` +
    'This will overwrite your current data. The app will reload.\n' +
    'Make sure you have a backup before proceeding.'
  );
  if (!ok) { e.target.value = ''; return; }

  restoreDb(file);
}

async function restoreDb(file) {
  const btn = document.getElementById('restore-input');
  try {
    const fd = new FormData();
    fd.append('file', file);
    await databaseAPI.restore(fd);
    toast('Database restored! Reloading in 2 s…', 'success');
    setTimeout(() => location.reload(), 2000);
  } catch (err) {
    toast('Restore failed: ' + err.message, 'error');
  } finally {
    if (btn) btn.value = '';
  }
}
