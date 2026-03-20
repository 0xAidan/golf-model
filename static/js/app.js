/**
 * Golf Model Dashboard — main entry script
 * Fetches state from /api/dashboard/state, runs prediction/autoresearch, promotes candidates.
 */

function escapeHtml(s) {
  if (!s) return '';
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

function parseBackendDate(value) {
  if (!value) return null;
  if (value instanceof Date) return value;
  if (typeof value !== 'string') return new Date(value);
  const raw = value.trim();
  if (!raw) return null;

  // Backend often emits UTC-naive strings: "YYYY-MM-DD HH:MM:SS"
  const naiveMatch = raw.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.\d+)?$/);
  if (naiveMatch) {
    return new Date(naiveMatch[1] + 'T' + naiveMatch[2] + 'Z');
  }
  return new Date(raw);
}

function formatTime(value) {
  const parsed = parseBackendDate(value);
  if (!parsed || Number.isNaN(parsed.getTime())) return value || 'Never';
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  }).format(parsed) + ' ET';
}

const APP_STATE = {
  recentRuns: [],
  recentCandidates: [],
  autoresearchStatus: null,
  runRoiCache: new Map(),
  watchlist: new Set(),
};

let autoresearchPollTimer = null;

function setAutoresearchPollingInterval(ms) {
  if (autoresearchPollTimer) {
    window.clearInterval(autoresearchPollTimer);
  }
  autoresearchPollTimer = window.setInterval(async function () {
    await Promise.all([
      loadAutoresearchStatus(),
      loadAutoresearchRuns(),
      loadBestCandidates(),
    ]);
  }, ms);
}

function toFiniteNumber(value) {
  if (value == null) return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed || trimmed === '—' || trimmed.toLowerCase() === 'n/a') return null;
    const cleaned = trimmed.replace(/[%,$+]/g, '').replace(/,/g, '');
    const parsed = Number.parseFloat(cleaned);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function formatPctDelta(value) {
  const num = toFiniteNumber(value);
  if (num == null) return '—';
  const abs = Math.abs(num);
  const decimals = abs >= 1 ? 2 : abs >= 0.1 ? 3 : 4;
  return (num >= 0 ? '+' : '') + num.toFixed(decimals) + '%';
}

function computeRunRoiDelta(run) {
  const direct = toFiniteNumber(run.roi_delta);
  if (direct != null) return direct;
  const candidateRoi = toFiniteNumber(run.candidate_roi ?? run.summary_metrics?.weighted_roi_pct);
  const baselineRoi = toFiniteNumber(run.baseline_roi ?? run.baseline_summary_metrics?.weighted_roi_pct);
  if (candidateRoi != null && baselineRoi != null) return candidateRoi - baselineRoi;
  return null;
}

function computeCandidateConfidence(run) {
  let score = 50;
  const roiDelta = computeRunRoiDelta(run);
  const clvDelta = toFiniteNumber(run.clv_delta);
  if (roiDelta != null) score += Math.max(-25, Math.min(25, roiDelta * 1.5));
  if (clvDelta != null) score += Math.max(-15, Math.min(15, clvDelta * 250));
  if (run.guardrail_results && run.guardrail_results.passed) score += 10;
  if (run.is_positive_test) score += 8;
  if (String(run.decision || '').toLowerCase() === 'discarded') score -= 12;
  return Math.max(5, Math.min(98, Math.round(score)));
}

function initMainTabs() {
  const tabBtns = document.querySelectorAll('.main-tab');
  const panels = document.querySelectorAll('.tab-panel');
  if (!tabBtns.length || !panels.length) return;

  tabBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      const targetId = btn.getAttribute('aria-controls');
      if (!targetId) return;
      tabBtns.forEach(function (b) {
        b.classList.remove('is-active');
        b.setAttribute('aria-selected', 'false');
        b.setAttribute('tabindex', '-1');
      });
      panels.forEach(function (p) {
        p.classList.remove('is-active');
        p.hidden = true;
      });
      btn.classList.add('is-active');
      btn.setAttribute('aria-selected', 'true');
      btn.setAttribute('tabindex', '0');
      const targetPanel = document.getElementById(targetId);
      if (targetPanel) {
        targetPanel.classList.add('is-active');
        targetPanel.hidden = false;
        if (targetId === 'tab-autoresearch') {
          loadAutoresearchPareto();
        }
      }
    });
  });
}

function renderWatchlist() {
  const list = document.getElementById('watchlistItems');
  if (!list) return;
  const items = Array.from(APP_STATE.watchlist);
  if (!items.length) {
    list.innerHTML = '<div class="status info">No pinned players yet.</div>';
    return;
  }
  list.innerHTML = items.map(function (name) {
    return '<div class="run-item"><div class="run-item-head"><h4>' + escapeHtml(name) + '</h4>' +
      '<button type="button" class="btn btn-secondary btn-sm" data-action="remove-watch" data-player="' + escapeHtml(name) + '">Remove</button></div></div>';
  }).join('');
}

async function loadStatus() {
  const liveEl = document.getElementById('liveModel');
  const researchEl = document.getElementById('researchModel');
  const lastRunEl = document.getElementById('lastRun');
  const statusLineEl = document.getElementById('statusLine');
  if (!statusLineEl && !liveEl) return;

  try {
    const resp = await fetch('/api/dashboard/state');
    const state = await resp.json();
    const live = state.effective_live_weekly_model || {};
    const research = state.effective_research_champion || {};
    const ar = state.autoresearch || {};

    if (statusLineEl) {
      statusLineEl.textContent =
        'Live: ' + (live.name || 'none') + ' | Research champion: ' + (research.name || 'none') + ' | Last autoresearch: ' + formatTime(ar.last_finished_at);
    }
    if (liveEl) liveEl.textContent = live.name || '—';
    if (researchEl) researchEl.textContent = research.name || '—';
    if (lastRunEl) lastRunEl.textContent = ar.last_finished_at ? formatTime(ar.last_finished_at) : '—';
  } catch (_) {
    if (statusLineEl) statusLineEl.textContent = 'Could not load status.';
    if (liveEl) liveEl.textContent = '—';
    if (researchEl) researchEl.textContent = '—';
    if (lastRunEl) lastRunEl.textContent = '—';
  }
}

async function runPrediction() {
  const btn = document.getElementById('runPredictionBtn');
  const resultEl = document.getElementById('predResult');
  const viewerEl = document.getElementById('predCardViewer');
  const downloadBtn = document.getElementById('downloadCardBtn');
  if (!btn || !resultEl || !viewerEl) return;

  btn.disabled = true;
  btn.classList.add('is-loading');
  resultEl.style.display = 'block';
  resultEl.textContent = 'Running prediction…';
  resultEl.className = 'result';
  viewerEl.style.display = 'none';
  viewerEl.innerHTML = '';
  if (downloadBtn) downloadBtn.style.display = 'none';

  try {
    const modeSelect = document.getElementById('predictionMode');
    const selectedMode = modeSelect ? modeSelect.value : 'full';
    const resp = await fetch('/api/simple/upcoming-prediction', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tour: 'pga', mode: selectedMode }),
    });
    const data = await resp.json();
    if (data.error || (data.errors && data.errors.length)) {
      resultEl.textContent = 'Error: ' + (data.error || (data.errors && data.errors.join(' ')) || 'Unknown');
      resultEl.classList.add('status', 'error');
      return;
    }
    resultEl.textContent = 'Done. Event: ' + (data.event_name || '—') + ' | Field: ' + (data.field_size ?? '—');
    resultEl.classList.add('status', 'success');

    let cardMarkdown = data.card_content;
    if (!cardMarkdown && (data.card_content_path || data.output_file || data.card_filepath)) {
      const path = data.card_content_path || data.output_file || data.card_filepath;
      const pathForApi = path.startsWith('output/') ? path : 'output/' + path.replace(/^.*[/]output[/]?/, '');
      const contentResp = await fetch('/api/output/content?path=' + encodeURIComponent(pathForApi));
      const contentData = await contentResp.json();
      cardMarkdown = contentData.error ? null : (contentData.content || null);
    }

    if (cardMarkdown) {
      window.lastCardMarkdown = cardMarkdown;
      window.lastCardEventName = (data.event_name || 'prediction_card')
        .replace(/[^a-zA-Z0-9\s-]/g, '')
        .replace(/\s+/g, '_')
        .toLowerCase();
      viewerEl.style.display = 'block';
      viewerEl.innerHTML =
        typeof marked !== 'undefined' && marked.parse ? marked.parse(cardMarkdown) : escapeHtml(cardMarkdown);
      if (downloadBtn) downloadBtn.style.display = 'inline-block';
    } else {
      window.lastCardMarkdown = null;
      if (downloadBtn) downloadBtn.style.display = 'none';
    }
    loadStatus();
  } catch (err) {
    resultEl.textContent = 'Error: ' + err.message;
    resultEl.classList.add('status', 'error');
  } finally {
    btn.disabled = false;
    btn.classList.remove('is-loading');
  }
}

function downloadCard() {
  const md = window.lastCardMarkdown;
  if (!md) return;
  const base = (window.lastCardEventName || 'prediction_card').replace(/[^a-zA-Z0-9_-]/g, '_');
  const now = new Date();
  const ymd =
    now.getFullYear() +
    String(now.getMonth() + 1).padStart(2, '0') +
    String(now.getDate()).padStart(2, '0');
  const filename = base + '_' + ymd + '.md';
  const blob = new Blob([md], { type: 'text/markdown' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
}

async function gradeLastEvent() {
  const btn = document.getElementById('gradeLastEventBtn');
  const resultEl = document.getElementById('gradeResult');
  if (!btn || !resultEl) return;

  btn.disabled = true;
  btn.classList.add('is-loading');
  resultEl.style.display = 'block';
  resultEl.textContent = 'Grading last event…';
  resultEl.className = 'result';

  try {
    const resp = await fetch('/api/grade-tournament', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const data = await resp.json();
    if (data.error) {
      resultEl.textContent = 'Error: ' + data.error;
      resultEl.classList.add('status', 'error');
      return;
    }
    const scoring = data.steps && data.steps.scoring ? data.steps.scoring : {};
    const profit = scoring.total_profit || 0;
    const profitStr = profit >= 0 ? '+' + profit.toFixed(2) : profit.toFixed(2);
    resultEl.textContent =
      'Graded: ' + (data.event_id || '—') +
      ' | Picks: ' + (scoring.total_picks || 0) +
      ' | W/L: ' + (scoring.wins || 0) + '/' + (scoring.losses || 0) +
      ' | P/L: ' + profitStr + 'u';
    resultEl.classList.add('status', 'success');
  } catch (err) {
    resultEl.textContent = 'Grading failed: ' + err.message;
    resultEl.classList.add('status', 'error');
  } finally {
    btn.disabled = false;
    btn.classList.remove('is-loading');
  }
}

async function runAutoresearch() {
  const btn = document.getElementById('runAutoresearchBtn');
  const resultEl = document.getElementById('autoresearchResult');
  if (!btn || !resultEl) return;

  btn.disabled = true;
  btn.classList.add('is-loading');
  resultEl.style.display = 'block';
  resultEl.textContent = 'Running autoresearch (this may take a while)…';
  resultEl.className = 'result status loading';

  try {
    const resp = await fetch('/api/autoresearch/run-once', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope: 'global', max_candidates: 3 }),
    });
    if (!resp.ok) {
      const errData = await resp.json().catch(function () { return {}; });
      throw new Error(errData.error || 'Server error (' + resp.status + ')');
    }
    const data = await resp.json();
    let msg = data.error
      ? 'Error: ' + data.error
      : 'Cycle complete. Proposals evaluated: ' + (data.proposals_evaluated ?? '—');
    if (data.data_health) {
      const dh = data.data_health;
      msg += ' | Guardrail mode: ' + (data.guardrail_mode || '—');
      msg += ' | Data: events ' + (dh.event_count ?? '—') + ', PIT rows ' + (dh.pit_rolling_stats_rows ?? '—');
      if (dh.warnings && dh.warnings.length) {
        msg += '\nNote: ' + dh.warnings.join(' ');
      }
    }
    resultEl.textContent = msg;
    resultEl.className = data.error ? 'result status error' : 'result status success';
    await loadAutoresearchStatus();
    await loadAutoresearchRuns();
    await loadBestCandidates();
    loadStatus();
  } catch (err) {
    resultEl.textContent = 'Error: ' + err.message;
    resultEl.className = 'result status error';
  } finally {
    btn.disabled = false;
    btn.classList.remove('is-loading');
  }
}

async function startAutoresearchEngine() {
  const startBtn = document.getElementById('startAutoresearchBtn');
  const resultEl = document.getElementById('autoresearchResult');
  if (!startBtn || !resultEl) return;

  startBtn.disabled = true;
  startBtn.classList.add('is-loading');
  resultEl.style.display = 'block';
  resultEl.textContent = 'Starting autoresearch engine...';
  resultEl.className = 'result status loading';

  try {
    const engineModeEl = document.getElementById('engineModeSelect');
    const studyInp = document.getElementById('optunaStudyNameInput');
    const nTrialsEl = document.getElementById('optunaNTrialsInput');
    const engineMode = engineModeEl ? engineModeEl.value : 'research_cycle';
    const studyName = studyInp && studyInp.value.trim() ? studyInp.value.trim() : undefined;
    const ot = nTrialsEl
      ? Math.max(1, Math.min(50, parseInt(nTrialsEl.value || '3', 10)))
      : 3;
    const resp = await fetch('/api/autoresearch/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scope: 'global',
        interval_seconds: 300,
        max_candidates: 5,
        engine_mode: engineMode,
        optuna_study_name: studyName,
        optuna_trials_per_cycle: ot,
      }),
    });
    if (!resp.ok) {
      const errData = await resp.json().catch(function () { return {}; });
      throw new Error(errData.error || 'Server error (' + resp.status + ')');
    }
    const data = await resp.json();
    const running = data && data.optimizer && data.optimizer.running;
    resultEl.textContent = running
      ? 'Autoresearch engine started. Running every 5 minutes with 5 candidates per cycle.'
      : 'Start request returned, but engine is not running.';
    resultEl.className = running ? 'result status success' : 'result status error';
    await loadAutoresearchStatus();
    await loadAutoresearchRuns();
    await loadBestCandidates();
    loadStatus();
  } catch (err) {
    resultEl.textContent = 'Error: ' + err.message;
    resultEl.className = 'result status error';
  } finally {
    startBtn.disabled = false;
    startBtn.classList.remove('is-loading');
  }
}

async function resetAutoresearchState() {
  const btn = document.getElementById('resetAutoresearchBtn');
  const resultEl = document.getElementById('autoresearchResult');
  if (!btn || !resultEl) return;

  btn.disabled = true;
  btn.classList.add('is-loading');
  resultEl.style.display = 'block';
  resultEl.textContent = 'Resetting research state...';
  resultEl.className = 'result status loading';

  try {
    const resp = await fetch('/api/autoresearch/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    if (!resp.ok) {
      const errData = await resp.json().catch(function () { return {}; });
      throw new Error(errData.error || 'Server error (' + resp.status + ')');
    }
    const data = await resp.json();
    resultEl.textContent = data.error ? 'Error: ' + data.error : (data.message || 'Research state reset.');
    resultEl.className = data.error ? 'result status error' : 'result status success';
    await loadAutoresearchStatus();
    await loadAutoresearchRuns();
    await loadBestCandidates();
    loadStatus();
  } catch (err) {
    resultEl.textContent = 'Error: ' + err.message;
    resultEl.className = 'result status error';
  } finally {
    btn.disabled = false;
    btn.classList.remove('is-loading');
  }
}

async function stopAutoresearchEngine() {
  const stopBtn = document.getElementById('stopAutoresearchBtn');
  const resultEl = document.getElementById('autoresearchResult');
  if (!stopBtn || !resultEl) return;

  stopBtn.disabled = true;
  stopBtn.classList.add('is-loading');
  resultEl.style.display = 'block';
  resultEl.textContent = 'Stopping autoresearch engine...';
  resultEl.className = 'result status loading';

  try {
    const resp = await fetch('/api/autoresearch/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    if (!resp.ok) {
      const errData = await resp.json().catch(function () { return {}; });
      throw new Error(errData.error || 'Server error (' + resp.status + ')');
    }
    const data = await resp.json();
    const running = data && data.status && data.status.running;
    resultEl.textContent = running ? 'Engine is still running.' : 'Autoresearch engine stopped.';
    resultEl.className = running ? 'result status error' : 'result status success';
    await loadAutoresearchStatus();
    await loadAutoresearchRuns();
    loadStatus();
  } catch (err) {
    resultEl.textContent = 'Error: ' + err.message;
    resultEl.className = 'result status error';
  } finally {
    stopBtn.disabled = false;
    stopBtn.classList.remove('is-loading');
  }
}

async function loadAutoresearchStatus() {
  const statusEl = document.getElementById('autoresearchEngineStatus');
  const startBtn = document.getElementById('startAutoresearchBtn');
  const stopBtn = document.getElementById('stopAutoresearchBtn');
  if (!statusEl) return;

  try {
    const resp = await fetch('/api/autoresearch/status');
    if (!resp.ok) throw new Error('Server error (' + resp.status + ')');
    const data = await resp.json();
    const status = data.status || {};
    const running = !!status.running;
    const state = status.state || (running ? 'running' : 'idle');
    const runCount = status.run_count || 0;
    const intervalSeconds = status.interval_seconds || 0;
    const lastFinished = status.last_finished_at ? formatTime(status.last_finished_at) : 'Never';
    const lastError = status.last_error || '';
    const isDiskIO = lastError && /disk I\/O|I\/O error/i.test(lastError);

    statusEl.style.display = 'block';
    statusEl.className = 'ar-status-badge' + (running ? ' is-running' : (lastError ? ' is-error' : ''));
    statusEl.textContent =
      'Engine: ' + state +
      ' · Runs: ' + runCount +
      ' · Interval: ' + intervalSeconds + 's' +
      ' · Last: ' + lastFinished +
      (lastError ? ' · Error: ' + lastError : '');
    if (isDiskIO && statusEl.title !== 'dismissed') {
      statusEl.title = 'Often caused by: project in iCloud/synced folder, another app using the DB, or full disk. Move data/ off cloud sync and avoid other processes using golf.db.';
    } else if (!isDiskIO) {
      statusEl.title = '';
    }

    if (startBtn) startBtn.disabled = running;
    if (stopBtn) stopBtn.disabled = !running;

    APP_STATE.autoresearchStatus = status;
    updateSinceStartSection();
    setAutoresearchPollingInterval(running ? 5000 : 15000);
    loadAutoresearchSettings();
  } catch (err) {
    statusEl.style.display = 'block';
    statusEl.className = 'result status error';
    statusEl.textContent = 'Failed to load engine status: ' + err.message;
    setAutoresearchPollingInterval(15000);
  }
}

async function loadAutoresearchSettings() {
  const select = document.getElementById('guardrailModeSelect');
  if (!select) return;
  try {
    const resp = await fetch('/api/autoresearch/settings');
    if (!resp.ok) return;
    const data = await resp.json();
    const mode = (data.guardrail_mode || 'strict').toLowerCase();
    if (mode === 'strict' || mode === 'loose') {
      select.value = mode;
    }
    const engineSel = document.getElementById('engineModeSelect');
    if (engineSel && data.engine_mode) {
      engineSel.value = data.engine_mode === 'optuna' ? 'optuna' : 'research_cycle';
    }
    const llmCb = document.getElementById('useTheoryLlmCheckbox');
    if (llmCb) llmCb.checked = !!data.use_theory_engine_llm;
    const studyInp = document.getElementById('optunaStudyNameInput');
    if (studyInp && data.optuna_study_name) studyInp.value = data.optuna_study_name;
    const nTrials = document.getElementById('optunaNTrialsInput');
    if (nTrials && data.optuna_trials_per_cycle != null) {
      nTrials.value = String(Math.max(1, Math.min(50, parseInt(data.optuna_trials_per_cycle, 10) || 3)));
    }
  } catch (err) {
    select.value = 'strict';
  }
}

function handleEngineModeChange() {
  const select = document.getElementById('engineModeSelect');
  if (!select) return;
  fetch('/api/autoresearch/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ engine_mode: select.value }),
  })
    .then(function (r) { return r.ok ? r.json() : null; })
    .catch(function () {});
}

function handleTheoryLlmChange() {
  const cb = document.getElementById('useTheoryLlmCheckbox');
  if (!cb) return;
  fetch('/api/autoresearch/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ use_theory_engine_llm: cb.checked }),
  })
    .then(function (r) { return r.ok ? r.json() : null; })
    .catch(function () {});
}

function handleOptunaStudyBlur() {
  const inp = document.getElementById('optunaStudyNameInput');
  if (!inp || !inp.value.trim()) return;
  fetch('/api/autoresearch/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ optuna_study_name: inp.value.trim().slice(0, 120) }),
  }).catch(function () {});
}

async function loadAutoresearchPareto() {
  const container = document.getElementById('optunaParetoContainer');
  const studyInput = document.getElementById('optunaStudyNameInput');
  if (!container) return;
  const name = studyInput && studyInput.value.trim() ? studyInput.value.trim() : '';
  const q = name ? '?study_name=' + encodeURIComponent(name) : '';
  try {
    const resp = await fetch('/api/autoresearch/study' + q);
    const data = await resp.json();
    if (!data.ok) throw new Error(data.error || 'Failed to load study');
    const summ = data.summary || {};
    const rows = summ.pareto_trials || [];
    if (!rows.length) {
      container.innerHTML =
        '<div class="status info">No Pareto trials yet. Run trials (button below) or CLI: <code>python scripts/run_autoresearch_optuna.py</code>.</div>';
      return;
    }
    let html =
      '<table class="ar-pareto-table"><thead><tr><th>Trial</th><th>ROI</th><th>CLV</th><th>−cal</th><th>−DD</th><th>Promotable</th></tr></thead><tbody>';
    for (var i = 0; i < rows.length; i++) {
      const pt = rows[i];
      const vals = pt.values || [];
      const ua = pt.user_attrs || {};
      const roi = vals[0] != null ? Number(vals[0]).toFixed(2) : '—';
      const clv = vals[1] != null ? Number(vals[1]).toFixed(4) : '—';
      const ncal = vals[2] != null ? Number(vals[2]).toFixed(4) : '—';
      const ndd = vals[3] != null ? Number(vals[3]).toFixed(2) : '—';
      const prom = ua.feasible && ua.guardrail_passed ? 'yes' : 'no';
      html +=
        '<tr><td>' +
        escapeHtml(String(pt.number)) +
        '</td><td>' +
        roi +
        '</td><td>' +
        clv +
        '</td><td>' +
        ncal +
        '</td><td>' +
        ndd +
        '</td><td>' +
        prom +
        '</td></tr>';
    }
    html += '</tbody></table>';
    container.innerHTML = html;
  } catch (err) {
    container.innerHTML = '<div class="status error">' + escapeHtml(err.message) + '</div>';
  }
}

async function runOptunaTrialsFromDashboard() {
  const nEl = document.getElementById('optunaNTrialsInput');
  const container = document.getElementById('optunaParetoContainer');
  const studyInput = document.getElementById('optunaStudyNameInput');
  if (!container) return;
  const n = Math.max(1, Math.min(50, parseInt((nEl && nEl.value) || '5', 10)));
  const studyName = studyInput && studyInput.value.trim() ? studyInput.value.trim() : '';
  container.innerHTML =
    '<div class="status info">Running ' + n + ' trial(s) — walk-forward replay; may take several minutes.</div>';
  try {
    const resp = await fetch('/api/autoresearch/optuna/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        n_trials: n,
        years: [2024, 2025],
        study_name: studyName || undefined,
      }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || 'Request failed');
    await loadAutoresearchPareto();
  } catch (err) {
    container.innerHTML = '<div class="status error">' + escapeHtml(err.message) + '</div>';
  }
}

function handleGuardrailModeChange() {
  const select = document.getElementById('guardrailModeSelect');
  if (!select) return;
  const mode = select.value;
  fetch('/api/autoresearch/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ guardrail_mode: mode }),
  })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (data) {
      if (data && data.guardrail_mode) select.value = data.guardrail_mode;
    })
    .catch(function () {});
}

async function loadAutoresearchRuns() {
  const runsEl = document.getElementById('autoresearchRuns');
  if (!runsEl) return;
  try {
    const resp = await fetch('/api/autoresearch/runs?scope=global&limit=20');
    if (!resp.ok) {
      const errData = await resp.json().catch(function () { return {}; });
      throw new Error(errData.error || 'Server error (' + resp.status + ')');
    }
    const data = await resp.json();
    const runs = data.runs || [];
    APP_STATE.recentRuns = runs;
    if (!runs.length) {
      runsEl.innerHTML = '<div class="status info">Recent runs: none yet.</div>';
      return;
    }
    const badge = document.getElementById('runCountBadge');
    if (badge) badge.textContent = runs.length;
    let html = '';
    for (const r of runs) {
      const when = formatTime(r.created_at);
      const name = escapeHtml(r.display_title || r.candidate_name || 'Unnamed');
      const whatTested = escapeHtml((r.what_tested || r.hypothesis || '').slice(0, 140));
      const summary = escapeHtml((r.summary_reason || '').slice(0, 180));
      const nextHint = escapeHtml((r.next_attempt_hint || '').slice(0, 120));
      const verdictClass = r.is_positive_test ? 'positive' : (r.decision === 'blocked_by_guardrails' ? 'blocked' : 'neutral');
      const roiDelta = formatPctDelta(computeRunRoiDelta(r));
      const confidence = computeCandidateConfidence(r);
      const sm = r.summary_metrics || {};
      const bsm = r.baseline_summary_metrics || {};
      const roi = sm.weighted_roi_pct != null ? sm.weighted_roi_pct.toFixed(2) + '%' : '—';
      const baseRoi = bsm.weighted_roi_pct != null ? bsm.weighted_roi_pct.toFixed(2) + '%' : '—';
      const clv = sm.weighted_clv_avg != null ? sm.weighted_clv_avg.toFixed(4) : '—';
      const baseClv = bsm.weighted_clv_avg != null ? bsm.weighted_clv_avg.toFixed(4) : '—';
      const bets = sm.total_bets || '—';
      html +=
        '<article class="run-item run-item-expandable" tabindex="0" aria-label="Click to expand details">' +
        '<div class="run-item-head"><h4>' + name + '</h4>' +
        '<span class="run-verdict ' + verdictClass + '">' + escapeHtml(r.decision || '—') + '</span></div>' +
        '<div class="run-metrics">' +
        '<span class="metric-pill">ROI Δ ' + escapeHtml(roiDelta) + '</span>' +
        '<span class="metric-pill">' + confidence + '% conf</span>' +
        '<span class="run-item-meta">' + escapeHtml(when) + '</span>' +
        '</div>' +
        '<div class="confidence-wrap"><div class="confidence-track"><div class="confidence-fill" style="width:' + confidence + '%"></div></div></div>' +
        '<div class="run-detail" hidden>' +
        (whatTested ? '<div class="run-item-text"><strong>Tested:</strong> ' + whatTested + '</div>' : '') +
        (summary ? '<div class="run-item-text"><strong>Result:</strong> ' + summary + '</div>' : '') +
        (nextHint ? '<div class="run-item-text"><strong>Next:</strong> ' + nextHint + '</div>' : '') +
        '<div class="run-detail-metrics">' +
        '<span>ROI: ' + roi + ' vs ' + baseRoi + '</span>' +
        '<span>CLV: ' + clv + ' vs ' + baseClv + '</span>' +
        '<span>Bets: ' + bets + '</span>' +
        '</div>' +
        '</div>' +
        '</article>';
    }
    runsEl.innerHTML = html;
    if (APP_STATE.recentCandidates) {
      updateStatsBar(APP_STATE.recentCandidates, runs);
    }
  } catch (err) {
    runsEl.innerHTML = '<div class="status error">Failed to load recent runs: ' + err.message + '</div>';
  }
}

async function loadBestCandidates() {
  const container = document.getElementById('bestCandidates');
  if (!container) return;

  try {
    const resp = await fetch('/api/autoresearch/best-candidates?scope=global&limit=3');
    if (!resp.ok) {
      const errData = await resp.json().catch(function () { return {}; });
      throw new Error(errData.error || 'Server error (' + resp.status + ')');
    }
    const data = await resp.json();
    const candidates = data.candidates || [];
    APP_STATE.recentCandidates = candidates;
    const badge = document.getElementById('candidateCountBadge');
    if (badge) badge.textContent = candidates.length;
    if (!candidates.length) {
      container.innerHTML =
        '<div class="status info">No evaluated candidates yet. Run autoresearch first.</div>';
      updateStatsBar([], APP_STATE.recentRuns || []);
      return;
    }
    updateStatsBar(candidates, APP_STATE.recentRuns || []);
    let html = '';
    candidates.forEach(function (c, index) {
      const isLeader = index === 0;
      const sm = c.summary_metrics || {};
      const bsm = c.baseline_summary_metrics || {};
      const roi = sm.weighted_roi_pct != null ? sm.weighted_roi_pct.toFixed(2) + '%' : '—';
      const baseRoi = bsm.weighted_roi_pct != null ? bsm.weighted_roi_pct.toFixed(2) + '%' : '—';
      const roiDelta = (sm.weighted_roi_pct != null && bsm.weighted_roi_pct != null)
        ? formatPctDelta(sm.weighted_roi_pct - bsm.weighted_roi_pct)
        : '—';
      const clv = sm.weighted_clv_avg != null ? sm.weighted_clv_avg.toFixed(4) : '—';
      const passed = c.guardrail_results && c.guardrail_results.passed;
      const passedLabel = passed ? '✓ pass' : '✗ fail';
      const passedClass = passed ? 'val-positive' : 'val-negative';
      const hypothesis = escapeHtml((c.what_tested || c.hypothesis || '').slice(0, 100));
      const reportPath = c.artifact_content_path || c.artifact_markdown_path;
      const reportLink = reportPath
        ? ' · <a href="#" class="report-link link-secondary" data-path="' +
          escapeHtml(reportPath) + '" data-action="report">report</a>'
        : '';
      const itemClass = 'candidate-item' + (isLeader ? ' candidate-leader' : '');
      html +=
        '<article class="' + itemClass + '" data-id="' + escapeHtml(String(c.id)) + '" role="article" aria-label="' + (isLeader ? 'Best candidate' : 'Candidate ' + (index + 1)) + '">' +
        (isLeader ? '<div class="candidate-leader-badge" aria-hidden="true">Best</div>' : '') +
        '<h3 class="candidate-name">' + escapeHtml(c.name || 'Unnamed') + '</h3>' +
        (hypothesis ? '<div class="run-item-text">' + hypothesis + '</div>' : '') +
        '<div class="metrics">ROI ' + roi + ' <span style="opacity:.5">vs</span> ' + baseRoi +
        ' · Δ ' + roiDelta +
        ' · CLV ' + clv +
        ' · <span class="' + passedClass + '">' + passedLabel + '</span>' +
        reportLink +
        '</div>' +
        '<div class="candidate-actions">' +
        '<button type="button" class="btn btn-promote btn-sm" data-action="promote" data-id="' +
        escapeHtml(String(c.id)) + '">Promote</button>' +
        '<span id="promoteMsg' + escapeHtml(String(c.id)) + '" class="promote-msg"></span>' +
        '</div></article>';
    });
    container.innerHTML = html;
  } catch (err) {
    container.innerHTML =
      '<div class="status error">Failed to load candidates: ' + escapeHtml(err.message) + '</div>';
  }
}

function renderPromotionQueue(runs) {
  const queueEl = document.getElementById('promotionQueue');
  if (!queueEl) return;
  const promotable = (runs || []).filter(function (r) {
    const kept = String(r.decision || '').toLowerCase() === 'kept';
    const guardFail = String(r.guardrail_verdict || '').toLowerCase().includes('fail');
    const delta = computeRunRoiDelta(r);
    return kept && !guardFail && delta != null && delta > 0;
  }).slice(0, 8);

  if (!promotable.length) {
    queueEl.innerHTML = '<div class="status info">No promotable +EV runs yet.</div>';
    return;
  }
  let html = '';
  for (const run of promotable) {
    const delta = formatPctDelta(computeRunRoiDelta(run));
    const promoteId = run.proposal_id || run.id || '';
    const promoteLabel = run.proposal_id ? 'Promote' : 'Review';
    html += '<article class="run-item">' +
      '<div class="run-item-head"><h4>' + escapeHtml(run.candidate_name || 'candidate') + '</h4>' +
      '<span class="run-verdict positive">promotable</span></div>' +
      '<div class="run-metrics"><span class="metric-pill">ROI delta: ' + escapeHtml(delta) + '</span></div>' +
      '<div class="candidate-actions"><button type="button" class="btn btn-promote btn-sm" data-action="promote" data-id="' +
      escapeHtml(String(promoteId)) + '">' + promoteLabel + '</button></div>' +
      '</article>';
  }
  queueEl.innerHTML = html;
}

function _findBaseline(candidates, runs) {
  for (var i = 0; i < candidates.length; i++) {
    var b = candidates[i].baseline_summary_metrics || {};
    if (b.weighted_roi_pct != null) return b;
  }
  for (var j = 0; j < (runs || []).length; j++) {
    var br = runs[j].baseline_summary_metrics || {};
    if (br.weighted_roi_pct != null) return br;
  }
  return {};
}

function updateStatsBar(candidates, runs) {
  const setVal = function (id, text, cls) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = 'ar-stat-value' + (cls ? ' ' + cls : '');
  };
  if (!candidates.length && !(runs || []).length) {
    setVal('statBaselineRoi', '—'); setVal('statBestRoi', '—');
    setVal('statBaselineClv', '—'); setVal('statBestClv', '—');
    setVal('statTotalProposals', '—'); setVal('statPromotable', '0');
    updateSinceStartSection();
    return;
  }
  var bsm = _findBaseline(candidates, runs);
  var bestCandidate = candidates.length ? candidates[0] : null;
  var sm = bestCandidate ? (bestCandidate.summary_metrics || {}) : {};
  var baseRoi = bsm.weighted_roi_pct;
  var bestRoi = sm.weighted_roi_pct;
  setVal('statBaselineRoi', baseRoi != null ? baseRoi.toFixed(2) + '%' : '—', baseRoi != null ? (baseRoi > 0 ? 'val-positive' : 'val-negative') : '');
  setVal('statBestRoi', bestRoi != null ? bestRoi.toFixed(2) + '%' : '—', (bestRoi != null && baseRoi != null && bestRoi > baseRoi) ? 'val-positive' : '');
  setVal('statBaselineClv', bsm.weighted_clv_avg != null ? bsm.weighted_clv_avg.toFixed(4) : '—');
  setVal('statBestClv', sm.weighted_clv_avg != null ? sm.weighted_clv_avg.toFixed(4) : '—');
  setVal('statTotalProposals', String(candidates.length));
  var promotable = candidates.filter(function (c) {
    var cb = c.baseline_summary_metrics || {};
    return c.guardrail_results && c.guardrail_results.passed &&
      c.summary_metrics && c.summary_metrics.weighted_roi_pct != null &&
      cb.weighted_roi_pct != null &&
      c.summary_metrics.weighted_roi_pct > cb.weighted_roi_pct;
  });
  setVal('statPromotable', String(promotable.length), promotable.length > 0 ? 'val-positive' : '');
  var note = document.getElementById('promotionQueueNote');
  if (note) {
    note.textContent = promotable.length > 0
      ? promotable.length + ' ready to promote'
      : '';
  }
  updateSinceStartSection();
}

function updateSinceStartSection() {
  const setVal = function (id, text, cls) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = 'ar-stat-value' + (cls ? ' ' + cls : '');
  };
  const status = APP_STATE.autoresearchStatus || {};
  const atStartRoi = status.at_start_baseline_roi;
  const atStartClv = status.at_start_baseline_clv;
  const candidates = APP_STATE.recentCandidates || [];
  const best = candidates.length ? candidates[0] : null;
  const bestRoi = best && best.summary_metrics ? best.summary_metrics.weighted_roi_pct : null;
  const bestClv = best && best.summary_metrics ? best.summary_metrics.weighted_clv_avg : null;

  setVal('sinceStartRoi', atStartRoi != null ? atStartRoi.toFixed(2) + '%' : '—', atStartRoi != null ? (atStartRoi >= 0 ? 'val-positive' : 'val-negative') : '');
  setVal('sinceStartClv', atStartClv != null ? atStartClv.toFixed(4) : '—');
  setVal('sinceStartCurrentRoi', bestRoi != null ? bestRoi.toFixed(2) + '%' : '—', bestRoi != null ? (bestRoi >= 0 ? 'val-positive' : 'val-negative') : '');
  setVal('sinceStartCurrentClv', bestClv != null ? bestClv.toFixed(4) : '—');

  if (atStartRoi != null && bestRoi != null) {
    const deltaRoi = bestRoi - atStartRoi;
    const roiText = (deltaRoi >= 0 ? '+' : '') + deltaRoi.toFixed(2) + '%';
    setVal('sinceStartDeltaRoi', roiText, deltaRoi > 0 ? 'val-positive' : (deltaRoi < 0 ? 'val-negative' : ''));
  } else {
    setVal('sinceStartDeltaRoi', '—');
  }
  if (atStartClv != null && bestClv != null) {
    const deltaClv = bestClv - atStartClv;
    const clvText = (deltaClv >= 0 ? '+' : '') + deltaClv.toFixed(4);
    setVal('sinceStartDeltaClv', clvText, deltaClv > 0 ? 'val-positive' : (deltaClv < 0 ? 'val-negative' : ''));
  } else {
    setVal('sinceStartDeltaClv', '—');
  }
}

async function viewReport(path) {
  const resp = await fetch('/api/output/content?path=' + encodeURIComponent(path));
  const data = await resp.json();
  if (data.error) {
    alert(data.error);
    return;
  }
  const win = window.open('', '_blank');
  const content = typeof marked !== 'undefined' && marked.parse ? marked.parse(data.content || '') : '<pre>' + escapeHtml(data.content || '') + '</pre>';
  win.document.write(
    '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Report</title>' +
      '<link rel="stylesheet" href="/static/css/main.css">' +
      '</head><body class="wrap" style="padding:24px;">' +
      content +
      '</body></html>'
  );
  win.document.close();
}

async function promoteToLive(proposalId) {
  const msgEl = document.getElementById('promoteMsg' + proposalId);
  if (msgEl) msgEl.textContent = 'Promoting…';

  try {
    const resp = await fetch('/api/model-registry/promote-proposal-to-live', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proposal_id: proposalId, scope: 'global', reviewer: 'dashboard' }),
    });
    const data = await resp.json();
    if (msgEl) {
      if (data.ok) msgEl.textContent = 'Promoted.';
      else
        msgEl.textContent =
          (data.blocked_reason && data.blocked_reason.length
            ? 'Blocked: ' + data.blocked_reason.join(', ')
            : data.error || 'Failed');
    }
    loadStatus();
    loadBestCandidates();
  } catch (err) {
    if (msgEl) msgEl.textContent = 'Error: ' + err.message;
  }
}

function openTools() {
  const overlay = document.getElementById('toolsOverlay');
  if (overlay) {
    overlay.classList.add('is-open');
    overlay.setAttribute('aria-hidden', 'false');
    const firstFocus = overlay.querySelector('button, [href], input, select');
    if (firstFocus) firstFocus.focus();
  }
}

function closeTools() {
  const overlay = document.getElementById('toolsOverlay');
  if (overlay) {
    overlay.classList.remove('is-open');
    overlay.setAttribute('aria-hidden', 'true');
  }
}

function initTools() {
  const overlay = document.getElementById('toolsOverlay');
  const openBtn = document.getElementById('toolsOpenBtn');
  const closeBtn = document.getElementById('toolsCloseBtn');
  if (openBtn) {
    openBtn.addEventListener('click', function (e) {
      e.preventDefault();
      openTools();
    });
  }
  if (closeBtn) closeBtn.addEventListener('click', closeTools);
  if (overlay) {
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) closeTools();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && overlay.classList.contains('is-open')) closeTools();
    });
  }
}

function initCommandMenu() {
  const dialog = document.getElementById('commandMenuDialog');
  const openBtn = document.getElementById('commandMenuBtn');
  const closeBtn = document.getElementById('commandMenuCloseBtn');
  if (!dialog) return;

  const open = function () {
    if (typeof dialog.showModal === 'function') dialog.showModal();
  };
  const close = function () {
    if (typeof dialog.close === 'function' && dialog.open) dialog.close();
  };

  if (openBtn) {
    openBtn.addEventListener('click', function () {
      open();
    });
  }
  if (closeBtn) {
    closeBtn.addEventListener('click', function () {
      close();
    });
  }

  dialog.addEventListener('click', function (e) {
    if (e.target === dialog) close();
  });

  document.addEventListener('keydown', function (e) {
    const isCmdK = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k';
    if (isCmdK) {
      e.preventDefault();
      open();
      return;
    }
    if (e.key === 'Escape' && dialog.open) close();
  });

  dialog.addEventListener('click', function (e) {
    const button = e.target.closest('button[data-command]');
    if (!button) return;
    const cmd = button.getAttribute('data-command');
    if (cmd === 'prediction') runPrediction();
    if (cmd === 'matchups-only') {
      var modeSelect = document.getElementById('predictionMode');
      if (modeSelect) modeSelect.value = 'matchups-only';
      runPrediction();
    }
    if (cmd === 'grade-event') gradeLastEvent();
    if (cmd === 'run-once') runAutoresearch();
    if (cmd === 'start-engine') startAutoresearchEngine();
    if (cmd === 'view-grading') {
      var gradingTab = document.getElementById('tab-btn-grading');
      if (gradingTab) gradingTab.click();
    }
    if (cmd === 'reset-state') resetAutoresearchState();
    close();
  });
}

function showPanel(panelKey, opts) {
  const options = opts || {};
  const tabs = document.querySelectorAll('.workspace-tab');
  const panels = document.querySelectorAll('.workspace-panel');
  tabs.forEach(function (tab) {
    tab.classList.toggle('is-active', tab.getAttribute('data-panel') === panelKey);
  });
  panels.forEach(function (panel) {
    panel.classList.toggle('is-active', panel.getAttribute('data-panel') === panelKey);
  });
  if (options.openOverlay) openWorkspace();
}

function openWorkspace() {
  const overlay = document.getElementById('workspaceOverlay');
  if (!overlay) return;
  overlay.classList.add('is-open');
  overlay.setAttribute('aria-hidden', 'false');
}

function closeWorkspace() {
  const overlay = document.getElementById('workspaceOverlay');
  if (!overlay) return;
  overlay.classList.remove('is-open');
  overlay.setAttribute('aria-hidden', 'true');
}

function initWorkspaceOverlay() {
  const openBtn = document.getElementById('workspaceOpenBtn');
  const hideBtn = document.getElementById('workspaceHideBtn');
  const closeBtn = document.getElementById('workspaceCloseBtn');
  const overlay = document.getElementById('workspaceOverlay');
  if (openBtn) openBtn.addEventListener('click', openWorkspace);
  if (hideBtn) hideBtn.addEventListener('click', closeWorkspace);
  if (closeBtn) closeBtn.addEventListener('click', closeWorkspace);
  if (overlay) {
    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) closeWorkspace();
    });
  }
  document.querySelectorAll('.workspace-tab').forEach(function (tab) {
    tab.addEventListener('click', function () {
      const panel = tab.getAttribute('data-panel');
      if (panel) showPanel(panel, { openOverlay: false });
    });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') closeWorkspace();
  });
}

document.addEventListener('click', function (e) {
  const expandable = e.target.closest('.run-item-expandable');
  if (expandable && !e.target.closest('button, a, .candidate-actions')) {
    const detail = expandable.querySelector('.run-detail');
    if (detail) {
      const isOpen = !detail.hidden;
      detail.hidden = isOpen;
      expandable.classList.toggle('is-expanded', !isOpen);
    }
    return;
  }
  const reportLink = e.target.closest('.report-link');
  if (reportLink) {
    e.preventDefault();
    viewReport(reportLink.getAttribute('data-path'));
    return;
  }
  const promoteBtn = e.target.closest('[data-action="promote"]');
  if (promoteBtn && promoteBtn.dataset.id) {
    e.preventDefault();
    const parsedId = parseInt(promoteBtn.dataset.id, 10);
    if (Number.isFinite(parsedId) && parsedId > 0) {
      promoteToLive(parsedId);
    }
  }
  const removeWatchBtn = e.target.closest('[data-action="remove-watch"]');
  if (removeWatchBtn && removeWatchBtn.dataset.player) {
    APP_STATE.watchlist.delete(removeWatchBtn.dataset.player);
    renderWatchlist();
  }
});

document.addEventListener('dragstart', function (e) {
  const card = e.target.closest('.candidate-item, .run-item');
  if (!card) return;
  const player = card.getAttribute('data-player') || card.querySelector('h4')?.textContent || '';
  if (!player || !e.dataTransfer) return;
  e.dataTransfer.effectAllowed = 'copy';
  e.dataTransfer.setData('text/plain', player);
});

document.addEventListener('DOMContentLoaded', function () {
  loadStatus();
  loadBestCandidates();
  loadAutoresearchStatus();
  loadAutoresearchRuns();
  initMainTabs();
  initCommandMenu();

  const runPredictionBtn = document.getElementById('runPredictionBtn');
  const runAutoresearchBtn = document.getElementById('runAutoresearchBtn');
  const startAutoresearchBtn = document.getElementById('startAutoresearchBtn');
  const stopAutoresearchBtn = document.getElementById('stopAutoresearchBtn');
  const resetAutoresearchBtn = document.getElementById('resetAutoresearchBtn');
  const downloadCardBtn = document.getElementById('downloadCardBtn');
  const gradeLastEventBtn = document.getElementById('gradeLastEventBtn');
  if (runPredictionBtn) runPredictionBtn.addEventListener('click', runPrediction);
  if (gradeLastEventBtn) gradeLastEventBtn.addEventListener('click', gradeLastEvent);
  var gradeLastEventBtnTab = document.getElementById('gradeLastEventBtnTab');
  if (gradeLastEventBtnTab) gradeLastEventBtnTab.addEventListener('click', gradeLastEvent);
  if (runAutoresearchBtn) runAutoresearchBtn.addEventListener('click', runAutoresearch);
  if (startAutoresearchBtn) startAutoresearchBtn.addEventListener('click', startAutoresearchEngine);
  if (stopAutoresearchBtn) stopAutoresearchBtn.addEventListener('click', stopAutoresearchEngine);
  if (resetAutoresearchBtn) resetAutoresearchBtn.addEventListener('click', resetAutoresearchState);
  if (downloadCardBtn) downloadCardBtn.addEventListener('click', downloadCard);
  const guardrailModeSelect = document.getElementById('guardrailModeSelect');
  if (guardrailModeSelect) guardrailModeSelect.addEventListener('change', handleGuardrailModeChange);
  const engineModeSelect = document.getElementById('engineModeSelect');
  if (engineModeSelect) engineModeSelect.addEventListener('change', handleEngineModeChange);
  const useTheoryLlmCheckbox = document.getElementById('useTheoryLlmCheckbox');
  if (useTheoryLlmCheckbox) useTheoryLlmCheckbox.addEventListener('change', handleTheoryLlmChange);
  const optunaStudyNameInput = document.getElementById('optunaStudyNameInput');
  if (optunaStudyNameInput) optunaStudyNameInput.addEventListener('blur', handleOptunaStudyBlur);
  const loadParetoBtn = document.getElementById('loadParetoBtn');
  if (loadParetoBtn) loadParetoBtn.addEventListener('click', loadAutoresearchPareto);
  const runOptunaTrialsBtn = document.getElementById('runOptunaTrialsBtn');
  if (runOptunaTrialsBtn) runOptunaTrialsBtn.addEventListener('click', runOptunaTrialsFromDashboard);
  const revealEls = document.querySelectorAll('.reveal');
  if (revealEls.length && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) entry.target.classList.add('is-visible');
        });
      },
      { threshold: 0.1, rootMargin: '0px 0px -20px 0px' }
    );
    revealEls.forEach(function (el) {
      observer.observe(el);
    });
  }
});
