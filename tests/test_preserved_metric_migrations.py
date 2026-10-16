"""Startup normalization and fresh metrics keep exact source observations."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest


def _versions(conn, source_table):
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='prediction_history_versions'"
    ).fetchone():
        return []
    return [json.loads(row[0]) for row in conn.execute(
        "SELECT payload_json FROM prediction_history_versions WHERE source_table=? ORDER BY id",
        (source_table,),
    )]


def _metric(tournament_id, **updates):
    return {
        "tournament_id": tournament_id,
        "csv_import_id": None,
        "player_key": "source_player",
        "player_display": "Source Player",
        "metric_category": "strokes_gained",
        "data_mode": "recent_form",
        "round_window": "50",
        "metric_name": "SG:TOT",
        "metric_value": 1.25,
        "metric_text": "original source text",
        **updates,
    }


def test_migration_retains_pick_and_outcome_source_values_and_times(tmp_db, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tournament = tmp_db.get_or_create_tournament("Source normalization", year=2026)
    conn = tmp_db.get_conn()
    pick = conn.execute("""INSERT INTO picks
        (tournament_id,player_key,bet_type,model_variant,source,market_book,
         opponent_key,opponent_display,market_type,ev,created_at)
        VALUES (?,'source_player','outright','  ',NULL,NULL,NULL,NULL,'outright',-0.2,
                '2026-03-04T08:09:10.123Z')""", (tournament,)).lastrowid
    conn.execute("""INSERT INTO pick_outcomes
        (pick_id,hit,model_hit,profit,stake,notes,entered_at)
        VALUES (?,1,NULL,5.5,1.25,'original booked outcome','2026-03-08T12:13:14.567Z')""", (pick,))
    conn.commit()
    original_pick = dict(conn.execute("SELECT * FROM picks WHERE id=?", (pick,)).fetchone())
    original_outcome = dict(conn.execute("SELECT * FROM pick_outcomes WHERE pick_id=?", (pick,)).fetchone())

    tmp_db._run_migrations(conn)

    assert _versions(conn, "picks") == [original_pick]
    assert _versions(conn, "pick_outcomes") == [original_outcome]
    current_pick = dict(conn.execute("SELECT * FROM picks WHERE id=?", (pick,)).fetchone())
    assert current_pick["model_variant"] == "baseline"
    assert current_pick["source"] == "ui_display"
    assert current_pick["market_book"] == current_pick["opponent_key"] == current_pick["opponent_display"] == ""
    assert current_pick["created_at"] == original_pick["created_at"]
    outcome = dict(conn.execute("SELECT * FROM pick_outcomes WHERE pick_id=?", (pick,)).fetchone())
    assert outcome == {**original_outcome, "model_hit": 0}
    tmp_db._run_migrations(conn)
    assert _versions(conn, "picks") == [original_pick]
    assert _versions(conn, "pick_outcomes") == [original_outcome]
    conn.close()


def test_legacy_matchup_market_type_backfill_retains_exact_old_row(tmp_db, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tournament = tmp_db.get_or_create_tournament("Legacy market identity", year=2026)
    conn = tmp_db.get_conn()
    conn.execute("DROP INDEX idx_picks_unique")
    conn.execute("ALTER TABLE picks DROP COLUMN market_type")
    pick = conn.execute("""INSERT INTO picks
        (tournament_id,player_key,bet_type,model_variant,source,market_book,opponent_key,opponent_display)
        VALUES (?,'source_player','matchup','baseline','ui_display','','opponent','Opponent')""", (tournament,)).lastrowid
    conn.commit()
    original = dict(conn.execute("SELECT * FROM picks WHERE id=?", (pick,)).fetchone())
    tmp_db._run_migrations(conn)
    assert _versions(conn, "picks") == [original]
    assert conn.execute("SELECT market_type FROM picks WHERE id=?", (pick,)).fetchone()[0] == "tournament_matchups"
    conn.close()


def test_metrics_migration_preserves_discarded_sources_and_max_id_reads(tmp_db, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tournament = tmp_db.get_or_create_tournament("Source metric versions", year=2026)
    conn = tmp_db.get_conn()
    conn.execute("DROP INDEX idx_metrics_unique")
    conn.execute("ALTER TABLE metrics ADD COLUMN source_captured_at TEXT")
    for version in (1, 2, 3):
        conn.execute("""INSERT INTO metrics
            (tournament_id,player_key,player_display,metric_category,data_mode,round_window,
             metric_name,metric_value,metric_text,source_captured_at)
            VALUES (?,'source_player','Source Player','strokes_gained',NULL,'50',
                    'SG:TOT',?,?,?)""", (tournament, version, f"source {version}", f"2026-03-0{version}T10:00:00Z"))
    conn.commit()
    originals = [dict(row) for row in conn.execute("SELECT * FROM metrics ORDER BY id")]

    tmp_db._run_migrations(conn)

    assert _versions(conn, "metrics") == originals[:-1]
    assert [dict(row) for row in conn.execute("SELECT * FROM metrics")] == originals[-1:]
    assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='idx_metrics_unique'").fetchone()
    assert tmp_db.get_player_metrics(tournament, "source_player") == originals[-1:]
    tmp_db._run_migrations(conn)
    assert _versions(conn, "metrics") == originals[:-1]
    conn.close()


def test_metric_writes_preserve_changed_source_and_leave_unchanged_ids(tmp_db, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tournament = tmp_db.get_or_create_tournament("Metric refresh", year=2026)
    original_import = tmp_db.log_csv_import(tournament, "original.csv", "sg", "recent_form", "50", 1)
    refreshed_import = tmp_db.log_csv_import(tournament, "refreshed.csv", "sg", "recent_form", "50", 1)
    original_input = _metric(tournament, csv_import_id=original_import)
    tmp_db.store_metrics([original_input])
    conn = tmp_db.get_conn()
    conn.execute("ALTER TABLE metrics ADD COLUMN source_captured_at TEXT")
    conn.execute("UPDATE metrics SET source_captured_at='2026-03-04T08:09:10.123Z'")
    conn.commit()
    conn.close()
    original = tmp_db.get_player_metrics(tournament, "source_player")[0]
    tmp_db.store_metrics([original_input, original_input])
    conn = tmp_db.get_conn()
    assert _versions(conn, "metrics") == []
    conn.close()
    refreshed = _metric(tournament, csv_import_id=refreshed_import, metric_value=2.5, metric_text="new source text")
    tmp_db.store_metrics([refreshed, refreshed, _metric(tournament, player_key="new_player")])
    conn = tmp_db.get_conn()
    try:
        assert _versions(conn, "metrics") == [original]
        assert tmp_db.get_player_metrics(tournament, "source_player") == [{
            "id": original["id"], **refreshed,
            "source_captured_at": original["source_captured_at"],
        }]
        assert conn.execute("SELECT filename FROM csv_imports WHERE id=?", (original["csv_import_id"],)).fetchone()[0] == "original.csv"
        assert len(tmp_db.get_player_metrics(tournament, "new_player")) == 1
    finally:
        conn.close()


def test_metric_update_and_journal_roll_back_together(tmp_db, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tournament = tmp_db.get_or_create_tournament("Rejected metric update", year=2026)
    original_input = _metric(tournament)
    tmp_db.store_metrics([original_input])
    original = tmp_db.get_player_metrics(tournament, "source_player")
    conn = tmp_db.get_conn()
    conn.execute("""CREATE TRIGGER reject_metric_update BEFORE UPDATE ON metrics
        BEGIN SELECT RAISE(ABORT, 'reject test update'); END""")
    conn.commit()
    conn.close()
    with pytest.raises(sqlite3.IntegrityError, match="reject test update"):
        tmp_db.store_metrics([_metric(tournament, player_key="new_player"), _metric(tournament, metric_value=9)])
    conn = tmp_db.get_conn()
    try:
        assert tmp_db.get_player_metrics(tournament, "source_player") == original
        assert tmp_db.get_player_metrics(tournament, "new_player") == []
        assert _versions(conn, "metrics") == []
    finally:
        conn.close()


def test_metric_identity_writes_serialize_without_unique_index_or_nonnull_keys(tmp_db, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tournament = tmp_db.get_or_create_tournament("Concurrent metric refresh", year=2026)
    conn = tmp_db.get_conn()
    conn.execute("DROP INDEX idx_metrics_unique")
    conn.commit()
    conn.close()
    row = _metric(tournament, data_mode=None, round_window=None)
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: tmp_db.store_metrics([row]), range(8)))
    assert len(tmp_db.get_player_metrics(tournament, "source_player")) == 1
    conn = tmp_db.get_conn()
    assert _versions(conn, "metrics") == []
    conn.close()


def test_explicit_opt_out_keeps_metric_updates_functional_without_journal(tmp_db, monkeypatch):
    monkeypatch.setenv("PRESERVE_PREDICTION_HISTORY", "0")
    tournament = tmp_db.get_or_create_tournament("Explicit metric policy", year=2026)
    tmp_db.store_metrics([_metric(tournament), _metric(tournament, metric_value=3)])
    conn = tmp_db.get_conn()
    try:
        assert _versions(conn, "metrics") == []
        assert tmp_db.get_player_metrics(tournament, "source_player")[0]["metric_value"] == 3
    finally:
        conn.close()
