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
  autoresearchSettings: null,
  optunaDashboard: null,
  simpleAutoresearch: null,
  autoresearchMode: 'simple',
  runRoiCache: new Map(),
  watchlist: new Set(),
  liveRefreshStatus: null,
  liveSnapshot: null,
  livePollMs: 15000,
};

let autoresearchPollTimer = null;
let liveRefreshPollTimer = null;

function isOptunaEngineMode() {
  const st = APP_STATE.autoresearchStatus || {};
  const cfg = APP_STATE.autoresearchSettings || {};
  const em = st.engine_mode || cfg.engine_mode;
  return em === 'optuna' || em === 'optuna_scalar';
}

function getAutoresearchEngineMode() {
  const st = APP_STATE.autoresearchStatus || {};
  const cfg = APP_STATE.autoresearchSettings || {};
  return st.engine_mode || cfg.engine_mode || 'research_cycle';
}

async function fetchOptunaStudyDashboard() {
  const note = document.getElementById('arOptunaStatsNote');
  if (!isOptunaEngineMode()) {
    APP_STATE.optunaDashboard = null;
    if (note) {
      note.style.display = 'none';
      note.textContent = '';
    }
    return;
  }
  const status = APP_STATE.autoresearchStatus || {};
  const em = getAutoresearchEngineMode();
  const studyKind = em === 'optuna_scalar' ? 'scalar' : 'mo';
  const moInp = document.getElementById('optunaStudyNameInput');
  const scInp = document.getElementById('optunaScalarStudyNameInput');
  const name =
    studyKind === 'scalar'
      ? (
          status.optuna_scalar_study_name ||
          (APP_STATE.autoresearchSettings && APP_STATE.autoresearchSettings.optuna_scalar_study_name) ||
          (scInp && scInp.value.trim()) ||
          ''
        ).trim()
      : (
          status.optuna_study_name ||
          (APP_STATE.autoresearchSettings && APP_STATE.autoresearchSettings.optuna_study_name) ||
          (moInp && moInp.value.trim()) ||
          ''
        ).trim();
  const q =
    '?study_kind=' +
    encodeURIComponent(studyKind) +
    (name ? '&study_name=' + encodeURIComponent(name) : '');
  try {
    const resp = await fetch('/api/autoresearch/study' + q);
    const data = await resp.json();
    if (!data.ok) throw new Error(data.error || 'study load failed');
    APP_STATE.optunaDashboard = data.dashboard || null;
    if (note) {
      note.style.display = 'block';
      note.textContent =
        studyKind === 'scalar'
          ? 'Optuna scalar: optimizes one objective (blended score or ROI per settings). Best ROI/CLV are maxima seen across trials in this study.'
          : 'Optuna MO: Best ROI / Best CLV are the maximum observed across completed walk-forward trials in this study (multi-objective exploration, not the ranked research-proposal list).';
    }
  } catch (err) {
    APP_STATE.optunaDashboard = null;
    if (note) {
      note.style.display = 'block';
      note.textContent = 'Could not load Optuna study metrics: ' + err.message;
    }
  }
}

function setAutoresearchPollingInterval(ms) {
  if (autoresearchPollTimer) {
    window.clearInterval(autoresearchPollTimer);
  }
  autoresearchPollTimer = window.setInterval(async function () {
    await loadSimpleAutoresearchStatus();
    await loadAutoresearchStatus();
    await loadAutoresearchRuns();
    await loadBestCandidates();
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

function formatIntervalLabel(seconds) {
  const num = toFiniteNumber(seconds);
  if (num == null) return 'Custom cadence';
  if (num % 60 === 0) {
    const minutes = num / 60;
    return 'Every ' + minutes + ' minute' + (minutes === 1 ? '' : 's');
  }
  return 'Every ' + num + ' seconds';
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

function getCurrentAutoresearchMode() {
  return APP_STATE.autoresearchMode || 'simple';
}

function setAutoresearchMode(mode) {
  const nextMode = mode === 'lab' ? 'lab' : 'simple';
  APP_STATE.autoresearchMode = nextMode;
  const buttons = document.querySelectorAll('[data-ar-mode]');
  const panels = document.querySelectorAll('.ar-mode-panel');
  buttons.forEach(function (button) {
    const isActive = button.getAttribute('data-ar-mode') === nextMode;
    button.classList.toggle('is-active', isActive);
    button.setAttribute('aria-selected', isActive ? 'true' : 'false');
    button.setAttribute('tabindex', isActive ? '0' : '-1');
  });
  panels.forEach(function (panel) {
    const isActive = panel.id === (nextMode === 'lab' ? 'arModeLab' : 'arModeSimple');
    panel.classList.toggle('is-active', isActive);
    panel.hidden = !isActive;
  });
  if (nextMode === 'lab') {
    loadAutoresearchPareto();
  }
}

function openAutoresearchTab(mode) {
  const autoresearchTab = document.getElementById('tab-btn-autoresearch');
  if (autoresearchTab) {
    autoresearchTab.click();
  }
  setAutoresearchMode(mode || 'simple');
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
          if (getCurrentAutoresearchMode() === 'lab') {
            loadAutoresearchPareto();
          }
        }
      }
    });
  });
}

function initAutoresearchModeTabs() {
  const buttons = document.querySelectorAll('[data-ar-mode]');
  if (!buttons.length) return;
  buttons.forEach(function (button) {
    button.addEventListener('click', function () {
      setAutoresearchMode(button.getAttribute('data-ar-mode') || 'simple');
    });
  });
  setAutoresearchMode(getCurrentAutoresearchMode());
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

function setLiveRefreshPollingInterval(ms) {
  APP_STATE.livePollMs = ms;
  if (liveRefreshPollTimer) {
    window.clearInterval(liveRefreshPollTimer);
  }
  liveRefreshPollTimer = window.setInterval(async function () {
    await loadLiveRefreshStatus();
    await loadLiveRefreshSnapshot();
  }, ms);
}

function renderTournamentTable(items, targetId, emptyMessage) {
  const el = document.getElementById(targetId);
  if (!el) return;
  if (!items || !items.length) {
    el.innerHTML = '<div class="status info">' + escapeHtml(emptyMessage) + '</div>';
    return;
  }
  let html = '<table><thead><tr><th>#</th><th>Player</th><th>Composite</th><th>Course Fit</th><th>Form</th><th>Momentum</th></tr></thead><tbody>';
  for (let i = 0; i < items.length; i++) {
    const row = items[i];
    html += '<tr>' +
      '<td>' + escapeHtml(String(row.rank || i + 1)) + '</td>' +
      '<td>' + escapeHtml(row.player || '—') + '</td>' +
      '<td>' + escapeHtml(row.composite != null ? Number(row.composite).toFixed(3) : '—') + '</td>' +
      '<td>' + escapeHtml(row.course_fit != null ? Number(row.course_fit).toFixed(3) : '—') + '</td>' +
      '<td>' + escapeHtml(row.form != null ? Number(row.form).toFixed(3) : '—') + '</td>' +
      '<td>' + escapeHtml(row.momentum != null ? Number(row.momentum).toFixed(3) : '—') + '</td>' +
      '</tr>';
  }
  html += '</tbody></table>';
  el.innerHTML = html;
}

function renderMatchupTable(items, targetId, emptyMessage) {
  const el = document.getElementById(targetId);
  if (!el) return;
  if (!items || !items.length) {
    el.innerHTML = '<div class="status info">' + escapeHtml(emptyMessage) + '</div>';
    return;
  }
  let html = '<table><thead><tr><th>Player</th><th>Opponent</th><th>Odds</th><th>Book</th><th>EV</th><th>Market</th></tr></thead><tbody>';
  for (let i = 0; i < items.length; i++) {
    const row = items[i];
    html += '<tr>' +
      '<td>' + escapeHtml(row.player || '—') + '</td>' +
      '<td>' + escapeHtml(row.opponent || '—') + '</td>' +
      '<td>' + escapeHtml(row.market_odds || '—') + '</td>' +
      '<td>' + escapeHtml(row.bookmaker || '—') + '</td>' +
      '<td>' + escapeHtml(row.ev != null ? Number(row.ev).toFixed(3) : '—') + '</td>' +
      '<td>' + escapeHtml(row.market_type || '—') + '</td>' +
      '</tr>';
  }
  html += '</tbody></table>';
  el.innerHTML = html;
}

function renderLiveSnapshot(snapshot, ageSeconds) {
  if (!snapshot) return;
  APP_STATE.liveSnapshot = snapshot;
  const modeEl = document.getElementById('liveCadenceMode');
  const updatedEl = document.getElementById('liveSnapshotUpdated');
  const ageEl = document.getElementById('liveSnapshotAge');
  if (modeEl) modeEl.textContent = snapshot.cadence_mode || '—';
  if (updatedEl) updatedEl.textContent = formatTime(snapshot.generated_at);
  if (ageEl) ageEl.textContent = ageSeconds != null ? String(ageSeconds) + 's' : '—';

  const live = snapshot.live_tournament || {};
  const upcoming = snapshot.upcoming_tournament || {};
  const liveMeta = document.getElementById('liveTournamentMeta');
  const liveStatus = document.getElementById('liveTournamentStatus');
  if (liveMeta) {
    liveMeta.textContent = (live.event_name || 'Unknown event') + ' · Field ' + (live.field_size != null ? live.field_size : '—');
  }
  if (liveStatus) {
    liveStatus.className = 'result status ' + (live.active ? 'success' : 'info');
    liveStatus.textContent = live.active
      ? 'Live window active. Snapshot auto-refresh is running.'
      : 'Live window not currently active. Showing latest available snapshot.';
  }

  const upcomingMeta = document.getElementById('upcomingTournamentMeta');
  const upcomingStatus = document.getElementById('upcomingTournamentStatus');
  if (upcomingMeta) {
    upcomingMeta.textContent = (upcoming.event_name || 'Upcoming event') + ' · Field ' + (upcoming.field_size != null ? upcoming.field_size : '—');
  }
  if (upcomingStatus) {
    upcomingStatus.className = 'result status info';
    upcomingStatus.textContent = 'Upcoming projections auto-refresh from the always-on runtime.';
  }

  renderTournamentTable(live.rankings, 'liveRankings', 'No live rankings yet.');
  renderMatchupTable(live.matchups, 'liveMatchups', 'No live matchup opportunities yet.');
  renderTournamentTable(upcoming.rankings, 'upcomingRankings', 'No upcoming rankings yet.');
  renderMatchupTable(upcoming.matchups, 'upcomingMatchups', 'No upcoming matchup opportunities yet.');
}

async function loadLiveRefreshSnapshot() {
  try {
    const resp = await fetch('/api/live-refresh/snapshot');
    if (!resp.ok) throw new Error('Server error (' + resp.status + ')');
    const data = await resp.json();
    if (!data.ok || !data.snapshot) return;
    renderLiveSnapshot(data.snapshot, data.age_seconds);
  } catch (_) {}
}

async function loadLiveRefreshStatus() {
  const opsResult = document.getElementById('liveRefreshOpsResult');
  try {
    const resp = await fetch('/api/live-refresh/status');
    if (!resp.ok) throw new Error('Server error (' + resp.status + ')');
    const data = await resp.json();
    const status = data.status || {};
    APP_STATE.liveRefreshStatus = status;
    const running = !!status.running;
    const isVisible = typeof document !== 'undefined' ? document.visibilityState === 'visible' : true;
    const pollMs = running ? (isVisible ? 5000 : 30000) : (isVisible ? 15000 : 60000);
    if (APP_STATE.livePollMs !== pollMs) {
      setLiveRefreshPollingInterval(pollMs);
    }
    const startBtn = document.getElementById('startLiveRefreshBtn');
    const stopBtn = document.getElementById('stopLiveRefreshBtn');
    if (startBtn) startBtn.disabled = running;
    if (stopBtn) stopBtn.disabled = !running;
    if (opsResult) {
      opsResult.style.display = 'block';
      opsResult.className = 'result status ' + (running ? 'success' : 'info');
      opsResult.textContent =
        'Live refresh ' + (running ? 'running' : 'stopped') +
        ' · mode ' + (status.cadence_mode || '—') +
        ' · next recompute ' + (status.next_recompute_at ? formatTime(status.next_recompute_at) : '—');
    }
  } catch (err) {
    if (opsResult) {
      opsResult.style.display = 'block';
      opsResult.className = 'result status error';
      opsResult.textContent = 'Could not load live refresh status: ' + err.message;
    }
  }
}

async function startLiveRefresh() {
  const opsResult = document.getElementById('liveRefreshOpsResult');
  try {
    if (opsResult) {
      opsResult.style.display = 'block';
      opsResult.className = 'result status loading';
      opsResult.textContent = 'Starting live refresh runtime…';
    }
    const resp = await fetch('/api/live-refresh/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || 'Request failed');
    await loadLiveRefreshStatus();
    await loadLiveRefreshSnapshot();
  } catch (err) {
    if (opsResult) {
      opsResult.style.display = 'block';
      opsResult.className = 'result status error';
      opsResult.textContent = 'Error: ' + err.message;
    }
  }
}

async function stopLiveRefresh() {
  const opsResult = document.getElementById('liveRefreshOpsResult');
  try {
    if (opsResult) {
      opsResult.style.display = 'block';
      opsResult.className = 'result status loading';
      opsResult.textContent = 'Stopping live refresh runtime…';
    }
    const resp = await fetch('/api/live-refresh/stop', { method: 'POST' });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || 'Request failed');
    await loadLiveRefreshStatus();
  } catch (err) {
    if (opsResult) {
      opsResult.style.display = 'block';
      opsResult.className = 'result status error';
      opsResult.textContent = 'Error: ' + err.message;
    }
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

async function gradeLastEvent(event) {
  const triggerBtn = event && event.currentTarget ? event.currentTarget : document.getElementById('gradeLastEventBtn');
  const primaryResult = document.getElementById('gradeResult');
  const tabResult = document.getElementById('gradeResultTab');
  const resultEls = [primaryResult, tabResult].filter(Boolean);
  if (!triggerBtn || !resultEls.length) return;

  triggerBtn.disabled = true;
  triggerBtn.classList.add('is-loading');
  resultEls.forEach(function (resultEl) {
    resultEl.style.display = 'block';
    resultEl.textContent = 'Grading last event…';
    resultEl.className = 'result';
  });

  try {
    const resp = await fetch('/api/grade-tournament', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const data = await resp.json();
    if (data.error) {
      resultEls.forEach(function (resultEl) {
        resultEl.textContent = 'Error: ' + data.error;
        resultEl.classList.add('status', 'error');
      });
      return;
    }
    const scoring = data.steps && data.steps.scoring ? data.steps.scoring : {};
    const profit = scoring.total_profit || 0;
    const profitStr = profit >= 0 ? '+' + profit.toFixed(2) : profit.toFixed(2);
    resultEls.forEach(function (resultEl) {
      resultEl.textContent =
        'Graded: ' + (data.event_id || '—') +
        ' | Picks: ' + (scoring.total_picks || 0) +
        ' | W/L: ' + (scoring.wins || 0) + '/' + (scoring.losses || 0) +
        ' | P/L: ' + profitStr + 'u';
      resultEl.classList.add('status', 'success');
    });
  } catch (err) {
    resultEls.forEach(function (resultEl) {
      resultEl.textContent = 'Grading failed: ' + err.message;
      resultEl.classList.add('status', 'error');
    });
  } finally {
    triggerBtn.disabled = false;
    triggerBtn.classList.remove('is-loading');
  }
}

function renderSimpleAutoresearchBest(best) {
  const container = document.getElementById('simpleAutoresearchBest');
  if (!container) return;
  if (!best) {
    container.className = 'ar-simple-empty';
    container.textContent = 'No completed tuning runs yet.';
    return;
  }
  const roi = best.roi_pct != null ? Number(best.roi_pct).toFixed(2) + '%' : '—';
  const clv = best.clv_avg != null ? Number(best.clv_avg).toFixed(4) : '—';
  const metric = best.metric_value != null ? Number(best.metric_value).toFixed(2) + '%' : '—';
  const label = best.guardrails_passed ? 'Best safe trial' : 'Best trial (blocked)';
  container.className = 'ar-simple-summary';
  container.innerHTML =
    '<div class="ar-simple-number">' + escapeHtml(metric) + '</div>' +
    '<div class="ar-simple-detail">' + escapeHtml(label) + ' #' + escapeHtml(String(best.trial_number ?? '—')) + '</div>' +
    '<div class="ar-simple-detail">ROI ' + escapeHtml(roi) + ' · CLV ' + escapeHtml(clv) + '</div>';
}

function renderSimpleAutoresearchRecent(attempts) {
  const container = document.getElementById('simpleAutoresearchRecent');
  if (!container) return;
  if (!attempts || !attempts.length) {
    container.className = 'ar-simple-empty';
    container.textContent = 'Recent attempts will show up here after a run.';
    return;
  }
  container.className = 'ar-simple-list';
  container.innerHTML = attempts.map(function (attempt) {
    const roi = attempt.roi_pct != null ? Number(attempt.roi_pct).toFixed(2) + '%' : '—';
    const clv = attempt.clv_avg != null ? Number(attempt.clv_avg).toFixed(4) : '—';
    const verdict = attempt.guardrails_passed ? 'Safe' : 'Blocked';
    return '<div class="ar-simple-list-item">' +
      '<div><strong>Trial #' + escapeHtml(String(attempt.trial_number ?? '—')) + '</strong> · ' + escapeHtml(verdict) + '</div>' +
      '<div class="ar-simple-list-meta">ROI ' + escapeHtml(roi) + ' · CLV ' + escapeHtml(clv) + '</div>' +
      '</div>';
  }).join('');
}

function updateSimpleAutoresearchUi(data) {
  if (!data) return;
  APP_STATE.simpleAutoresearch = data;
  const badge = document.getElementById('simpleAutoresearchBadge');
  const goal = document.getElementById('simpleAutoresearchGoal');
  const cadence = document.getElementById('simpleAutoresearchCadence');
  const headline = document.getElementById('simpleAutoresearchHeadline');
  const objective = document.getElementById('simpleAutoresearchObjective');
  const lastRun = document.getElementById('simpleAutoresearchLastRun');
  const error = document.getElementById('simpleAutoresearchError');
  const startBtn = document.getElementById('simpleAutoresearchStartBtn');
  const stopBtn = document.getElementById('simpleAutoresearchStopBtn');

  if (badge) {
    badge.textContent = data.state === 'running' ? 'Running' : data.state === 'error' ? 'Attention' : data.state === 'completed' ? 'Ready' : 'Idle';
    badge.className = 'ar-simple-badge' +
      (data.state === 'running' ? ' is-running' : data.state === 'error' ? ' is-error' : data.state === 'completed' ? ' is-ready' : '');
  }
  if (goal) goal.textContent = data.goal || 'Testing small matchup-strategy tweaks against the current baseline.';
  if (cadence) cadence.textContent = formatIntervalLabel(data.interval_seconds || 300);
  if (headline) headline.textContent = data.headline || 'Edge tuner is idle.';
  if (objective) objective.textContent = 'Objective: ' + (data.objective || 'weighted_roi_pct');
  if (lastRun) {
    if (data.cycle_in_progress && data.last_run_started_at) {
      lastRun.textContent = 'Current batch started: ' + formatTime(data.last_run_started_at);
    } else {
      lastRun.textContent =
        'Last completed: ' + (data.last_run_finished_at ? formatTime(data.last_run_finished_at) : 'Never');
    }
  }
  if (error) {
    error.textContent = data.error ? 'Error: ' + data.error : 'No errors.';
  }
  if (startBtn) startBtn.disabled = !!data.is_running;
  if (stopBtn) stopBtn.disabled = !data.is_running;
  renderSimpleAutoresearchBest(data.best_improvement);
  renderSimpleAutoresearchRecent(data.recent_attempts || []);
}

function setSimpleAutoresearchResult(message, tone) {
  const resultEl = document.getElementById('simpleAutoresearchResult');
  if (!resultEl) return;
  resultEl.style.display = 'block';
  resultEl.textContent = message;
  resultEl.className = 'result status ' + (tone || 'info');
}

async function loadSimpleAutoresearchStatus() {
  try {
    const resp = await fetch('/api/simple/autoresearch/status');
    if (!resp.ok) throw new Error('Server error (' + resp.status + ')');
    const data = await resp.json();
    updateSimpleAutoresearchUi(data);
  } catch (err) {
    setSimpleAutoresearchResult('Could not load edge tuner status: ' + err.message, 'error');
  }
}

async function startSimpleAutoresearch() {
  const btn = document.getElementById('simpleAutoresearchStartBtn');
  if (!btn) return;
  btn.disabled = true;
  btn.classList.add('is-loading');
  setSimpleAutoresearchResult('Starting edge tuner…', 'loading');
  try {
    const resp = await fetch('/api/simple/autoresearch/start', { method: 'POST' });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || 'Request failed');
    updateSimpleAutoresearchUi(data);
    setSimpleAutoresearchResult('Edge tuner started. It will keep testing small changes in report-only mode.', 'success');
    await loadAutoresearchStatus();
    loadStatus();
  } catch (err) {
    setSimpleAutoresearchResult('Error: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.classList.remove('is-loading');
  }
}

async function stopSimpleAutoresearch() {
  const btn = document.getElementById('simpleAutoresearchStopBtn');
  if (!btn) return;
  btn.disabled = true;
  btn.classList.add('is-loading');
  setSimpleAutoresearchResult('Stopping edge tuner…', 'loading');
  try {
    const resp = await fetch('/api/simple/autoresearch/stop', { method: 'POST' });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || 'Request failed');
    updateSimpleAutoresearchUi(data);
    setSimpleAutoresearchResult('Edge tuner stopped.', 'success');
    await loadAutoresearchStatus();
    loadStatus();
  } catch (err) {
    setSimpleAutoresearchResult('Error: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.classList.remove('is-loading');
  }
}

async function runSimpleAutoresearchOnce() {
  const btn = document.getElementById('simpleAutoresearchRunOnceBtn');
  if (!btn) return;
  btn.disabled = true;
  btn.classList.add('is-loading');
  setSimpleAutoresearchResult('Running one safe edge-tuner batch…', 'loading');
  try {
    const resp = await fetch('/api/simple/autoresearch/run-once', { method: 'POST' });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || 'Request failed');
    updateSimpleAutoresearchUi({
      mode: data.mode,
      report_only: data.report_only,
      state: 'completed',
      is_running: false,
      objective: data.objective,
      goal: data.goal,
      headline: data.best_improvement
        ? 'One batch finished. A safe candidate was found for review.'
        : 'One batch finished. No safe candidate beat the current baseline.',
      interval_seconds: APP_STATE.simpleAutoresearch && APP_STATE.simpleAutoresearch.interval_seconds
        ? APP_STATE.simpleAutoresearch.interval_seconds
        : 300,
      best_improvement: data.best_improvement,
      recent_attempts: data.recent_attempts || [],
      last_run_finished_at: new Date().toISOString(),
      error: null,
    });
    const best = data.best_improvement;
    const message = best
      ? (
        best.guardrails_passed
          ? 'Run complete. Best safe trial #' + best.trial_number + ' posted ROI ' + Number(best.roi_pct || 0).toFixed(2) + '%.'
          : 'Run complete. Best trial #' + best.trial_number + ' did not clear guardrails.'
      )
      : 'Run complete. No safe candidate beat the baseline in this batch.';
    setSimpleAutoresearchResult(message, 'success');
    await loadAutoresearchStatus();
    loadStatus();
  } catch (err) {
    setSimpleAutoresearchResult('Error: ' + err.message, 'error');
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
    const scalarInp = document.getElementById('optunaScalarStudyNameInput');
    const scalarObj = document.getElementById('scalarObjectiveSelect');
    const nTrialsEl = document.getElementById('optunaNTrialsInput');
    const engineMode = engineModeEl ? engineModeEl.value : 'research_cycle';
    const studyName = studyInp && studyInp.value.trim() ? studyInp.value.trim() : undefined;
    const scalarStudyName = scalarInp && scalarInp.value.trim() ? scalarInp.value.trim() : undefined;
    const scalarObjective = scalarObj ? scalarObj.value : undefined;
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
        optuna_scalar_study_name: scalarStudyName,
        scalar_objective: scalarObjective,
        optuna_trials_per_cycle: ot,
      }),
    });
    if (!resp.ok) {
      const errData = await resp.json().catch(function () { return {}; });
      throw new Error(errData.error || 'Server error (' + resp.status + ')');
    }
    const data = await resp.json();
    const running = data && data.optimizer && data.optimizer.running;
    const startedOptuna = engineMode === 'optuna';
    const startedScalar = engineMode === 'optuna_scalar';
    resultEl.textContent = running
      ? (startedScalar
        ? 'Autoresearch engine started. Optuna scalar runs every 5 minutes (' + ot + ' trial(s) per cycle).'
        : startedOptuna
          ? 'Autoresearch engine started. Optuna MO runs every 5 minutes (' + ot + ' trial(s) per cycle).'
          : 'Autoresearch engine started. Running every 5 minutes with 5 candidates per cycle.')
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
    await loadAutoresearchSettings();
    await fetchOptunaStudyDashboard();
    updateSinceStartSection();
    setAutoresearchPollingInterval(running ? 5000 : 15000);
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
    APP_STATE.autoresearchSettings = data;
    const mode = (data.guardrail_mode || 'strict').toLowerCase();
    if (mode === 'strict' || mode === 'loose') {
      select.value = mode;
    }
    const engineSel = document.getElementById('engineModeSelect');
    if (engineSel && data.engine_mode) {
      const em = data.engine_mode;
      engineSel.value =
        em === 'optuna' ? 'optuna' : em === 'optuna_scalar' ? 'optuna_scalar' : 'research_cycle';
    }
    const llmCb = document.getElementById('useTheoryLlmCheckbox');
    if (llmCb) llmCb.checked = !!data.use_theory_engine_llm;
    const studyInp = document.getElementById('optunaStudyNameInput');
    if (studyInp && data.optuna_study_name) studyInp.value = data.optuna_study_name;
    const scalarInp = document.getElementById('optunaScalarStudyNameInput');
    if (scalarInp && data.optuna_scalar_study_name) scalarInp.value = data.optuna_scalar_study_name;
    const scalarObj = document.getElementById('scalarObjectiveSelect');
    if (scalarObj && data.scalar_objective) {
      scalarObj.value = data.scalar_objective === 'weighted_roi_pct' ? 'weighted_roi_pct' : 'blended_score';
    }
    const nTrials = document.getElementById('optunaNTrialsInput');
    if (nTrials && data.optuna_trials_per_cycle != null) {
      nTrials.value = String(Math.max(1, Math.min(50, parseInt(data.optuna_trials_per_cycle, 10) || 3)));
    }
  } catch (err) {
    APP_STATE.autoresearchSettings = null;
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
    .then(function () {
      return loadAutoresearchSettings();
    })
    .then(function () {
      return fetchOptunaStudyDashboard();
    })
    .then(function () {
      if (APP_STATE.recentCandidates && APP_STATE.recentCandidates.length) {
        updateStatsBar(APP_STATE.recentCandidates, APP_STATE.recentRuns || []);
      }
      updateSinceStartSection();
    })
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

function handleScalarStudyBlur() {
  const inp = document.getElementById('optunaScalarStudyNameInput');
  if (!inp || !inp.value.trim()) return;
  fetch('/api/autoresearch/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ optuna_scalar_study_name: inp.value.trim().slice(0, 120) }),
  }).catch(function () {});
}

function handleScalarObjectiveChange() {
  const sel = document.getElementById('scalarObjectiveSelect');
  if (!sel) return;
  fetch('/api/autoresearch/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scalar_objective: sel.value }),
  }).catch(function () {});
}

async function loadAutoresearchPareto() {
  const container = document.getElementById('optunaParetoContainer');
  const studyInput = document.getElementById('optunaStudyNameInput');
  const scalarInput = document.getElementById('optunaScalarStudyNameInput');
  if (!container) return;
  const em = getAutoresearchEngineMode();
  const studyKind = em === 'optuna_scalar' ? 'scalar' : 'mo';
  const name =
    studyKind === 'scalar'
      ? (scalarInput && scalarInput.value.trim() ? scalarInput.value.trim() : '')
      : (studyInput && studyInput.value.trim() ? studyInput.value.trim() : '');
  const q =
    '?study_kind=' +
    encodeURIComponent(studyKind) +
    (name ? '&study_name=' + encodeURIComponent(name) : '');
  try {
    const resp = await fetch('/api/autoresearch/study' + q);
    const data = await resp.json();
    if (!data.ok) throw new Error(data.error || 'Failed to load study');
    const summ = data.summary || {};
    if (studyKind === 'scalar') {
      const bt = summ.best_trial;
      const bv = summ.best_value;
      if (summ.n_trials == null || summ.n_trials === 0) {
        container.innerHTML =
          '<div class="status info">No scalar trials yet. Run trials below or CLI with <code>study_kind=scalar</code>.</div>';
        await fetchOptunaStudyDashboard();
        return;
      }
      const detail = bt
        ? '<table class="ar-pareto-table"><thead><tr><th>Trial</th><th>Objective</th><th>ROI</th><th>Promotable</th></tr></thead><tbody><tr><td>' +
          escapeHtml(String(bt.number)) +
          '</td><td>' +
          escapeHtml(String(bt.value != null ? Number(bt.value).toFixed(4) : '—')) +
          '</td><td>' +
          escapeHtml(String((bt.user_attrs && bt.user_attrs.weighted_roi_pct != null) ? Number(bt.user_attrs.weighted_roi_pct).toFixed(2) : '—')) +
          '</td><td>' +
          escapeHtml(
            bt.user_attrs && bt.user_attrs.feasible && bt.user_attrs.guardrail_passed ? 'yes' : 'no'
          ) +
          '</td></tr></tbody></table>'
        : '';
      container.innerHTML =
        '<div class="status info">Scalar study: best objective = ' +
        escapeHtml(bv != null ? String(Number(bv).toFixed(4)) : '—') +
        '</div>' +
        detail;
      await fetchOptunaStudyDashboard();
      if (APP_STATE.recentCandidates) {
        updateStatsBar(APP_STATE.recentCandidates, APP_STATE.recentRuns || []);
      }
      updateSinceStartSection();
      return;
    }
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
    await fetchOptunaStudyDashboard();
    if (APP_STATE.recentCandidates) {
      updateStatsBar(APP_STATE.recentCandidates, APP_STATE.recentRuns || []);
    }
    updateSinceStartSection();
  } catch (err) {
    container.innerHTML = '<div class="status error">' + escapeHtml(err.message) + '</div>';
  }
}

async function runOptunaTrialsFromDashboard() {
  const nEl = document.getElementById('optunaNTrialsInput');
  const container = document.getElementById('optunaParetoContainer');
  const studyInput = document.getElementById('optunaStudyNameInput');
  const scalarInput = document.getElementById('optunaScalarStudyNameInput');
  const scalarObj = document.getElementById('scalarObjectiveSelect');
  if (!container) return;
  const n = Math.max(1, Math.min(50, parseInt((nEl && nEl.value) || '5', 10)));
  const em = getAutoresearchEngineMode();
  const studyKind = em === 'optuna_scalar' ? 'scalar' : 'mo';
  const studyName =
    studyKind === 'scalar'
      ? (scalarInput && scalarInput.value.trim() ? scalarInput.value.trim() : '')
      : (studyInput && studyInput.value.trim() ? studyInput.value.trim() : '');
  const payload = {
    n_trials: n,
    years: [2024, 2025],
    study_kind: studyKind,
    study_name: studyName || undefined,
  };
  if (studyKind === 'scalar' && scalarObj) {
    payload.scalar_objective = scalarObj.value;
  }
  container.innerHTML =
    '<div class="status info">Running ' + n + ' trial(s) — walk-forward replay; may take several minutes.</div>';
  try {
    const resp = await fetch('/api/autoresearch/optuna/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || 'Request failed');
    await loadAutoresearchPareto();
    await fetchOptunaStudyDashboard();
    if (APP_STATE.recentCandidates) {
      updateStatsBar(APP_STATE.recentCandidates, APP_STATE.recentRuns || []);
    }
    updateSinceStartSection();
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
    if (!APP_STATE.autoresearchSettings) {
      await loadAutoresearchSettings();
    }
    await fetchOptunaStudyDashboard();
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
  const od = APP_STATE.optunaDashboard;
  const useOptuna = isOptunaEngineMode() && od != null;

  const bestRoiLabel = document.getElementById('statBestRoiLabel');
  const bestClvLabel = document.getElementById('statBestClvLabel');
  const propLabel = document.getElementById('statTotalProposalsLabel');
  const promoLabel = document.getElementById('statPromotableLabel');
  const sk = od && od.study_kind;
  if (bestRoiLabel) bestRoiLabel.textContent = useOptuna ? 'Best ROI (study max)' : 'Best ROI';
  if (bestClvLabel) bestClvLabel.textContent = useOptuna ? 'Best CLV (study max)' : 'Best CLV';
  if (propLabel) propLabel.textContent = useOptuna ? 'Trials' : 'Proposals';
  if (promoLabel) promoLabel.textContent = useOptuna ? (sk === 'scalar' ? 'Best OK' : 'Pareto OK') : 'Promotable';

  if (!candidates.length && !(runs || []).length && !useOptuna) {
    setVal('statBaselineRoi', '—'); setVal('statBestRoi', '—');
    setVal('statBaselineClv', '—'); setVal('statBestClv', '—');
    setVal('statTotalProposals', '—'); setVal('statPromotable', '0');
    updateSinceStartSection();
    return;
  }

  var bsm = _findBaseline(candidates, runs);

  if (useOptuna) {
    var baseRoi = bsm.weighted_roi_pct;
    var baseClv = bsm.weighted_clv_avg;
    var trialMaxRoi = od.trial_max_roi_pct;
    var trialMaxClv = od.trial_max_clv;
    var nTrials = od.n_complete_trials != null ? od.n_complete_trials : 0;
    var paretoOk = od.pareto_promotable_count != null ? od.pareto_promotable_count : 0;
    setVal('statBaselineRoi', baseRoi != null ? baseRoi.toFixed(2) + '%' : '—', baseRoi != null ? (baseRoi > 0 ? 'val-positive' : 'val-negative') : '');
    setVal(
      'statBestRoi',
      trialMaxRoi != null ? trialMaxRoi.toFixed(2) + '%' : '—',
      trialMaxRoi != null && baseRoi != null && trialMaxRoi > baseRoi ? 'val-positive' : ''
    );
    setVal('statBaselineClv', baseClv != null ? baseClv.toFixed(4) : '—');
    setVal(
      'statBestClv',
      trialMaxClv != null ? trialMaxClv.toFixed(4) : '—',
      trialMaxClv != null && baseClv != null && trialMaxClv > baseClv ? 'val-positive' : ''
    );
    setVal('statTotalProposals', String(nTrials));
    setVal('statPromotable', String(paretoOk), paretoOk > 0 ? 'val-positive' : '');
    var note = document.getElementById('promotionQueueNote');
    if (note) {
      note.textContent =
        paretoOk > 0
          ? (sk === 'scalar'
            ? paretoOk + ' best trial passes feasibility + guardrails'
            : paretoOk + ' on Pareto pass feasibility + guardrails')
          : '';
    }
    updateSinceStartSection();
    return;
  }

  var bestCandidate = candidates.length ? candidates[0] : null;
  var sm = bestCandidate ? (bestCandidate.summary_metrics || {}) : {};
  var baseRoiR = bsm.weighted_roi_pct;
  var bestRoiR = sm.weighted_roi_pct;
  setVal('statBaselineRoi', baseRoiR != null ? baseRoiR.toFixed(2) + '%' : '—', baseRoiR != null ? (baseRoiR > 0 ? 'val-positive' : 'val-negative') : '');
  setVal('statBestRoi', bestRoiR != null ? bestRoiR.toFixed(2) + '%' : '—', (bestRoiR != null && baseRoiR != null && bestRoiR > baseRoiR) ? 'val-positive' : '');
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
  var noteR = document.getElementById('promotionQueueNote');
  if (noteR) {
    noteR.textContent = promotable.length > 0
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
  const od = APP_STATE.optunaDashboard;
  const useOptuna = isOptunaEngineMode() && od != null;
  const bestRoi = useOptuna
    ? od.trial_max_roi_pct
    : (best && best.summary_metrics ? best.summary_metrics.weighted_roi_pct : null);
  const bestClv = useOptuna
    ? od.trial_max_clv
    : (best && best.summary_metrics ? best.summary_metrics.weighted_clv_avg : null);

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
    if (cmd === 'run-once') {
      openAutoresearchTab('simple');
      runSimpleAutoresearchOnce();
    }
    if (cmd === 'start-engine') {
      openAutoresearchTab('simple');
      startSimpleAutoresearch();
    }
    if (cmd === 'open-lab') {
      openAutoresearchTab('lab');
    }
    if (cmd === 'view-grading') {
      var gradingTab = document.getElementById('tab-btn-grading');
      if (gradingTab) gradingTab.click();
    }
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
  loadLiveRefreshStatus();
  loadLiveRefreshSnapshot();
  setLiveRefreshPollingInterval(15000);
  loadSimpleAutoresearchStatus();
  (async function initAutoresearchUi() {
    await loadAutoresearchStatus();
    await loadAutoresearchRuns();
    await loadBestCandidates();
  })();
  initMainTabs();
  initAutoresearchModeTabs();
  initCommandMenu();

  const runPredictionBtn = document.getElementById('runPredictionBtn');
  const simpleAutoresearchStartBtn = document.getElementById('simpleAutoresearchStartBtn');
  const simpleAutoresearchRunOnceBtn = document.getElementById('simpleAutoresearchRunOnceBtn');
  const simpleAutoresearchStopBtn = document.getElementById('simpleAutoresearchStopBtn');
  const runAutoresearchBtn = document.getElementById('runAutoresearchBtn');
  const startAutoresearchBtn = document.getElementById('startAutoresearchBtn');
  const stopAutoresearchBtn = document.getElementById('stopAutoresearchBtn');
  const resetAutoresearchBtn = document.getElementById('resetAutoresearchBtn');
  const downloadCardBtn = document.getElementById('downloadCardBtn');
  const gradeLastEventBtn = document.getElementById('gradeLastEventBtn');
  const startLiveRefreshBtn = document.getElementById('startLiveRefreshBtn');
  const stopLiveRefreshBtn = document.getElementById('stopLiveRefreshBtn');
  if (runPredictionBtn) runPredictionBtn.addEventListener('click', runPrediction);
  if (simpleAutoresearchStartBtn) simpleAutoresearchStartBtn.addEventListener('click', startSimpleAutoresearch);
  if (simpleAutoresearchRunOnceBtn) simpleAutoresearchRunOnceBtn.addEventListener('click', runSimpleAutoresearchOnce);
  if (simpleAutoresearchStopBtn) simpleAutoresearchStopBtn.addEventListener('click', stopSimpleAutoresearch);
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
  const optunaScalarStudyNameInput = document.getElementById('optunaScalarStudyNameInput');
  if (optunaScalarStudyNameInput) optunaScalarStudyNameInput.addEventListener('blur', handleScalarStudyBlur);
  const scalarObjectiveSelect = document.getElementById('scalarObjectiveSelect');
  if (scalarObjectiveSelect) scalarObjectiveSelect.addEventListener('change', handleScalarObjectiveChange);
  const loadParetoBtn = document.getElementById('loadParetoBtn');
  if (loadParetoBtn) loadParetoBtn.addEventListener('click', loadAutoresearchPareto);
  const runOptunaTrialsBtn = document.getElementById('runOptunaTrialsBtn');
  if (runOptunaTrialsBtn) runOptunaTrialsBtn.addEventListener('click', runOptunaTrialsFromDashboard);
  if (startLiveRefreshBtn) startLiveRefreshBtn.addEventListener('click', startLiveRefresh);
  if (stopLiveRefreshBtn) stopLiveRefreshBtn.addEventListener('click', stopLiveRefresh);
  document.addEventListener('visibilitychange', function () {
    loadLiveRefreshStatus();
  });
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
