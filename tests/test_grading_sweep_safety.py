"""A sweep needs completed-event evidence and must survive one provider failure."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from src import db
from src.event_pick_freeze import _completed_events_for_sweep, ensure_all_completed_pga_events_graded


def _pick(conn, event_id, *, year, name="Test event"):
    tid = conn.execute(
        "INSERT INTO tournaments (event_id, year, name) VALUES (?, ?, ?)",
        (event_id, year, name),
    ).lastrowid
    conn.execute(
        "INSERT INTO picks (tournament_id, player_key, ev) VALUES (?, 'test_player', 0.1)",
        (tid,),
    )
    return tid


@pytest.mark.parametrize("end_offset", [None, 0, 7])
def test_upcoming_positive_ev_picks_do_not_enter_completed_sweep(tmp_db, monkeypatch, end_offset):
    today = datetime.now(timezone.utc).date()
    monkeypatch.setattr("src.datagolf._call_api", lambda *_args, **_kwargs: [])
    conn = db.get_conn()
    try:
        _pick(conn, "528", year=today.year, name="Butterfield Bermuda Championship")
        conn.execute(
            "INSERT INTO historical_event_info (event_id, year, tour, start_date, end_date) "
            "VALUES ('528', ?, 'pga', ?, ?)",
            (today.year, today.isoformat(),
             None if end_offset is None else (today + timedelta(days=end_offset)).isoformat()),
        )
        conn.commit()
        assert _completed_events_for_sweep(conn, year=today.year) == []
        # Eligibility discovery must leave existing inventory unchanged.
        assert conn.execute("SELECT COUNT(*) FROM picks").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM pick_outcomes").fetchone()[0] == 0
    finally:
        conn.close()


def test_past_end_date_allows_picks_when_results_and_rounds_are_missing(tmp_db, monkeypatch):
    today = datetime.now(timezone.utc).date()
    monkeypatch.setattr("src.datagolf._call_api", lambda *_args, **_kwargs: [])
    conn = db.get_conn()
    try:
        _pick(conn, "30", year=today.year)
        conn.execute(
            "INSERT INTO historical_event_info (event_id, year, tour, end_date) VALUES ('30', ?, 'pga', ?)",
            (today.year, (today - timedelta(days=2)).isoformat()),
        )
        conn.commit()
        assert [row["event_id"] for row in _completed_events_for_sweep(conn, year=today.year)] == ["30"]
    finally:
        conn.close()


def test_placeholder_results_do_not_imply_completion(tmp_db, monkeypatch):
    monkeypatch.setattr("src.datagolf._call_api", lambda *_args, **_kwargs: [])
    conn = db.get_conn()
    try:
        tid = _pick(conn, "528", year=2026)
        conn.execute("INSERT INTO results (tournament_id, player_key, finish_text) VALUES (?, 'test_player', '')", (tid,))
        conn.commit()
        assert _completed_events_for_sweep(conn, year=2026) == []
    finally:
        conn.close()


@pytest.mark.parametrize("completed", [None, "", " ", "unknown", "2999-01-01"])
def test_round_rows_without_past_completion_date_are_not_evidence(tmp_db, monkeypatch, completed):
    monkeypatch.setattr("src.datagolf._call_api", lambda *_args, **_kwargs: [])
    conn = db.get_conn()
    try:
        conn.execute(
            "INSERT INTO rounds (dg_id, event_id, event_name, year, tour, round_num, event_completed) "
            "VALUES (1, '528', 'Bermuda', 2026, 'pga', 1, ?)", (completed,),
        )
        conn.commit()
        assert _completed_events_for_sweep(conn, year=2026) == []
    finally:
        conn.close()


def test_completed_rounds_remain_eligible_without_picks(tmp_db, monkeypatch):
    monkeypatch.setattr("src.datagolf._call_api", lambda *_args, **_kwargs: [])
    conn = db.get_conn()
    try:
        conn.execute(
            "INSERT INTO rounds (dg_id, event_id, event_name, year, tour, round_num, event_completed) "
            "VALUES (1, '30', 'John Deere Classic', 2020, 'pga', 4, '2020-07-12')"
        )
        conn.commit()
        assert [row["event_id"] for row in _completed_events_for_sweep(conn, year=2020)] == ["30"]
    finally:
        conn.close()


def test_schedule_needs_finished_status_or_past_end_date(tmp_db, monkeypatch):
    today = datetime.now(timezone.utc).date()
    schedule = [
        {"event_id": "future", "year": today.year, "status": "upcoming"},
        {"event_id": "today", "year": today.year, "end_date": today.isoformat()},
        {"event_id": "finished", "year": today.year, "status": "completed"},
        {"event_id": "past", "year": today.year, "end_date": (today - timedelta(days=1)).isoformat()},
    ]
    monkeypatch.setattr("src.datagolf._call_api", lambda *_args, **_kwargs: {"schedule": schedule})
    conn = db.get_conn()
    try:
        assert {row["event_id"] for row in _completed_events_for_sweep(conn, year=today.year)} == {"finished", "past"}
    finally:
        conn.close()


def test_failed_event_is_reported_and_does_not_abort_later_events(tmp_db, monkeypatch, caplog):
    events = [
        {"event_id": "30", "event_name": "First event", "year": 2026},
        {"event_id": "34", "event_name": "Next event", "year": 2026},
    ]
    monkeypatch.setattr("src.event_pick_freeze._completed_events_for_sweep", lambda conn, *, year: events)
    seen = []

    def freeze(event_id, **kwargs):
        seen.append(event_id)
        if event_id == "30":
            raise RuntimeError("400 for https://feeds.example/results?key=secret-token API_KEY=other-secret")
        return {"status": "complete", "event_id": event_id, "year": kwargs["year"]}

    monkeypatch.setattr("src.event_pick_freeze.freeze_completed_event_picks", freeze)
    report = ensure_all_completed_pga_events_graded(year=2026)
    assert seen == ["30", "34"]
    assert report["events_processed"] == 2
    assert report["ok"] is False
    assert report["results"][0] == {
        "status": "error", "reason": "grading_failed", "event_id": "30", "year": 2026, "error": "RuntimeError",
    }
    assert report["results"][1]["status"] == "complete"
    output = json.dumps(report) + caplog.text
    assert "secret-token" not in output
    assert "other-secret" not in output
    assert "https://" not in output


def test_schedule_failure_logs_no_credentials_and_preserves_local_evidence(tmp_db, monkeypatch, caplog):
    def fail(*_args, **_kwargs):
        raise RuntimeError("https://feeds.example/get-schedule?key=secret-token")

    monkeypatch.setattr("src.datagolf._call_api", fail)
    conn = db.get_conn()
    try:
        tid = _pick(conn, "30", year=2026)
        conn.execute(
            "INSERT INTO results (tournament_id, player_key, finish_position, finish_text) VALUES (?, 'test_player', 1, '1')",
            (tid,),
        )
        conn.commit()
        assert [row["event_id"] for row in _completed_events_for_sweep(conn, year=2026)] == ["30"]
    finally:
        conn.close()
    assert "RuntimeError" in caplog.text
    assert "secret-token" not in caplog.text
    assert "https://" not in caplog.text
