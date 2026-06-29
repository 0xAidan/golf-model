"""Tests for ensure_event_grading_readiness backfill."""

from __future__ import annotations

from src import db
from src.event_pick_freeze import ensure_event_grading_readiness


def test_ensure_event_grading_readiness_backfills_ledger_from_picks(tmp_db):
    event_id = "26"
    year = 2026
    tid = db.get_or_create_tournament("U.S. Open", year=year, event_id=event_id)
    db.store_picks([
        {
            "tournament_id": tid,
            "model_variant": "v5",
            "source": "cockpit",
            "bet_type": "outright",
            "player_key": "scottie_scheffler",
            "player_display": "Scottie Scheffler",
            "opponent_key": "",
            "opponent_display": "",
            "model_prob": 0.12,
            "market_odds": "+800",
            "market_book": "draftkings",
            "market_implied_prob": 0.11,
            "ev": 0.05,
        },
    ])

    report = ensure_event_grading_readiness(
        event_id,
        year=year,
        event_name="U.S. Open",
    )

    assert report["status"] == "ready"
    assert report["positive_ev_picks"] >= 1
    assert report["ledger_rows"] >= 1
    assert report["grading_ready"] is True

    conn = db.get_conn()
    try:
        ledger = conn.execute(
            "SELECT COUNT(*) AS c FROM pick_ledger WHERE event_id = ?",
            (event_id,),
        ).fetchone()["c"]
    finally:
        conn.close()
    assert int(ledger) >= 1


def test_ensure_all_completed_pga_events_graded_accepts_complete_status(monkeypatch, tmp_db):
    from src.event_pick_freeze import ensure_all_completed_pga_events_graded

    monkeypatch.setattr("src.event_pick_freeze.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(
        "src.event_pick_freeze.freeze_completed_event_picks",
        lambda event_id, *, year, event_name=None: {
            "status": "complete",
            "event_id": event_id,
            "year": year,
        },
    )
    monkeypatch.setattr("src.event_pick_freeze.db.get_conn", lambda: _FakeConn())

    report = ensure_all_completed_pga_events_graded(year=2026)
    assert report["ok"] is True


class _FakeConn:
    def execute(self, *args, **kwargs):
        return self

    def fetchall(self):
        return [{"event_id": "34", "event_name": "Travelers Championship", "year": 2026}]

    def close(self):
        return None
