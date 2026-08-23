"""Operator backend for the autoresearch view (PR9).

Everything the Autoresearch tab needs, in one place:
- Cycle status + next-cycle ETA (reads orchestrator heartbeat + timer cadence)
- Ledger browser (read-only slices of output/research/ledger.jsonl)
- Promotion-ready dossiers listing
- Promote-to-Lab: swaps the LAB track to a candidate config (auditable row +
  one-click rollback via existing parent_id chain). The DASHBOARD slot is NOT
  touched here — that stays behind /api/tracks/promote with typed confirmation.
- Algorithm eras: per-config_hash graded ROI/W-L measured from activation time,
  plus an all-time line.
- Effort dial read/write (light/standard/max).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src import db

logger = logging.getLogger("golf.autoresearch_operator")

ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "output" / "research" / "ledger.jsonl"
HEARTBEAT_PATH = ROOT / "data" / "autoresearch_heartbeat.json"

EFFORT_CHOICES = ("light", "standard", "max")
NIGHTLY_UTC_HOUR = 2  # golf-autoresearch.timer runs 02:30 UTC


# ---------------------------------------------------------------------------
# Cycle status
# ---------------------------------------------------------------------------


def get_cycle_status() -> dict[str, Any]:
    heartbeat = None
    if HEARTBEAT_PATH.exists():
        try:
            heartbeat = json.loads(HEARTBEAT_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            heartbeat = None

    now = datetime.now(timezone.utc)
    next_run = now.replace(hour=NIGHTLY_UTC_HOUR, minute=30, second=0, microsecond=0)
    if next_run <= now:
        # datetime lacks replace(day+1); use timestamp arithmetic.
        next_run = datetime.fromtimestamp(now.timestamp() + 86400, tz=timezone.utc).replace(
            hour=NIGHTLY_UTC_HOUR, minute=30, second=0, microsecond=0
        )
    hours_to_next = round((next_run - now).total_seconds() / 3600.0, 1)

    return {
        "heartbeat": heartbeat,
        "heartbeat_age_seconds": (
            int((now - _parse_ts(heartbeat.get("ts"))).total_seconds())
            if heartbeat and heartbeat.get("ts")
            else None
        ),
        "next_nightly_utc": next_run.isoformat(),
        "hours_until_next_cycle": hours_to_next,
        "effort": get_effort(),
    }


def _parse_ts(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return datetime.fromtimestamp(0, tz=timezone.utc)


# ---------------------------------------------------------------------------
# Ledger browser (read-only)
# ---------------------------------------------------------------------------


def browse_ledger(
    *,
    limit: int = 100,
    kinds: list[str] | None = None,
    decision: str | None = None,
) -> dict[str, Any]:
    if not LEDGER_PATH.exists():
        return {"rows": [], "total": 0}
    rows: list[dict[str, Any]] = []
    total = 0
    wanted = set(kinds or [])
    with LEDGER_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            total += 1
            if wanted and row.get("kind") not in wanted:
                continue
            if decision and row.get("decision") != decision:
                continue
            rows.append(row)
    rows.reverse()  # newest first
    return {"rows": rows[: max(1, min(limit, 500))], "total": total}


# ---------------------------------------------------------------------------
# Promotion-ready dossiers
# ---------------------------------------------------------------------------


def list_promotion_ready() -> list[dict[str, Any]]:
    dossiers = []
    base = ROOT / "output" / "research" / "promotion_ready"
    if base.exists():
        for path in sorted(base.glob("promotion_ready_*.json"), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["dossier_path"] = str(path)
                dossiers.append(payload)
            except (json.JSONDecodeError, OSError):
                continue
    return dossiers


# ---------------------------------------------------------------------------
# Promote to Lab (human click; auditable; rollback = parent restore)
# ---------------------------------------------------------------------------


def promote_candidate_to_lab(
    config_hash: str,
    *,
    reason: str,
    activated_by: str = "operator",
) -> dict[str, Any]:
    """
    Swap the LAB track to the staged candidate config.

    Records an auditable lab track_configs row whose parent_id points at the
    prior active lab row (rollback target). The dashboard slot is untouched.
    """
    dossier = _find_dossier(config_hash)
    if not dossier:
        return {"ok": False, "reason": f"No promotion-ready dossier for {config_hash}"}

    from backtester.strategy_config_artifact import build_strategy_from_artifact
    from backtester.track_registry_bridge import record_lab_promotion

    strategy = build_strategy_from_artifact(dossier["candidate_artifact"], __import__("backtester.strategy", fromlist=["StrategyConfig"]).StrategyConfig(name="lab_challenger"))
    result = record_lab_promotion(
        strategy=strategy,
        label=f"tier1-{config_hash}",
        reason=reason,
        activated_by=activated_by,
        evidence=dossier.get("evidence"),
    )
    return result


def _find_dossier(config_hash: str) -> dict[str, Any] | None:
    base = ROOT / "output" / "research" / "promotion_ready"
    path = base / f"promotion_ready_{config_hash}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    # Reconstruct the artifact from the stored changes vs current champion file
    overrides = payload.get("overrides") or {}
    artifact = {
        "schema_version": payload.get("schema_version", 2),
        "name": payload.get("name", "tier1_staged"),
        "overrides": overrides,
        "ranges": payload.get("ranges") or {},
        "segments": payload.get("segments") or {},
    }
    return {
        **payload,
        "candidate_artifact": artifact,
        "evidence": {
            "search_window": payload.get("search_window"),
            "confirmation_window": payload.get("confirmation_window"),
            "multiplicity_context": payload.get("multiplicity_context"),
        },
    }


def rollback_lab() -> dict[str, Any]:
    """Restore the previous lab config (one action)."""
    from backtester.track_registry_bridge import rollback_lab_track

    return rollback_lab_track()


# ---------------------------------------------------------------------------
# Algorithm eras (per-algo performance from activation moment)
# ---------------------------------------------------------------------------


def get_algorithm_eras(*, window_days: int | None = None) -> dict[str, Any]:
    """
    Per-algorithm graded matchup ROI/W-L measured strictly AFTER each lab-track
    config's activation timestamp, plus an all-time aggregate.
    """
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """
            SELECT id, track, model_variant, config_hash, label, status,
                   activated_at, activated_by, activation_reason
            FROM track_configs
            ORDER BY id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    eras: list[dict[str, Any]] = []
    all_time = {"picks": 0, "wins": 0, "staked": 0.0, "returned": 0.0}

    for row in rows:
        if row["track"] != "lab":
            continue
        started_at = row["activated_at"]
        metrics = _graded_metrics_since(conn, started_at, window_days=window_days)
        eras.append(
            {
                "track_config_id": row["id"],
                "config_hash": row["config_hash"],
                "label": row["label"],
                "model_variant": row["model_variant"],
                "status": row["status"],
                "activated_at": started_at,
                "activated_by": row["activated_by"],
                "activation_reason": row["activation_reason"],
                **metrics,
            }
        )

    conn2 = db.get_conn()
    try:
        all_time = _alltime_matchup_stats(conn2)
    finally:
        conn2.close()

    return {"eras": eras, "all_time": all_time}


def _graded_metrics_since(conn: sqlite3.Connection, since_ts: str | None, *, window_days: int | None = None) -> dict[str, Any]:
    params: list[Any] = []
    where = ["t.event_id IS NOT NULL"]
    if since_ts:
        where.append("p.created_at >= ?")
        params.append(_iso_to_sqlite(since_ts))
    if window_days:
        where.append("p.created_at >= datetime('now', ?)")
        params.append(f"-{int(window_days)} days")

    query = f"""
        SELECT po.hit, po.stake, po.profit
        FROM picks p
        JOIN pick_outcomes po ON po.pick_id = p.id
        JOIN tournaments t ON t.id = p.tournament_id
        WHERE p.bet_type LIKE '%match%' AND {' AND '.join(where)}
    """
    picks = wins = 0
    staked = returned = 0.0
    for hit, stake, profit in conn.execute(query, params):
        picks += 1
        staked += float(stake or 1.0)
        returned += float(stake or 1.0) + float(profit or 0.0)
        wins += 1 if hit == 1 else 0
    roi = ((returned - staked) / staked * 100.0) if staked else 0.0
    return {
        "picks": picks,
        "wins": wins,
        "win_rate_pct": round(wins / picks * 100.0, 2) if picks else None,
        "staked_units": round(staked, 2),
        "roi_pct": round(roi, 2),
    }


def _alltime_matchup_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT COUNT(*), SUM(CASE WHEN po.hit = 1 THEN 1 ELSE 0 END),
               SUM(COALESCE(po.stake, 1.0)), SUM(COALESCE(po.stake, 1.0) + COALESCE(po.profit, 0.0))
        FROM picks p
        JOIN pick_outcomes po ON po.pick_id = p.id
        WHERE p.bet_type LIKE '%match%'
        """
    ).fetchone()
    picks = int(row[0] or 0)
    wins = int(row[1] or 0)
    staked = float(row[2] or 0.0)
    returned = float(row[3] or 0.0)
    roi = ((returned - staked) / staked * 100.0) if staked else 0.0
    return {
        "picks": picks,
        "wins": wins,
        "win_rate_pct": round(wins / picks * 100.0, 2) if picks else None,
        "staked_units": round(staked, 2),
        "roi_pct": round(roi, 2),
    }


def _iso_to_sqlite(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(str(ts))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return "1970-01-01 00:00:00"


# ---------------------------------------------------------------------------
# Effort dial
# ---------------------------------------------------------------------------


def get_effort() -> str:
    try:
        from workers.autoresearch_orchestrator import get_effort_setting

        return get_effort_setting()
    except Exception:
        return "standard"


def set_effort(name: str) -> dict[str, Any]:
    from workers.autoresearch_orchestrator import set_effort_setting

    ok = set_effort_setting(name)
    if not ok:
        return {"ok": False, "error": f"effort must be one of {EFFORT_CHOICES}"}
    return {"ok": True, "effort": name.strip().lower()}
