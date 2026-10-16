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
        {"event_id": "1", "year": today.year, "status": "upcoming"},
        {"event_id": "2", "year": today.year, "end_date": today.isoformat()},
        {"event_id": "3", "year": today.year, "status": "completed"},
        {"event_id": "4", "year": today.year, "end_date": (today - timedelta(days=1)).isoformat()},
    ]
    monkeypatch.setattr("src.datagolf._call_api", lambda *_args, **_kwargs: {"schedule": schedule})
    conn = db.get_conn()
    try:
        assert {row["event_id"] for row in _completed_events_for_sweep(conn, year=today.year)} == {"3", "4"}
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


def test_prior_season_bermuda_sources_do_not_complete_current_season_picks(tmp_db, monkeypatch):
    today = datetime.now(timezone.utc).date()
    monkeypatch.setattr("src.datagolf._call_api", lambda *_args, **_kwargs: [])
    conn = db.get_conn()
    try:
        _pick(conn, "528", year=today.year, name="Butterfield Bermuda Championship")
        conn.execute(
            "INSERT INTO rounds (dg_id,event_id,event_name,year,tour,round_num,event_completed) "
            "VALUES (1,'528','Butterfield Bermuda Championship',?,'pga',4,?)",
            (today.year - 1, f"{today.year - 1}-11-16"),
        )
        conn.execute(
            "INSERT INTO historical_event_info(event_id,year,tour,end_date) VALUES ('528',?,'pga',?)",
            (today.year - 1, f"{today.year - 1}-11-16"),
        )
        conn.commit()
        assert _completed_events_for_sweep(conn, year=today.year) == []
    finally:
        conn.close()


@pytest.mark.parametrize("source", ["rounds", "historical_event_info"])
def test_completion_date_must_belong_to_the_requested_season(tmp_db, monkeypatch, source):
    today = datetime.now(timezone.utc).date()
    monkeypatch.setattr("src.datagolf._call_api", lambda *_args, **_kwargs: [])
    conn = db.get_conn()
    try:
        _pick(conn, "528", year=today.year)
        if source == "rounds":
            conn.execute(
                "INSERT INTO rounds(dg_id,event_id,year,tour,round_num,event_completed) "
                "VALUES (1,'528',?,'pga',4,?)", (today.year, f"{today.year - 1}-11-16"),
            )
        else:
            conn.execute(
                "INSERT INTO historical_event_info(event_id,year,tour,end_date) VALUES ('528',?,'pga',?)",
                (today.year, f"{today.year - 1}-11-16"),
            )
        conn.commit()
        assert _completed_events_for_sweep(conn, year=today.year) == []
    finally:
        conn.close()


@pytest.mark.parametrize("source", ["rounds", "historical_event_info"])
def test_known_other_tour_results_are_not_pga_completion_evidence(tmp_db, monkeypatch, source):
    today = datetime.now(timezone.utc).date()
    monkeypatch.setattr("src.datagolf._call_api", lambda *_args, **_kwargs: [])
    conn = db.get_conn()
    try:
        tid = _pick(conn, "528", year=today.year)
        conn.execute(
            "INSERT INTO results(tournament_id,player_key,finish_position,finish_text) "
            "VALUES (?,'test_player',1,'1')", (tid,),
        )
        if source == "rounds":
            conn.execute(
                "INSERT INTO rounds(dg_id,event_id,year,tour,round_num,event_completed) "
                "VALUES (1,'528',?,'euro',4,?)", (today.year, today.isoformat()),
            )
        else:
            conn.execute(
                "INSERT INTO historical_event_info(event_id,year,tour,end_date) VALUES ('528',?,'euro',?)",
                (today.year, (today - timedelta(days=1)).isoformat()),
            )
        conn.commit()
        assert _completed_events_for_sweep(conn, year=today.year) == []
    finally:
        conn.close()


def test_schedule_rejects_unknown_or_contradictory_identity_without_hiding_valid_events(tmp_db, monkeypatch):
    today = datetime.now(timezone.utc).date()
    yesterday = (today - timedelta(days=1)).isoformat()
    schedule = [
        {"event_id": "1", "year": "invalid", "status": "completed"},
        {"event_id": "2", "status": "completed"},
        {"event_id": "3", "end_date": f"{today.year - 1}-11-16"},
        {"event_id": "4", "year": today.year, "tour": "euro", "status": "completed"},
        {"event_id": "5", "year": today.year, "end_date": f"{today.year - 1}-11-16"},
        {"event_id": "6", "year": today.year, "status": "completed", "end_date": (today + timedelta(days=1)).isoformat()},
        {"event_id": "fixture-event", "year": today.year, "status": "completed"},
        {"event_id": "30", "year": today.year, "status": "completed"},
        {"event_id": "31", "end_date": yesterday},
    ]
    monkeypatch.setattr("src.datagolf._call_api", lambda *_args, **_kwargs: {"schedule": schedule})
    conn = db.get_conn()
    try:
        assert {r["event_id"] for r in _completed_events_for_sweep(conn, year=today.year)} == {"30", "31"}
    finally:
        conn.close()


@pytest.mark.parametrize("provider_error", [False, True])
def test_missing_results_never_run_grading_or_learning_or_report_success(tmp_db, monkeypatch, caplog, provider_error):
    today = datetime.now(timezone.utc).date()
    monkeypatch.setattr("src.datagolf._call_api", lambda *_args, **_kwargs: [])
    conn = db.get_conn()
    tid = _pick(conn, "30", year=today.year, name="John Deere Classic")
    conn.execute(
        "INSERT INTO historical_event_info(event_id,year,tour,end_date) VALUES ('30',?,'pga',?)",
        (today.year, (today - timedelta(days=1)).isoformat()),
    )
    conn.commit()
    originals = [dict(r) for r in conn.execute("SELECT * FROM picks WHERE tournament_id=?", (tid,))]
    conn.close()

    def acquire(*_args, **_kwargs):
        if provider_error:
            raise RuntimeError("https://feeds.example/results?key=secret-token")
        return {"status": "no_data", "results_stored": 0}

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Missing results must not trigger scoring or learning")

    monkeypatch.setattr("src.event_results.acquire_event_results", acquire)
    monkeypatch.setattr("scripts.grade_tournament.grade_tournament", forbidden)
    monkeypatch.setattr("src.learning.post_tournament_learn", forbidden)
    report = ensure_all_completed_pga_events_graded(year=today.year)
    assert report["ok"] is False
    assert report["events_processed"] == 1
    assert report["results"][0]["status"] == ("error" if provider_error else "unavailable")
    assert "secret-token" not in json.dumps(report) + caplog.text
    conn = db.get_conn()
    try:
        assert [dict(r) for r in conn.execute("SELECT * FROM picks WHERE tournament_id=?", (tid,))] == originals
        assert conn.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM pick_outcomes").fetchone()[0] == 0
    finally:
        conn.close()
