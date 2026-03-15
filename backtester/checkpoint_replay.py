"""Checkpoint-based PIT replay helpers for pilot autoresearch mode."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from backtester.autoresearch_config import load_pilot_contract, resolve_checkpoint_dates
from backtester.strategy import SimulationResult, StrategyConfig, replay_event
from src import db

SIGNATURE_KEYWORDS = (
    "the players championship",
    "arnold palmer invitational",
    "memorial tournament",
    "genesis invitational",
    "travelers championship",
    "wells fargo championship",
    "truist championship",
)


@dataclass
class PilotEvent:
    event_id: str
    year: int
    event_name: str
    start_date: str


def resolve_recent_signature_event() -> PilotEvent:
    """Resolve the most recent signature event from stored historical events."""
    conn = db.get_conn()
    rows = conn.execute(
        """
        SELECT event_id, year, event_name, start_date
        FROM historical_event_info
        WHERE event_id IS NOT NULL AND start_date IS NOT NULL
        ORDER BY start_date DESC, year DESC
        """
    ).fetchall()
    conn.close()
    for row in rows:
        event_name = (row["event_name"] or "").strip().lower()
        if any(keyword in event_name for keyword in SIGNATURE_KEYWORDS):
            return PilotEvent(
                event_id=str(row["event_id"]),
                year=int(row["year"]),
                event_name=row["event_name"],
                start_date=row["start_date"],
            )
    raise ValueError("No signature event found in historical_event_info")


def get_pilot_checkpoints() -> dict[str, Any]:
    """Return resolved pilot event and checkpoint list from pilot contract."""
    contract = load_pilot_contract()
    pilot_event = resolve_recent_signature_event()
    checkpoints = resolve_checkpoint_dates(pilot_event.start_date, contract)
    return {
        "contract": contract,
        "pilot_event": asdict(pilot_event),
        "checkpoints": checkpoints,
    }


def replay_checkpoint(event_id: str, year: int, strategy: StrategyConfig, as_of_date: str, checkpoint_id: str) -> dict[str, Any]:
    """
    Run one checkpoint replay.

    Uses open-line odds only to avoid post-close leakage in checkpoint mode.
    """
    bets = replay_event(
        event_id=event_id,
        year=year,
        strategy=strategy,
        odds_source="open",
        as_of_date=as_of_date,
    )
    result = SimulationResult(strategy=strategy, events_simulated=1, bet_details=bets)
    result.compute_metrics()
    return {
        "checkpoint_id": checkpoint_id,
        "as_of_date": as_of_date,
        "metrics": {
            "roi_pct": result.roi_pct,
            "clv_avg": result.clv_avg,
            "calibration_error": result.calibration_error,
            "total_bets": result.total_bets,
            "max_drawdown_pct": max(0.0, -result.roi_pct),
        },
    }


def summarize_checkpoint_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "checkpoints_evaluated": 0,
            "weighted_roi_pct": 0.0,
            "weighted_clv_avg": 0.0,
            "weighted_calibration_error": 0.0,
            "total_bets": 0,
        }

    n = len(results)
    roi = sum(r["metrics"]["roi_pct"] for r in results) / n
    clv = sum(r["metrics"]["clv_avg"] for r in results) / n
    cal = sum(r["metrics"]["calibration_error"] for r in results) / n
    bets = sum(r["metrics"]["total_bets"] for r in results)
    return {
        "checkpoints_evaluated": n,
        "weighted_roi_pct": round(roi, 4),
        "weighted_clv_avg": round(clv, 4),
        "weighted_calibration_error": round(cal, 4),
        "total_bets": bets,
    }


def assert_checkpoint_temporal_integrity(event_id: str, year: int, as_of_date: str) -> None:
    """
    Assert that PIT source rounds for this event are strictly before checkpoint date.

    This guard verifies contract behavior for checkpoint mode.
    """
    conn = db.get_conn()
    row = conn.execute(
        """
        SELECT MAX(r.event_completed) AS max_source_date
        FROM pit_rolling_stats p
        JOIN rounds r ON r.player_key = p.player_key
        WHERE p.event_id = ? AND p.year = ?
        """,
        (str(event_id), int(year)),
    ).fetchone()
    conn.close()
    max_source = row["max_source_date"] if row else None
    if max_source and date.fromisoformat(max_source) > date.fromisoformat(as_of_date):
        raise ValueError(
            f"Temporal leakage detected for event {event_id}/{year}: source {max_source} > as_of {as_of_date}"
        )

