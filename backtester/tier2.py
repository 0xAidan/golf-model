"""Tier 2: structural hypothesis detection and operator-gated draft PRs.

Tier 1 can only turn existing knobs. Tier 2 detects signals that require NEW
code/segments (e.g., a golfer-type segment where model residuals cluster),
writes a human-readable hypothesis dossier, and alerts the operator. Creating
the actual draft PR is ALWAYS an explicit operator action (dashboard button ->
POST /api/autoresearch/tier2/create-pr) — the loop never writes to GitHub
unattended.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backtester.research_lab.fingerprint import evaluator_identity

logger = logging.getLogger("backtester.tier2")

DOSSIER_DIR = Path("output") / "research" / "tier2"

# Signal thresholds (deliberately conservative; PROGRAM.md forbids tiny-n claims).
MIN_SEGMENT_N = 30
MIN_ABS_RESIDUAL_PCT = 5.0  # mean absolute ROI deviation from 0 in a segment
MAX_SIGNALS_PER_CYCLE = 5

SEGMENT_KEYS = ("market_type", "book", "momentum_regime", "course_type", "odds_band")


def detect_segment_signals(
    lines: list[dict[str, Any]],
    *,
    min_n: int = MIN_SEGMENT_N,
    min_abs_roi_pct: float = MIN_ABS_RESIDUAL_PCT,
    top_k: int = MAX_SIGNALS_PER_CYCLE,
) -> list[dict[str, Any]]:
    """
    Scan graded backtest lines grouped by segment values; flag segments whose
    flat-unit ROI deviates from zero beyond threshold with sufficient n.

    `lines` rows come from research_backtest_lines + outcome joins:
        {segment_key fields..., odds_american, implied_prob, outcome}
    """
    buckets: dict[str, dict[str, Any]] = {}
    for line in lines:
        outcome = line.get("outcome")
        if outcome not in ("win", "loss"):
            continue
        implied = line.get("implied_prob") or 0.0
        if not implied or implied <= 0:
            continue
        decimal = 1.0 / float(implied)
        stake = 1.0
        profit = stake * (decimal - 1.0) if outcome == "win" else -stake
        for key in SEGMENT_KEYS:
            value = line.get(key)
            if not value:
                continue
            seg_key = f"{key}={value}"
            bucket = buckets.setdefault(
                seg_key, {"n": 0, "staked": 0.0, "returned": 0.0}
            )
            bucket["n"] += 1
            bucket["staked"] += stake
            bucket["returned"] += stake + profit if outcome == "win" else stake * 0 + (stake + profit)

    signals: list[dict[str, Any]] = []
    for seg_key, agg in buckets.items():
        n = agg["n"]
        if n < min_n or agg["staked"] <= 0:
            continue
        roi_pct = (agg["returned"] - agg["staked"]) / agg["staked"] * 100.0
        if abs(roi_pct) < min_abs_roi_pct:
            continue
        signals.append(
            {
                "segment": seg_key,
                "n": n,
                "roi_pct": round(roi_pct, 2),
                "direction": "model_edge" if roi_pct > 0 else "model_leak",
                "hypothesis": (
                    f"Bets in segment '{seg_key}' show {roi_pct:+.1f}% flat ROI over {n} graded picks."
                    if roi_pct > 0
                    else f"Bets in segment '{seg_key}' show {roi_pct:.1f}% flat ROI over {n} graded picks — "
                    "the model may be systematically miscalibrated here."
                ),
                "proposed_tier2_action": _propose_action(seg_key, roi_pct),
            }
        )
    signals.sort(key=lambda s: abs(s["roi_pct"]), reverse=True)
    return signals[:top_k]


def _propose_action(seg_key: str, roi_pct: float) -> str:
    axis = seg_key.split("=", 1)[0]
    if roi_pct < 0 and axis in ("book",):
        return "Consider excluding/downweighting this book's lines pending calibration review."
    if roi_pct > 0 and axis in ("course_type", "golfer_type", "momentum_regime"):
        return (
            "Candidate SEGMENT OVERRIDE for strategy_config.json segments block "
            f"(axis '{axis}') — needs new code to thread segment context into replay."
        )
    return "Requires structural investigation; propose a feature branch with tests."


def write_hypothesis_dossier(signal: dict[str, Any]) -> Path:
    """Write one Tier 2 hypothesis dossier; returns its path."""
    DOSSIER_DIR.mkdir(parents=True, exist_ok=True)
    slug = signal["segment"].replace("=", "_").replace("/", "-")
    payload = {
        "status": "HYPOTHESIS — needs code change (Tier 2)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **signal,
        "how_to_act": (
            "Review this dossier. If it looks real, click 'Create draft PR' in the "
            "Autoresearch tab; that opens an operator-initiated PR with an "
            "implementation sketch + tests. The loop never creates PRs by itself."
        ),
        **evaluator_identity(),
    }
    path = DOSSIER_DIR / f"hypothesis_{slug}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return path


def run_detection(*, alert_fn=None) -> list[dict[str, Any]]:
    """Full detection pass over the derived backtest ledger; dossiers + optional alert."""
    from backtester.backtest_ledger import coverage_summary
    from src.db import ensure_initialized

    ensure_initialized()
    from src import db

    conn = db.get_conn()
    try:
        rows = conn.execute(
            """
            SELECT market_type, book, implied_prob, outcome
            FROM research_backtest_lines
            """
        ).fetchall()
    finally:
        conn.close()

    lines = [
        {
            "market_type": r["market_type"],
            "book": r["book"],
            # Segment axes beyond book/market_type need enrichment later;
            # momentum_regime/course_type/golfer_type arrive with future features.
            "implied_prob": r["implied_prob"],
            "outcome": r["outcome"],
        }
        for r in rows
    ]
    signals = detect_segment_signals(lines)

    paths = [str(write_hypothesis_dossier(s)) for s in signals]
    if signals and alert_fn:
        alert_fn(
            "Autoresearch Tier 2: %d structural signal(s) detected.\n%s\n"
            "Dossiers under output/research/tier2/. Review before creating PRs."
            % (len(signals), "\n".join(f"- {s['segment']}: {s['roi_pct']:+.1f}% (n={s['n']})" for s in signals))
        )

    summary = {
        "signals_found": len(signals),
        "dossiers": paths,
        "ledger_events_total": coverage_summary().get("total_lines"),
    }

    from backtester.research_lab.ledger import append_ledger_row

    append_ledger_row({"source": "agent", "kind": "tier2_scan", "signals": len(signals)})
    return summary


# ---------------------------------------------------------------------------
# Operator-initiated PR creation (explicit action; never called by the loop)
# ---------------------------------------------------------------------------


def create_hypothesis_draft_pr(signal_segment: str, *, repo_dir: Path | None = None) -> dict[str, Any]:
    """
    Create a DRAFT PR for a stored hypothesis via gh CLI.

    Called ONLY from the authenticated operator endpoint. Returns
    {created: bool, pr_url?, error?}. Draft PRs are inert until merged and
    never touch production behavior on their own.
    """
    import subprocess

    dossier_path = DOSSIER_DIR / f"hypothesis_{signal_segment.replace('=', '_').replace('/', '-')}.json"
    if not dossier_path.exists():
        return {"created": False, "error": f"No dossier found for segment {signal_segment}"}
    payload = json.loads(dossier_path.read_text())

    branch = f"autoresearch/tier2-{slugify(signal_segment)}"
    title = f"[autoresearch] Tier 2 hypothesis: {signal_segment}"
    body = (
        "## Tier 2 structural hypothesis (operator-initiated draft PR)\n\n"
        f"**Segment:** `{payload.get('segment')}`\n"
        f"**n:** {payload.get('n')} graded picks\n"
        f"**Flat ROI:** {payload.get('roi_pct'):+.1f}%\n\n"
        f"**Hypothesis:** {payload.get('hypothesis')}\n\n"
        f"**Proposed action:** {payload.get('proposed_tier2_action')}\n\n"
        "---\n"
        "Implementation sketch: add the segment override plumbing described above,\n"
        "with characterization-safe tests mirroring tests/test_autoresearch_* style.\n"
        "This draft was created at operator request from the autoresearch dossier;\n"
        "the autonomous loop itself never opens PRs.\n"
    )

    commands_run: list[list[str]] = []
    try:
        def _run(cmd: list[str]) -> subprocess.CompletedProcess:
            commands_run.append(cmd)
            return subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                                  cwd=str(repo_dir) if repo_dir else None)

        checkout = _run(["git", "checkout", "-b", branch])
        if checkout.returncode != 0 and "already exists" not in checkout.stderr:
            return {"created": False, "error": checkout.stderr.strip()[:500]}

        sketch_path = Path("docs/research/tier2_sketches") / f"{slugify(signal_segment)}.md"
        sketch_path.parent.mkdir(parents=True, exist_ok=True)
        sketch_path.write_text(
            f"# Tier 2 implementation sketch — {signal_segment}\n\n{body}\n",
            encoding="utf-8",
        )
        _run(["git", "add", str(sketch_path)])
        commit = _run(["git", "commit", "-m", f"docs(autoresearch): tier2 hypothesis {signal_segment}"])
        if commit.returncode != 0:
            return {"created": False, "error": commit.stderr.strip()[:500]}
        push = _run(["git", "push", "-u", "origin", branch])
        if push.returncode != 0:
            return {"created": False, "error": push.stderr.strip()[:500]}
        pr = _run([
            "gh", "pr", "create", "--draft",
            "--title", title, "--body", body, "--head", branch,
        ])
        if pr.returncode != 0:
            return {"created": False, "error": pr.stderr.strip()[:500]}
        pr_url = pr.stdout.strip().splitlines()[-1]
        _run(["git", "checkout", "main"])  # restore operator's branch
        return {"created": True, "pr_url": pr_url, "branch": branch}
    except Exception as exc:
        return {"created": False, "error": str(exc)[:500], "commands": len(commands_run)}


def slugify(text: str) -> str:
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in "=/ -":
            out.append("-")
    return "".join(out).strip("-")[:60]
