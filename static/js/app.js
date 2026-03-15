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

function formatTime(value) {
  if (!value) return 'Never';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
    timeZoneName: 'short',
  });
}

let autoresearchPollTimer = null;

function setAutoresearchPollingInterval(ms) {
  if (autoresearchPollTimer) {
    window.clearInterval(autoresearchPollTimer);
  }
  autoresearchPollTimer = window.setInterval(async function () {
    await loadAutoresearchStatus();
  }, ms);
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
      body: JSON.stringify({ scope: 'global', max_candidates: 2 }),
    });
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
      body: JSON.stringify({ scope: 'global', interval_seconds: 60, max_candidates: 3 }),
    });
    const data = await resp.json();
    const running = data && data.optimizer && data.optimizer.running;
    resultEl.textContent = running
      ? 'Autoresearch engine started. It will continue running every 60 seconds.'
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
    const data = await resp.json();
    const status = data.status || {};
    const running = !!status.running;
    const state = status.state || (running ? 'running' : 'idle');
    const runCount = status.run_count || 0;
    const intervalSeconds = status.interval_seconds || 0;
    const lastFinished = status.last_finished_at ? formatTime(status.last_finished_at) : 'Never';
    const lastError = status.last_error || '';

    statusEl.style.display = 'block';
    statusEl.className = 'result status ' + (running ? 'success' : (lastError ? 'error' : 'info'));
    statusEl.textContent =
      'Engine: ' + state +
      ' | Runs: ' + runCount +
      ' | Interval: ' + intervalSeconds + 's' +
      ' | Last finished: ' + lastFinished +
      (lastError ? ' | Last error: ' + lastError : '');

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
    const resp = await fetch('/api/autoresearch/runs?scope=global&limit=5');
    const data = await resp.json();
    const runs = data.runs || [];
    if (!runs.length) {
      runsEl.style.display = 'block';
      runsEl.className = 'result status info';
      runsEl.textContent = 'Recent runs: none yet.';
      return;
    }
    runsEl.style.display = 'block';
    runsEl.className = 'result run-feed';
    let html = '<div class="run-feed-title">Recent runs</div>';
    for (const r of runs) {
      const when = formatTime(r.created_at);
      const name = escapeHtml(r.display_title || r.candidate_name || 'Unnamed');
      const whatTested = escapeHtml((r.what_tested || r.hypothesis || 'No test description.').slice(0, 220));
      const summary = escapeHtml((r.summary_reason || 'No summary available.').slice(0, 220));
      const nextHint = escapeHtml((r.next_attempt_hint || 'Continue from strongest factor.').slice(0, 160));
      const verdictClass = r.is_positive_test ? 'positive' : (r.decision === 'blocked_by_guardrails' ? 'blocked' : 'neutral');
      const roiDeltaValue = Number(r.roi_delta);
      const roiDelta = Number.isFinite(roiDeltaValue)
        ? (roiDeltaValue >= 0 ? '+' : '') + roiDeltaValue.toFixed(2) + '%'
        : 'N/A';
      html +=
        '<article class="run-item">' +
        '<div class="run-item-head"><h4>' + name + '</h4>' +
        '<span class="run-verdict ' + verdictClass + '">' + escapeHtml(r.decision || 'unknown') + '</span></div>' +
        '<div class="run-item-meta">' + escapeHtml(when) + ' · ROI delta: ' + escapeHtml(roiDelta) + '</div>' +
        '<div class="run-item-text"><strong>Tested:</strong> ' + whatTested + '</div>' +
        '<div class="run-item-text"><strong>Result:</strong> ' + summary + '</div>' +
        '<div class="run-item-text"><strong>Next:</strong> ' + nextHint + '</div>' +
        '</article>';
    }
    runsEl.innerHTML = html;
  } catch (err) {
    runsEl.style.display = 'block';
    runsEl.className = 'result status error';
    runsEl.textContent = 'Failed to load recent runs: ' + err.message;
  }
}

async function loadBestCandidates() {
  const container = document.getElementById('bestCandidates');
  if (!container) return;

  try {
    const resp = await fetch('/api/autoresearch/best-candidates?scope=global&limit=10');
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
        '<article class="candidate-item" data-id="' +
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
    promoteToLive(parseInt(promoteBtn.dataset.id, 10));
  }
});

document.addEventListener('DOMContentLoaded', function () {
  loadStatus();
  loadBestCandidates();
  loadAutoresearchStatus();
  loadAutoresearchRuns();
  initTools();
  const runPredictionBtn = document.getElementById('runPredictionBtn');
  const runAutoresearchBtn = document.getElementById('runAutoresearchBtn');
  const startAutoresearchBtn = document.getElementById('startAutoresearchBtn');
  const stopAutoresearchBtn = document.getElementById('stopAutoresearchBtn');
  const downloadCardBtn = document.getElementById('downloadCardBtn');
  if (runPredictionBtn) runPredictionBtn.addEventListener('click', runPrediction);
  if (runAutoresearchBtn) runAutoresearchBtn.addEventListener('click', runAutoresearch);
  if (startAutoresearchBtn) startAutoresearchBtn.addEventListener('click', startAutoresearchEngine);
  if (stopAutoresearchBtn) stopAutoresearchBtn.addEventListener('click', stopAutoresearchEngine);
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
