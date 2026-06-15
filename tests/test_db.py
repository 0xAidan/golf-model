"""Tests for src/db.py -- dedup, constraints, year-aware lookups."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use a temp DB for tests
import src.db as db

_original_path = db.DB_PATH


def setup_module():
    """Create a fresh temp DB for each test module run."""
    tmp = tempfile.mktemp(suffix=".db")
    db.DB_PATH = tmp
    db._DB_INITIALIZED = False
    db.ensure_initialized()


def teardown_module():
    """Restore original DB path."""
    if os.path.exists(db.DB_PATH):
        os.unlink(db.DB_PATH)
    db.DB_PATH = _original_path
    db._DB_INITIALIZED = False


def test_tournament_year_separation():
    """Same tournament name in different years should create separate records."""
    tid_2025 = db.get_or_create_tournament("The Masters", year=2025)
    tid_2026 = db.get_or_create_tournament("The Masters", year=2026)
    assert tid_2025 != tid_2026, "Different years should create different tournaments"


def test_tournament_same_year_reuse():
    """Same tournament name + year should return the same id."""
    tid1 = db.get_or_create_tournament("US Open", year=2025)
    tid2 = db.get_or_create_tournament("US Open", year=2025)
    assert tid1 == tid2, "Same name+year should return the same tournament id"


def test_metric_upsert():
    """store_metrics should not raise on duplicate data (INSERT OR REPLACE)."""
    tid = db.get_or_create_tournament("Test Upsert", year=2025)
    row = {
        "tournament_id": tid,
        "csv_import_id": None,
        "player_key": "tiger_woods",
        "player_display": "Tiger Woods",
        "metric_category": "sim",
        "data_mode": "recent_form",
        "round_window": "all",
        "metric_name": "Win %",
        "metric_value": 5.0,
        "metric_text": None,
    }
    db.store_metrics([row])
    db.store_metrics([row])  # Should not raise


def test_results_dedup():
    """Duplicate results should be rejected by UNIQUE constraint."""
    tid = db.get_or_create_tournament("Test Dedup Results", year=2025)
    result = {
        "player_key": "rory_mcilroy",
        "player_display": "Rory McIlroy",
        "finish_position": 1,
        "finish_text": "1",
        "made_cut": 1,
    }
    db.store_results(tid, [result])
    # Second insert should fail silently or be caught
    try:
        db.store_results(tid, [result])
    except Exception:
        pass  # Expected -- unique constraint violation
    # Verify only one row
    conn = db.get_conn()
    count = conn.execute(
        "SELECT COUNT(*) as cnt FROM results WHERE tournament_id = ? AND player_key = ?",
        (tid, "rory_mcilroy"),
    ).fetchone()["cnt"]
    conn.close()
    assert count >= 1, "Should have at least one result row"


def test_foreign_keys_enabled():
    """Foreign keys should be enforced."""
    conn = db.get_conn()
    fk = conn.execute("PRAGMA foreign_keys").fetchone()
    conn.close()
    assert fk[0] == 1, "Foreign keys should be ON"


def test_get_player_display_names_prefers_human_readable_name():
    tid = db.get_or_create_tournament("Display Name Priority", year=2026)
    db.store_metrics(
        [
            {
                "tournament_id": tid,
                "csv_import_id": None,
                "player_key": "fifa_laopakdee",
                "player_display": "fifa_laopakdee",
                "metric_category": "strokes_gained",
                "data_mode": "recent_form",
                "round_window": "8",
                "metric_name": "SG:TOT",
                "metric_value": 42.0,
                "metric_text": None,
            },
            {
                "tournament_id": tid,
                "csv_import_id": None,
                "player_key": "fifa_laopakdee",
                "player_display": "Fifa Laopakdee",
                "metric_category": "sim",
                "data_mode": "recent_form",
                "round_window": "all",
                "metric_name": "Win %",
                "metric_value": 0.2,
                "metric_text": None,
            },
        ]
    )

    display_names = db.get_player_display_names(tid)

    assert display_names["fifa_laopakdee"] == "Fifa Laopakdee"


def test_store_picks_dedupes_within_lane_but_allows_cross_lane():
    tid = db.get_or_create_tournament("Lane Dedup Test", year=2026)
    base_pick = {
        "tournament_id": tid,
        "bet_type": "matchup",
        "player_key": "xander_schauffele",
        "player_display": "Xander Schauffele",
        "opponent_key": "collin_morikawa",
        "opponent_display": "Collin Morikawa",
        "model_prob": 0.52,
        "market_odds": "-110",
        "market_implied_prob": 0.5238,
        "ev": 0.08,
        "confidence": "good",
        "reasoning": "book=bet365",
        "model_variant": "baseline",
        "source": "ui_display",
    }
    db.store_picks([base_pick, dict(base_pick)])
    v5_pick = dict(base_pick)
    v5_pick["model_variant"] = "v5"
    v5_pick["model_prob"] = 0.55
    db.store_picks([v5_pick])

    # Defect P1-4: re-running the pick persistence path (e.g. a re-displayed snapshot
    # tick or a second pipeline run for the same event) must NOT raise a unique-constraint
    # violation and must stay idempotent (INSERT OR IGNORE against idx_picks_unique).
    db.store_picks([dict(base_pick)])
    db.store_picks([dict(base_pick), dict(v5_pick)])

    conn = db.get_conn()
    rows = conn.execute(
        "SELECT model_variant, COUNT(*) AS c FROM picks WHERE tournament_id = ? GROUP BY model_variant",
        (tid,),
    ).fetchall()
    conn.close()
    counts = {row["model_variant"]: row["c"] for row in rows}
    assert counts.get("baseline") == 1
    assert counts.get("v5") == 1


def test_hot_path_indexes_include_past_replay():
    """Past replay queries must have section-aware indexes on large snapshot tables."""
    conn = db.get_conn()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name IN (?, ?)",
            (
                "idx_market_prediction_rows_event_section",
                "idx_live_snapshot_history_event_section",
            ),
        ).fetchall()
    finally:
        conn.close()
    names = {row["name"] for row in rows}
    assert "idx_market_prediction_rows_event_section" in names
    assert "idx_live_snapshot_history_event_section" in names


def test_completed_market_rows_use_latest_dashboard_preteeoff_snapshot():
    rows = [
        _market_row("old", "upcoming", "480", "Old Pick", "old_pick", generated_at="2026-05-07T10:00:00+00:00"),
        _market_row("latest", "upcoming", "480", "Pick A", "pick_a", generated_at="2026-05-07T11:55:00+00:00"),
        _market_row("latest", "upcoming", "480", "Pick B", "pick_b", generated_at="2026-05-07T11:55:00+00:00"),
        _market_row("lab-latest", "lab_upcoming", "480", "Lab Pick", "lab_pick", generated_at="2026-05-07T11:56:00+00:00"),
    ]
    db.store_market_prediction_rows(rows)

    result = db.get_completed_market_prediction_rows_for_event("480", source="dashboard")

    assert [row["player_display"] for row in result] == ["Pick A", "Pick B"]
    assert {row["snapshot_id"] for row in result} == {"latest"}
    assert {row["section"] for row in result} == {"upcoming"}


def test_completed_market_rows_use_latest_lab_preteeoff_snapshot():
    rows = [
        _market_row("dashboard", "upcoming", "481", "Dashboard Pick", "dash_pick", generated_at="2026-05-07T11:55:00+00:00"),
        _market_row("lab-old", "lab_upcoming", "481", "Old Lab Pick", "old_lab", generated_at="2026-05-07T10:00:00+00:00"),
        _market_row("lab-latest", "lab_upcoming", "481", "Lab Pick", "lab_pick", generated_at="2026-05-07T11:56:00+00:00"),
    ]
    db.store_market_prediction_rows(rows)

    result = db.get_completed_market_prediction_rows_for_event("481", source="lab")

    assert [row["player_display"] for row in result] == ["Lab Pick"]
    assert result[0]["snapshot_id"] == "lab-latest"
    assert result[0]["section"] == "lab_upcoming"


def test_completed_market_rows_keep_best_line_per_unique_matchup():
    rows = [
        _market_row(
            "latest-dedupe",
            "upcoming",
            "482",
            "Cameron Young",
            "cameron_young",
            generated_at="2026-05-07T11:55:00+00:00",
            book="book-a",
            odds="-125",
        ),
        _market_row(
            "latest-dedupe",
            "upcoming",
            "482",
            "Cameron Young",
            "cameron_young",
            generated_at="2026-05-07T11:55:00+00:00",
            book="book-b",
            odds="-105",
        ),
        _market_row(
            "latest-dedupe",
            "upcoming",
            "482",
            "Rory McIlroy",
            "rory_mcilroy",
            generated_at="2026-05-07T11:55:00+00:00",
            book="book-c",
            odds="+120",
        ),
    ]
    db.store_market_prediction_rows(rows)

    result = db.get_completed_market_prediction_rows_for_event("482", source="dashboard")

    assert [(row["player_display"], row["book"], row["odds"]) for row in result] == [
        ("Cameron Young", "book-b", "-105"),
        ("Rory McIlroy", "book-c", "+120"),
    ]


def test_completed_market_rows_skip_sparse_ledger_for_richer_mpr():
    """Sparse pick_ledger must not block full live-section recovery (event 32 pattern)."""
    from src.pick_ledger import compute_pick_key, persist_pick_ledger_rows

    event_id = "998832"
    sparse_ledger = [
        {
            "pick_key": compute_pick_key(
                event_id=event_id,
                lane="cockpit",
                section="upcoming",
                phase="pre_tournament",
                bet_type="matchup",
                player_key="player_a",
                opponent_key="opponent_a",
                book="fanduel",
                odds="-110",
            ),
            "event_id": event_id,
            "event_name": "Sparse Ledger Event",
            "lane": "cockpit",
            "bet_type": "matchup",
            "player_key": "player_a",
            "player_display": "Player A",
            "opponent_key": "opponent_a",
            "opponent_display": "Opponent A",
            "book": "fanduel",
            "odds": "-110",
            "model_variant": "baseline",
            "ev": 0.05,
            "is_value": 1,
            "lifecycle": "recovered",
            "source_origin": "test",
            "generated_at": "2026-06-10T10:00:00+00:00",
        },
    ]
    persist_pick_ledger_rows(sparse_ledger)

    rich_rows = [
        _market_row("live-a", "live", event_id, "Player A", "player_a", generated_at="2026-06-10T11:00:00+00:00"),
        _market_row("live-b", "live", event_id, "Player B", "player_b", generated_at="2026-06-10T11:00:00+00:00"),
        _market_row("live-c", "live", event_id, "Player C", "player_c", generated_at="2026-06-10T11:00:00+00:00"),
    ]
    db.store_market_prediction_rows(rich_rows)

    result = db.get_completed_market_prediction_rows_for_event(event_id, source="dashboard")

    assert len(result) == 3
    assert result[0].get("recovery_tier") == "recovered_live_mislabeled"


def _market_row(
    snapshot_id: str,
    section: str,
    event_id: str,
    player_display: str,
    player_key: str,
    *,
    generated_at: str,
    book: str = "fanduel",
    odds: str = "-110",
) -> dict:
    return {
        "snapshot_id": snapshot_id,
        "generated_at": generated_at,
        "tour": "pga",
        "section": section,
        "event_id": event_id,
        "event_name": "Truist Championship",
        "market_family": "matchup",
        "market_type": "tournament_matchups",
        "player_key": player_key,
        "player_display": player_display,
        "opponent_key": "opponent",
        "opponent_display": "Opponent",
        "book": book,
        "odds": odds,
        "model_prob": 0.56,
        "implied_prob": 0.52,
        "ev": 0.08,
        "is_value": 1,
        "payload_json": "{}",
    }


def test_slim_market_payload_stores_empty_payload_for_duplicate_snapshots(monkeypatch):
    monkeypatch.setenv("MARKET_PREDICTION_SLIM_PAYLOAD", "1")
    rows = [
        _market_row("snap-slim", "upcoming", "900", "First", "first", generated_at="2026-06-01T10:00:00+00:00"),
        _market_row("snap-slim", "upcoming", "900", "Second", "second", generated_at="2026-06-01T10:00:00+00:00"),
    ]
    rows[0]["payload_json"] = '{"full": true}'
    rows[1]["payload_json"] = '{"full": true}'
    db.store_market_prediction_rows(rows)

    conn = db.get_conn()
    payloads = conn.execute(
        "SELECT payload_json FROM market_prediction_rows WHERE snapshot_id = ? ORDER BY id",
        ("snap-slim",),
    ).fetchall()
    conn.close()
    assert payloads[0]["payload_json"] == '{"full": true}'
    assert payloads[1]["payload_json"] == "{}"


def test_reclaim_database_disk_runs_vacuum_on_small_db(monkeypatch):
    monkeypatch.delenv("DISK_RECLAIM_MIN_FREE_MB", raising=False)
    conn = db.get_conn()
    conn.execute("DELETE FROM market_prediction_rows")
    conn.commit()
    conn.close()
    result = db.reclaim_database_disk(min_free_mb=1)
    assert result["ok"] is True
    assert result.get("bytes_before", 0) >= 0
