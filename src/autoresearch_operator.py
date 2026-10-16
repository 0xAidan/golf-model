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
import math
import os
import sqlite3
from datetime import datetime, timedelta, timezone
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
    """Attribute graded matchups to disjoint lab activation/config intervals.

    Hashless history remains in the all-time record, never in an invented era.
    Bounds use pick creation time, not the time its outcome was graded.
    """
    as_of = datetime.now(timezone.utc)
    window_start = as_of - timedelta(days=window_days) if window_days and window_days > 0 else None
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
        graded = _graded_matchup_rows(conn)
    finally:
        conn.close()

    lab_rows = [dict(row) for row in rows if row["track"] == "lab"]
    lab_rows.sort(key=lambda row: (_era_timestamp(row["activated_at"]) or datetime.max.replace(tzinfo=timezone.utc), row["id"]))
    eras: list[dict[str, Any]] = []
    bounds: list[tuple[datetime | None, datetime]] = []
    for index, row in enumerate(lab_rows):
        start = _era_timestamp(row["activated_at"])
        next_start = next(
            (_era_timestamp(later["activated_at"]) for later in lab_rows[index + 1:] if _era_timestamp(later["activated_at"]) is not None),
            None,
        )
        end = min(next_start, as_of) if next_start is not None else as_of
        bounds.append((start, end))
        status = "attributable"
        if start is None:
            status = "missing_activation_time"
        elif not str(row["config_hash"] or "").strip():
            status = "missing_config_hash"
        elif start >= end:
            status = "empty_activation_interval"
        eras.append(
            {
                "track_config_id": row["id"],
                "config_hash": row["config_hash"],
                "label": row["label"],
                "model_variant": row["model_variant"],
                "status": row["status"],
                "activated_at": row["activated_at"],
                "ended_at": end.isoformat(),
                "interval_end_basis": "next_activation" if next_start is not None and next_start <= as_of else "report_as_of",
                "attribution_status": status,
                "activated_by": row["activated_by"],
                "activation_reason": row["activation_reason"],
            }
        )

    attributed: list[list[dict[str, Any]]] = [[] for _ in eras]
    excluded: dict[str, int] = {}
    for pick in graded:
        reason = None
        created_at = _era_timestamp(pick["created_at"])
        config_hash = str(pick["model_config_hash"] or "").strip()
        if pick["source"] not in {"lab_sandbox", "lab_sandbox_candidate"}:
            reason = "different_or_unknown_lane"
        elif not config_hash:
            reason = "missing_config_hash"
        elif not str(pick["event_id"] or "").strip():
            reason = "missing_event_identity"
        elif created_at is None:
            reason = "missing_or_invalid_pick_time"
        elif window_start is not None and created_at < window_start:
            reason = "outside_report_window"
        else:
            intervals = [
                i for i, (start, end) in enumerate(bounds)
                if start is not None and start <= created_at < end and eras[i]["attribution_status"] == "attributable"
            ]
            matching = [i for i in intervals if str(eras[i]["config_hash"]).strip() == config_hash]
            if not intervals:
                reason = "outside_activation_intervals"
            elif not matching:
                reason = "config_hash_mismatch"
            elif str(pick["model_variant"] or "").strip() != str(eras[matching[0]]["model_variant"] or "").strip():
                reason = "model_variant_mismatch"
            else:
                attributed[matching[0]].append(pick)
        if reason:
            excluded[reason] = excluded.get(reason, 0) + 1

    for era, picks in zip(eras, attributed):
        era.update(_matchup_metrics(picks))
    attributed_count = sum(len(picks) for picks in attributed)
    return {
        "eras": eras,
        "all_time": _matchup_metrics(graded),
        "attribution": {
            "version": "bounded_lab_config_v1",
            "as_of": as_of.isoformat(),
            "lane": "lab",
            "interval": "activation_inclusive_to_next_activation_exclusive",
            "window_days": window_days,
            "graded_matchup_rows": len(graded),
            "attributed_picks": attributed_count,
            "unattributed_picks": len(graded) - attributed_count,
            "excluded": excluded,
            "all_time_scope": "all_lanes_all_dates_including_unattributed",
            "limitation": "Creation-time attribution; edits and rollback reactivations without a new activation record cannot be reconstructed.",
        },
    }


def _era_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _graded_matchup_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    # One authoritative/latest outcome per pick; keep all original rows intact.
    return [dict(row) for row in conn.execute(
        """
        WITH ranked_outcomes AS (
            SELECT pick_id, hit, stake, profit,
                   ROW_NUMBER() OVER (
                       PARTITION BY pick_id ORDER BY COALESCE(outcome_locked, 0) DESC, id DESC
                   ) AS outcome_rank
            FROM pick_outcomes
        )
        SELECT p.id, p.source, p.model_variant, p.model_config_hash, p.created_at,
               t.event_id, po.hit, po.stake, po.profit
        FROM picks p
        JOIN ranked_outcomes po ON po.pick_id = p.id AND po.outcome_rank = 1
        LEFT JOIN tournaments t ON t.id = p.tournament_id
        WHERE LOWER(p.bet_type) LIKE '%match%' AND po.hit IN (0, 1)
        """
    ).fetchall()]


def _matchup_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    picks = len(rows)
    wins = sum(row["hit"] == 1 for row in rows)
    staked = profit = 0.0
    roi_picks = 0
    for row in rows:
        try:
            stake, pick_profit = float(row["stake"]), float(row["profit"])
        except (TypeError, ValueError, OverflowError):
            continue
        if not math.isfinite(stake) or not math.isfinite(pick_profit) or stake <= 0:
            continue
        staked += stake
        profit += pick_profit
        roi_picks += 1
    return {
        "picks": picks,
        "wins": wins,
        "win_rate_pct": round(wins / picks * 100.0, 2) if picks else None,
        "staked_units": round(staked, 2),
        "roi_pct": round(profit / staked * 100.0, 2) if staked else None,
        "roi_picks": roi_picks,
        "missing_financials": picks - roi_picks,
    }


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
