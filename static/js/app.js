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
    const resp = await fetch('/api/simple/upcoming-prediction', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tour: 'pga' }),
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
    resultEl.textContent = data.error
      ? 'Error: ' + data.error
      : 'Cycle complete. Proposals evaluated: ' + (data.proposals_evaluated ?? '—');
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
    const resp = await fetch('/api/autoresearch/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope: 'global', interval_seconds: 300, max_candidates: 5 }),
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

    setAutoresearchPollingInterval(running ? 5000 : 15000);
  } catch (err) {
    statusEl.style.display = 'block';
    statusEl.className = 'result status error';
    statusEl.textContent = 'Failed to load engine status: ' + err.message;
    setAutoresearchPollingInterval(15000);
  }
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
    renderPromotionQueue(runs);
    if (!runs.length) {
      runsEl.style.display = 'block';
      runsEl.className = 'result status info recent-runs-feed';
      runsEl.textContent = 'Recent runs: none yet.';
      return;
    }
    runsEl.style.display = 'block';
    runsEl.className = 'result run-feed recent-runs-feed';
    let html = '';
    for (const r of runs) {
      const when = formatTime(r.created_at);
      const name = escapeHtml(r.display_title || r.candidate_name || 'Unnamed');
      const whatTested = escapeHtml((r.what_tested || r.hypothesis || 'No test description.').slice(0, 220));
      const summary = escapeHtml((r.summary_reason || 'No summary available.').slice(0, 220));
      const nextHint = escapeHtml((r.next_attempt_hint || 'Continue from strongest factor.').slice(0, 160));
      const verdictClass = r.is_positive_test ? 'positive' : (r.decision === 'blocked_by_guardrails' ? 'blocked' : 'neutral');
      const roiDelta = formatPctDelta(computeRunRoiDelta(r));
      const confidence = computeCandidateConfidence(r);
      html +=
        '<article class="run-item">' +
        '<div class="run-item-head"><h4>' + name + '</h4>' +
        '<span class="run-verdict ' + verdictClass + '">' + escapeHtml(r.decision || 'unknown') + '</span></div>' +
        '<div class="run-item-meta">' + escapeHtml(when) + '</div>' +
        '<div class="run-metrics">' +
        '<span class="metric-pill">ROI delta: ' + escapeHtml(roiDelta) + '</span>' +
        '<span class="metric-pill">Confidence: ' + confidence + '%</span>' +
        '</div>' +
        '<div class="confidence-wrap"><div class="confidence-track"><div class="confidence-fill" style="width:' + confidence + '%"></div></div></div>' +
        '<div class="run-item-text"><strong>Tested:</strong> ' + whatTested + '</div>' +
        '<div class="run-item-text"><strong>Result:</strong> ' + summary + '</div>' +
        '<div class="run-item-text"><strong>Next:</strong> ' + nextHint + '</div>' +
        '</article>';
    }
    runsEl.innerHTML = html;
  } catch (err) {
    runsEl.style.display = 'block';
    runsEl.className = 'result status error recent-runs-feed';
    runsEl.textContent = 'Failed to load recent runs: ' + err.message;
  }
}

async function loadBestCandidates() {
  const container = document.getElementById('bestCandidates');
  if (!container) return;

  try {
    const resp = await fetch('/api/autoresearch/best-candidates?scope=global&limit=25');
    if (!resp.ok) {
      const errData = await resp.json().catch(function () { return {}; });
      throw new Error(errData.error || 'Server error (' + resp.status + ')');
    }
    const data = await resp.json();
    const candidates = data.candidates || [];
    if (!candidates.length) {
      container.innerHTML =
        '<div class="status info">No evaluated candidates yet. Run autoresearch first.</div>';
      return;
    }
    let html = '';
    for (const c of candidates) {
      const roi =
        c.summary_metrics && c.summary_metrics.weighted_roi_pct != null
          ? c.summary_metrics.weighted_roi_pct.toFixed(1) + '%'
          : '—';
      const baseRoi =
        c.baseline_summary_metrics && c.baseline_summary_metrics.weighted_roi_pct != null
          ? c.baseline_summary_metrics.weighted_roi_pct.toFixed(1) + '%'
          : '—';
      const clv =
        c.summary_metrics && c.summary_metrics.weighted_clv_avg != null
          ? c.summary_metrics.weighted_clv_avg.toFixed(3)
          : '—';
      const confidence = Math.max(10, Math.min(98, Math.round(50 + (toFiniteNumber(c.roi_delta) || 0) * 2)));
      const passed = c.guardrail_results && c.guardrail_results.passed ? 'Yes' : 'No';
      const tldr = escapeHtml((c.strategy_tldr || '').slice(0, 280));
      const whatTested = escapeHtml((c.what_tested || c.hypothesis || 'No test description.').slice(0, 220));
      const summaryReason = escapeHtml((c.summary_reason || 'No summary available.').slice(0, 200));
      const nextAttempt = escapeHtml((c.next_attempt_hint || 'Keep iterating around strongest improvements.').slice(0, 160));
      const reportPath = c.artifact_content_path || c.artifact_markdown_path;
      const reportLink = reportPath
        ? '<a href="#" class="report-link link-secondary" data-path="' +
          escapeHtml(reportPath) +
          '" data-action="report">View report</a>'
        : '';
      html +=
        '<article class="candidate-item" draggable="true" data-player="' + escapeHtml(c.name || c.candidate_name || 'candidate') + '" data-id="' +
        escapeHtml(String(c.id)) +
        '">' +
        '<h3 class="candidate-name">' +
        escapeHtml(c.name || 'Unnamed') +
        '</h3>' +
        '<div class="tldr">' +
        tldr +
        (tldr.length >= 280 ? '…' : '') +
        '</div>' +
        '<div class="run-item-text"><strong>Tested:</strong> ' + whatTested + '</div>' +
        '<div class="run-item-text"><strong>Result:</strong> ' + summaryReason + '</div>' +
        '<div class="run-item-text"><strong>Next:</strong> ' + nextAttempt + '</div>' +
        '<div class="metrics">ROI: ' +
        roi +
        ' (base ' + baseRoi + ')' +
        ' · CLV: ' +
        clv +
        ' · Guardrails: ' +
        passed +
        ' ' +
        reportLink +
        '</div>' +
        '<div class="confidence-wrap"><div class="confidence-track"><div class="confidence-fill" style="width:' + confidence + '%"></div></div></div>' +
        '<div class="candidate-actions">' +
        '<button type="button" class="btn btn-promote btn-sm" data-action="promote" data-id="' +
        escapeHtml(String(c.id)) +
        '">Promote to live</button>' +
        '<span id="promoteMsg' +
        escapeHtml(String(c.id)) +
        '" class="promote-msg"></span>' +
        '</div></article>';
    }
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
    if (cmd === 'run-once') runAutoresearch();
    if (cmd === 'start-engine') startAutoresearchEngine();
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
  if (runPredictionBtn) runPredictionBtn.addEventListener('click', runPrediction);
  if (runAutoresearchBtn) runAutoresearchBtn.addEventListener('click', runAutoresearch);
  if (startAutoresearchBtn) startAutoresearchBtn.addEventListener('click', startAutoresearchEngine);
  if (stopAutoresearchBtn) stopAutoresearchBtn.addEventListener('click', stopAutoresearchEngine);
  if (resetAutoresearchBtn) resetAutoresearchBtn.addEventListener('click', resetAutoresearchState);
  if (downloadCardBtn) downloadCardBtn.addEventListener('click', downloadCard);
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
