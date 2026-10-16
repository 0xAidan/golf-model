"""Evidence reporting must never initialize, repair or mutate the source DB."""

import hashlib
import json
import sqlite3

import pytest

from src import market_evidence as evidence
from src.market_evidence import build_market_evidence, write_report


@pytest.fixture
def evidence_db(tmp_path):
    path = tmp_path / "evidence.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE tournaments (id INTEGER PRIMARY KEY, event_id TEXT, year INTEGER, name TEXT, date TEXT);
        CREATE TABLE picks (
            id INTEGER PRIMARY KEY, tournament_id INTEGER, source TEXT, model_variant TEXT,
            bet_type TEXT, market_type TEXT, player_key TEXT, opponent_key TEXT,
            market_book TEXT, market_odds TEXT, model_prob REAL, created_at TEXT,
            round_num INTEGER, group_id TEXT
        );
        CREATE TABLE pick_outcomes (
            id INTEGER PRIMARY KEY, pick_id INTEGER, hit INTEGER, profit REAL, stake REAL,
            actual_finish TEXT, grading_authority TEXT, outcome_locked INTEGER, entered_at TEXT
        );
        CREATE TABLE historical_matchup_odds (id INTEGER PRIMARY KEY);
        INSERT INTO tournaments VALUES (1, '100', 2026, 'First event', '2026-09-01');
        INSERT INTO tournaments VALUES (2, '101', 2026, 'Second event', '2026-09-08');
        INSERT INTO tournaments VALUES (3, '100', 2025, 'Prior season', '2025-09-01');
    """)
    conn.commit()
    conn.close()
    return path


def seed(path, pick_id, *, event=1, source="cockpit", market="tournament_matchups", bet_type="matchup",
         player="a", opponent="b", book="bet365", odds="+100", probability=.6,
         round_num=None, group_id=None, hit=1, profit=1, stake=1, result=None, authority="dg_official",
         graded=True):
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO picks VALUES (?, ?, ?, 'baseline', ?, ?, ?, ?, ?, ?, ?, '2026-08-31T12:00:00Z', ?, ?)",
        (pick_id, event, source, bet_type, market, player, opponent, book, odds, probability, round_num, group_id),
    )
    if graded:
        conn.execute(
            "INSERT INTO pick_outcomes VALUES (?, ?, ?, ?, ?, ?, ?, 1, '2026-09-10T12:00:00Z')",
            (pick_id, pick_id, hit, profit, stake, result, authority),
        )
    conn.commit()
    conn.close()


def test_read_is_byte_identical_without_schema_or_sidecar_changes(evidence_db):
    seed(evidence_db, 1)
    files_before = sorted(p.name for p in evidence_db.parent.iterdir())
    before = hashlib.sha256(evidence_db.read_bytes()).hexdigest()
    with sqlite3.connect(evidence_db) as conn:
        schema_before = list(conn.execute("SELECT * FROM sqlite_master ORDER BY name"))
    result = build_market_evidence(evidence_db)
    assert result["state"] == "available"
    assert hashlib.sha256(evidence_db.read_bytes()).hexdigest() == before
    assert sorted(p.name for p in evidence_db.parent.iterdir()) == files_before
    with sqlite3.connect(evidence_db) as conn:
        assert list(conn.execute("SELECT * FROM sqlite_master ORDER BY name")) == schema_before
    assert result["provenance"]["actual_wager_status"] == "unknown"
    assert result["provenance"]["full_season_verified"] is False


def test_event_season_round_and_lane_are_distinct(evidence_db):
    seed(evidence_db, 1)
    seed(evidence_db, 2, event=2)
    seed(evidence_db, 3, event=3)
    seed(evidence_db, 4, source="lab_sandbox")
    seed(evidence_db, 5, market="round_matchups", round_num=1)
    seed(evidence_db, 6, market="round_matchups", round_num=2)
    report = build_market_evidence(evidence_db, season=2026)
    assert report["coverage"]["record_count"] == 4
    assert report["coverage"]["event_count"] == 2
    assert report["coverage"]["duplicate_pick_records"] == 0
    markets = {m["key"]: m for m in report["markets"]}
    assert markets["72h"]["records"] == 2
    assert markets["18h"]["records"] == 2
    assert report["lanes"][1]["records"] == 0
    assert build_market_evidence(evidence_db, lane="lab")["summary"]["records"] == 1
    assert build_market_evidence(evidence_db, lane="all")["summary"]["records"] == 6


def test_void_push_unknown_and_missing_profit_are_never_losses(evidence_db):
    seed(evidence_db, 1, player="void", hit=0, profit=0, authority="void")
    seed(evidence_db, 2, player="push", hit=0, profit=0)
    seed(evidence_db, 3, player="unknown", hit=0, profit=None)
    seed(evidence_db, 4, player="loss", hit=0, profit=-1)
    seed(evidence_db, 5, player="win", hit=1, profit=None)
    seed(evidence_db, 6, player="pending", graded=False)
    summary = build_market_evidence(evidence_db)["summary"]
    assert (summary["wins"], summary["losses"], summary["pushes"], summary["voids"]) == (1, 1, 1, 1)
    assert summary["unknown"] == 1 and summary["ungraded"] == 1
    assert summary["net_units"] == -1
    assert summary["profit_covered_records"] == 3
    assert summary["profit_missing_records"] == 1
    assert summary["profit_coverage_complete"] is False
    assert summary["flat_unit_roi_pct"] is None
    assert summary["calibration"]["n"] == 2


def test_profit_is_preserved_and_flat_roi_requires_all_positive_stakes(evidence_db):
    seed(evidence_db, 1, player="a", profit=.4, stake=2, odds="+900")
    seed(evidence_db, 2, player="c", profit=-2, stake=2, hit=0)
    report = build_market_evidence(evidence_db)
    assert report["summary"]["net_units"] == -1.6  # Do not recalculate the +900 payout.
    assert report["summary"]["flat_unit_roi_pct"] == -40
    seed(evidence_db, 3, player="e", profit=1, stake=None)
    assert build_market_evidence(evidence_db)["summary"]["flat_unit_roi_pct"] is None


def test_calibration_bounds_and_binary_only(evidence_db):
    seed(evidence_db, 1, player="a", probability=1, profit=1)
    seed(evidence_db, 2, player="b", probability=0, hit=0, profit=-1)
    seed(evidence_db, 3, player="c", probability=1.2)
    seed(evidence_db, 4, player="d", probability=-.1)
    seed(evidence_db, 5, player="e", probability=.8, hit=0, profit=0)
    seed(evidence_db, 6, player="f", probability=.8, result="dead heat")
    seed(evidence_db, 7, player="g", probability=None)
    calibration = build_market_evidence(evidence_db)["summary"]["calibration"]
    assert calibration["n"] == 2
    assert calibration["brier"] == 0
    assert [b["lower"] for b in calibration["bins"]] == [0, .9]


def test_exact_repeats_count_once_but_conflicts_are_excluded(evidence_db):
    seed(evidence_db, 1)
    seed(evidence_db, 2)
    report = build_market_evidence(evidence_db)
    assert report["coverage"]["raw_pick_records"] == 2
    assert report["coverage"]["record_count"] == 1
    assert report["summary"]["net_units"] == 1
    seed(evidence_db, 3, odds="+150", profit=1.5)
    report = build_market_evidence(evidence_db)
    assert report["coverage"]["conflicting_identities"] == 1
    assert report["summary"]["net_units"] is None
    assert report["summary"]["calibration"]["n"] == 0
    assert report["summary"]["unknown"] == 1


def test_multiple_outcomes_for_one_pick_are_not_counted_twice(evidence_db):
    seed(evidence_db, 1)
    with sqlite3.connect(evidence_db) as conn:
        conn.execute("INSERT INTO pick_outcomes SELECT 2, pick_id, hit, profit, stake, actual_finish, grading_authority, outcome_locked, entered_at FROM pick_outcomes WHERE id=1")
    report = build_market_evidence(evidence_db)
    assert report["coverage"]["raw_pick_records"] == 1
    assert report["coverage"]["raw_outcome_records"] == 2
    assert report["summary"]["unknown"] == 1
    assert report["summary"]["net_units"] is None


def test_unknown_round_and_group_do_not_collapse_distinct_records(evidence_db):
    seed(evidence_db, 1, market="round_matchups")
    seed(evidence_db, 2, market="round_matchups")
    seed(evidence_db, 3, market="3ball", opponent="")
    seed(evidence_db, 4, market="3ball", opponent="")
    seed(evidence_db, 5, market="", player="unknown-duration")
    report = build_market_evidence(evidence_db)
    assert report["coverage"]["record_count"] == 5
    assert report["coverage"]["round_records_missing_round"] == 2
    assert report["coverage"]["group_records_missing_identity"] == 2
    markets = {m["key"]: m for m in report["markets"]}
    assert markets["group"]["records"] == 2
    assert markets["other"]["records"] == 1
    assert markets["72h"]["records"] == 0


def test_absent_schema_and_database_are_explicit_and_not_created(tmp_path):
    missing = tmp_path / "missing.db"
    assert build_market_evidence(missing)["state"] == "unavailable"
    assert not missing.exists()
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    before = empty.read_bytes()
    report = build_market_evidence(empty)
    assert report["state"] == "unavailable"
    assert "schema" in report["reason"]
    assert empty.read_bytes() == before


def test_empty_is_not_unavailable_and_gaps_are_explicit(evidence_db):
    report = build_market_evidence(evidence_db)
    assert report["state"] == "empty"
    assert report["summary"]["net_units"] is None
    assert report["summary"]["binary_hit_rate_pct"] is None
    gaps = {g["code"]: g for g in report["gaps"]}
    assert gaps["historical_matchup_odds"]["status"] == "empty"
    assert gaps["research_backtest_lines"]["status"] == "missing"


def test_committed_wal_is_read_without_immutable_mode(evidence_db):
    seed(evidence_db, 1)
    keeper = sqlite3.connect(evidence_db)
    keeper.execute("PRAGMA journal_mode=WAL")
    keeper.execute("PRAGMA wal_autocheckpoint=0")
    keeper.execute("UPDATE pick_outcomes SET profit = .5 WHERE id=1")
    keeper.commit()
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence_db.parent.iterdir() if not p.name.endswith("-shm")}
    try:
        assert build_market_evidence(evidence_db)["summary"]["net_units"] == .5
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence_db.parent.iterdir() if not p.name.endswith("-shm")}
        assert after == before
    finally:
        keeper.close()


def test_artifact_export_never_overwrites(evidence_db, tmp_path):
    report = build_market_evidence(evidence_db)
    target = tmp_path / "report-unique.json"
    write_report(report, target)
    original = target.read_text()
    assert json.loads(original)["state"] == "empty"
    with pytest.raises(FileExistsError):
        write_report({"changed": True}, target)
    assert target.read_text() == original


def test_endpoint_isolated_from_application_startup(evidence_db, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.routes.market_evidence import router

    seed(evidence_db, 1)
    monkeypatch.setenv("GOLF_DB_PATH", str(evidence_db))
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.get("/api/market-evidence?lane=dashboard&season=2026")
    assert response.status_code == 200
    assert response.json()["summary"]["wins"] == 1
    assert client.get("/api/market-evidence?lane=invalid").status_code == 422
    assert client.get("/api/market-evidence?season=1999").status_code == 422


def _source_hashes(path):
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in path.parent.iterdir() if p.is_file() and not p.name.endswith("-shm")
    }


def _assert_limit_report(report, kind):
    assert report["state"] == "unavailable"
    assert "No partial metrics" in report["reason"]
    assert report["coverage"]["record_count"] == 0
    assert report["coverage"]["raw_pick_records"] == 0
    assert report["summary"]["records"] == 0
    assert report["summary"]["net_units"] is None
    assert report["summary"]["flat_unit_roi_pct"] is None
    assert report["summary"]["calibration"]["n"] == 0
    assert report["markets"] == report["lanes"] == []
    assert report["gaps"][0]["code"] == "report_limit_exceeded"
    assert report["gaps"][0]["limit"] == kind


def test_row_cap_counts_joined_rows_before_deduplication_and_filtering(evidence_db, monkeypatch):
    monkeypatch.setattr(evidence, "MAX_REPORT_ROWS", 2)
    seed(evidence_db, 1)
    seed(evidence_db, 2)
    # Exactly at the cap preserves the existing exact-repeat behavior.
    report = build_market_evidence(evidence_db)
    assert report["coverage"]["raw_pick_records"] == 2
    assert report["summary"]["records"] == 1
    assert report["summary"]["net_units"] == 1
    with sqlite3.connect(evidence_db) as conn:
        conn.execute("INSERT INTO pick_outcomes SELECT 3, pick_id, hit, profit, stake, actual_finish, grading_authority, outcome_locked, entered_at FROM pick_outcomes WHERE id=1")
    before = _source_hashes(evidence_db)
    # Even a filter with no matching rows must not hide an incomplete source read.
    _assert_limit_report(build_market_evidence(evidence_db, lane="lab"), "rows")
    assert _source_hashes(evidence_db) == before


def test_aggregate_text_budget_counts_utf8_bytes_without_truncation(evidence_db, monkeypatch):
    monkeypatch.setattr(evidence, "MAX_REPORT_TEXT_BYTES", 8 * 1024)
    seed(evidence_db, 1, player="⛳" * 1500)
    assert build_market_evidence(evidence_db)["summary"]["net_units"] == 1
    seed(evidence_db, 2, player="⛳" * 1500 + "second")
    before = _source_hashes(evidence_db)
    _assert_limit_report(build_market_evidence(evidence_db), "text")
    assert _source_hashes(evidence_db) == before


@pytest.mark.parametrize("value", ["secret-source-text" * 5000, b"private-blob" * 7000])
def test_sqlite_value_limit_refuses_large_text_or_blob_before_python_materialization(evidence_db, value):
    seed(evidence_db, 1, player=value)
    before = _source_hashes(evidence_db)
    report = build_market_evidence(evidence_db)
    _assert_limit_report(report, "text")
    assert "secret-source-text" not in json.dumps(report)
    assert "private-blob" not in json.dumps(report)
    assert _source_hashes(evidence_db) == before


@pytest.mark.parametrize("phase", ["load", "grouping", "last_aggregate"])
def test_deadline_covers_loading_and_python_processing_without_partial_metrics(evidence_db, monkeypatch, phase):
    seed(evidence_db, 1, profit=.4, stake=2)
    seed(evidence_db, 2, player="c", hit=0, profit=-2, stake=2)
    now = [100.0]
    monkeypatch.setattr(evidence.time, "monotonic", lambda: now[0])

    if phase == "load":
        original = evidence._load_rows

        def load_then_expire(*args):
            rows = original(*args)
            now[0] += evidence.REPORT_TIMEOUT_SECONDS + 1
            return rows

        monkeypatch.setattr(evidence, "_load_rows", load_then_expire)
    elif phase == "grouping":
        original = evidence._identity

        def identity_then_expire(row):
            identity = original(row)
            now[0] += evidence.REPORT_TIMEOUT_SECONDS + 1
            return identity

        monkeypatch.setattr(evidence, "_identity", identity_then_expire)
    else:
        original = evidence._aggregate
        calls = [0]

        def aggregate_then_expire(rows, budget=None):
            result = original(rows, budget)
            if budget is not None:
                calls[0] += 1
                if calls[0] == 8:  # Summary, four markets, and three lanes.
                    now[0] += evidence.REPORT_TIMEOUT_SECONDS + 1
            return result

        monkeypatch.setattr(evidence, "_aggregate", aggregate_then_expire)

    before = _source_hashes(evidence_db)
    _assert_limit_report(build_market_evidence(evidence_db), "time")
    assert _source_hashes(evidence_db) == before


def test_historical_sized_report_fits_default_budget_with_original_metrics(evidence_db):
    seed(evidence_db, 1)
    with sqlite3.connect(evidence_db) as conn:
        conn.executemany(
            "INSERT INTO picks SELECT ?, tournament_id, source, model_variant, bet_type, market_type, ?, opponent_key, market_book, market_odds, model_prob, created_at, round_num, group_id FROM picks WHERE id=1",
            ((i, f"player-{i}") for i in range(2, 2501)),
        )
        conn.executemany(
            "INSERT INTO pick_outcomes SELECT ?, ?, hit, profit, stake, actual_finish, grading_authority, outcome_locked, entered_at FROM pick_outcomes WHERE id=1",
            ((i, i) for i in range(2, 2501)),
        )
    before = _source_hashes(evidence_db)
    report = build_market_evidence(evidence_db)
    assert report["state"] == "available"
    assert report["summary"]["records"] == report["summary"]["wins"] == 2500
    assert report["summary"]["net_units"] == 2500
    assert report["summary"]["flat_unit_roi_pct"] == 100
    assert report["summary"]["calibration"]["brier"] == .16
    assert _source_hashes(evidence_db) == before
