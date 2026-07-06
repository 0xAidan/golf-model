"""Regression tests for delayed completed-event grading retries."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from src import db, datagolf


def test_is_event_gradeable_accepts_past_end_date_with_results_evidence(tmp_db):
    tournament_id = db.get_or_create_tournament("John Deere Classic", year=2026, event_id="30")
    db.store_results(
        tournament_id,
        [
            {
                "player_key": "scottie_scheffler",
                "player_display": "Scottie Scheffler",
                "finish_position": 1,
                "finish_text": "1",
                "made_cut": 1,
            }
        ],
    )

    gradeable = datagolf.is_event_gradeable(
        {
            "event_id": "30",
            "event_name": "John Deere Classic",
            "year": 2026,
            "status": "in_progress",
            "end_date": "2026-07-06",
        },
        today=date(2026, 7, 7),
    )

    assert gradeable is True


def test_is_event_gradeable_accepts_remote_results_signal(monkeypatch):
    monkeypatch.setattr(
        datagolf,
        "_call_api",
        lambda endpoint, params=None, cache_ttl_seconds=300: {
            "results": [
                {
                    "player_name": "Scottie Scheffler",
                    "fin_text": "1",
                }
            ]
        },
    )

    gradeable = datagolf.is_event_gradeable(
        {
            "event_id": "30",
            "event_name": "John Deere Classic",
            "year": 2026,
            "status": "in_progress",
            "end_date": "2026-07-06",
        },
        today=date(2026, 7, 7),
    )

    assert gradeable is True


def test_maybe_auto_grade_completed_event_waits_for_retry_window(tmp_db, monkeypatch):
    from backtester import dashboard_runtime as runtime

    runtime._state = runtime._default_state()
    tournament_id = db.get_or_create_tournament("John Deere Classic", year=2026, event_id="30")
    db.store_picks(
        [
            {
                "tournament_id": tournament_id,
                "model_variant": "v5",
                "source": "cockpit",
                "bet_type": "top20",
                "player_key": "scottie_scheffler",
                "player_display": "Scottie Scheffler",
                "opponent_key": "",
                "opponent_display": "",
                "model_prob": 0.2,
                "market_odds": "+400",
                "market_book": "draftkings",
                "market_implied_prob": 0.15,
                "ev": 0.05,
            }
        ]
    )

    now = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
    clock = {"now": now}
    monkeypatch.setattr(runtime, "_utc_now", lambda: clock["now"])

    calls: list[datetime] = []

    def _freeze(_event_id, *, year, event_name=None):
        calls.append(clock["now"])
        if len(calls) == 1:
            return {"status": "captured", "reason": "awaiting_results"}
        return {"status": "complete", "reason": "graded"}

    monkeypatch.setattr("src.event_pick_freeze.freeze_completed_event_picks", _freeze)

    ingest_summary = {
        "latest_completed_event_id": "30",
        "latest_completed_event_year": 2026,
        "latest_completed_event_name": "John Deere Classic",
        "latest_completed_event_end_date": "2026-07-06",
    }

    first = runtime._maybe_auto_grade_completed_event(ingest_summary)
    assert first["reason"] == "awaiting_results"
    assert first["retry_after_seconds"] == 15 * 60
    assert len(calls) == 1

    second = runtime._maybe_auto_grade_completed_event(ingest_summary)
    assert second["status"] == "skipped"
    assert second["reason"] == "awaiting_retry_scheduled"
    assert len(calls) == 1

    clock["now"] = now + timedelta(minutes=16)
    third = runtime._maybe_auto_grade_completed_event(ingest_summary)
    assert third["status"] == "complete"
    assert len(calls) == 2


def test_maybe_auto_grade_completed_event_stops_after_24_hours(tmp_db, monkeypatch):
    from backtester import dashboard_runtime as runtime

    runtime._state = runtime._default_state()
    tournament_id = db.get_or_create_tournament("John Deere Classic", year=2026, event_id="30")
    db.store_picks(
        [
            {
                "tournament_id": tournament_id,
                "model_variant": "v5",
                "source": "cockpit",
                "bet_type": "top20",
                "player_key": "scottie_scheffler",
                "player_display": "Scottie Scheffler",
                "opponent_key": "",
                "opponent_display": "",
                "model_prob": 0.2,
                "market_odds": "+400",
                "market_book": "draftkings",
                "market_implied_prob": 0.15,
                "ev": 0.05,
            }
        ]
    )

    runtime._state.update(
        {
            "auto_grade_awaiting_event_id": "30",
            "auto_grade_awaiting_year": 2026,
            "auto_grade_awaiting_end_date": "2026-07-05",
            "auto_grade_awaiting_retry_after_at": "2026-07-06T00:15:00+00:00",
        }
    )

    monkeypatch.setattr(
        runtime,
        "_utc_now",
        lambda: datetime(2026, 7, 7, 1, 0, tzinfo=timezone.utc),
    )

    calls: list[str] = []
    monkeypatch.setattr(
        "src.event_pick_freeze.freeze_completed_event_picks",
        lambda *args, **kwargs: calls.append("called") or {"status": "complete"},
    )

    ingest_summary = {
        "latest_completed_event_id": "30",
        "latest_completed_event_year": 2026,
        "latest_completed_event_name": "John Deere Classic",
        "latest_completed_event_end_date": "2026-07-05",
    }

    result = runtime._maybe_auto_grade_completed_event(ingest_summary)

    assert result["status"] == "skipped"
    assert result["reason"] == "awaiting_retry_window_expired"
    assert calls == []
    assert runtime._state["auto_grade_awaiting_event_id"] is None
