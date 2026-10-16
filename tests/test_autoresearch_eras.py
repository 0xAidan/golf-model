"""Era evidence requires its lane, configuration and bounded activation time."""

from src import autoresearch_operator as op


def _era(conn, config_hash, activated_at, status="retired"):
    conn.execute(
        """INSERT INTO track_configs (track, strategy_bundle_json, model_variant, config_hash, status, activated_at)
           VALUES ('lab', '{}', 'v5', ?, ?, ?)""",
        (config_hash, status, activated_at),
    )


def _pick(conn, pick_id, when, config_hash, *, lane="lab_sandbox", profit=1.0, variant="v5", stake=1.0):
    conn.execute(
        """INSERT INTO picks (id, tournament_id, player_key, opponent_key, bet_type, source,
                              model_variant, model_config_hash, created_at)
           VALUES (?, 1, ?, 'opponent', 'matchup', ?, ?, ?, ?)""",
        (pick_id, f"player-{pick_id}", lane, variant, config_hash, when),
    )
    conn.execute(
        "INSERT INTO pick_outcomes (pick_id, hit, stake, profit) VALUES (?, ?, ?, ?)",
        (pick_id, int(profit > 0), stake, profit),
    )


def test_eras_use_a_real_open_connection_and_disjoint_config_intervals(tmp_db):
    conn = tmp_db.get_conn()
    conn.execute("INSERT INTO tournaments (id, name, year, event_id) VALUES (1, 'T', 2026, 'event')")
    _era(conn, "first", "2026-01-01T00:00:00Z")
    _era(conn, "second", "2026-02-01T00:00:00+00:00", "active")
    _pick(conn, 1, "2026-01-10 00:00:00", "first")
    _pick(conn, 2, "2026-02-01 00:00:00", "second", profit=-1.0)
    _pick(conn, 3, "2026-02-10 00:00:00", "first", profit=9.0)
    _pick(conn, 4, "2026-01-20 00:00:00", "first", lane="cockpit", profit=50.0)
    _pick(conn, 5, "2026-01-20 00:00:00", None, profit=50.0)
    _pick(conn, 6, "2025-12-31 23:59:59", "first", profit=50.0)
    _pick(conn, 7, "2026-01-20 00:00:00", "first", variant="baseline", profit=50.0)
    conn.commit()
    conn.close()

    result = op.get_algorithm_eras()
    first, second = result["eras"]
    assert first["picks"] == 1
    assert first["roi_pct"] == 100.0
    assert first["ended_at"] == "2026-02-01T00:00:00+00:00"
    assert second["picks"] == 1
    assert second["roi_pct"] == -100.0
    assert sum(e["picks"] for e in result["eras"]) == 2
    assert result["all_time"]["picks"] == 7
    assert result["attribution"]["unattributed_picks"] == 5
    assert result["attribution"]["excluded"]["missing_config_hash"] == 1


def test_era_without_activation_or_config_evidence_is_empty(tmp_db):
    conn = tmp_db.get_conn()
    conn.execute("INSERT INTO tournaments (id, name, year, event_id) VALUES (1, 'T', 2026, 'event')")
    _era(conn, "unknown-start", None)
    _pick(conn, 1, "2026-01-10 00:00:00", "unknown-start")
    conn.commit()
    conn.close()

    result = op.get_algorithm_eras()
    assert result["eras"][0]["picks"] == 0
    assert result["eras"][0]["roi_pct"] is None
    assert result["eras"][0]["attribution_status"] == "missing_activation_time"
    assert result["attribution"]["unattributed_picks"] == 1


def test_unknown_stake_does_not_become_one_unit_roi(tmp_db):
    conn = tmp_db.get_conn()
    conn.execute("INSERT INTO tournaments (id, name, year, event_id) VALUES (1, 'T', 2026, 'event')")
    _era(conn, "first", "2026-01-01T00:00:00Z", "active")
    _pick(conn, 1, "2026-01-10 00:00:00", "first", stake=None)
    conn.commit()
    conn.close()

    result = op.get_algorithm_eras()
    assert result["eras"][0]["picks"] == 1
    assert result["eras"][0]["roi_pct"] is None
    assert result["eras"][0]["missing_financials"] == 1


def test_era_boundaries_use_utc_instants_and_one_locked_outcome_per_pick(tmp_db):
    conn = tmp_db.get_conn()
    conn.execute("INSERT INTO tournaments (id, name, year, event_id) VALUES (1, 'T', 2026, 'event')")
    _era(conn, "first", "2026-01-01T00:00:00Z")
    _era(conn, "second", "2026-02-01T00:00:00-05:00", "active")
    _pick(conn, 1, "2026-02-01T04:59:59Z", "first")
    _pick(conn, 2, "2026-02-01T05:00:00Z", "second", profit=-1.0)
    conn.execute("UPDATE pick_outcomes SET outcome_locked = 1 WHERE pick_id = 1")
    conn.execute("INSERT INTO pick_outcomes (pick_id, hit, stake, profit) VALUES (1, 0, 1, -1)")
    conn.commit()
    conn.close()

    result = op.get_algorithm_eras()
    first, second = result["eras"]
    assert first["picks"] == second["picks"] == 1
    assert first["roi_pct"] == 100.0
    assert second["roi_pct"] == -100.0
    assert result["all_time"]["picks"] == 2


def test_report_window_excludes_older_era_evidence_but_preserves_all_time(tmp_db):
    conn = tmp_db.get_conn()
    conn.execute("INSERT INTO tournaments (id, name, year, event_id) VALUES (1, 'T', 2026, 'event')")
    _era(conn, "first", "2000-01-01T00:00:00Z", "active")
    _pick(conn, 1, "2000-02-01T00:00:00Z", "first")
    conn.commit()
    conn.close()

    result = op.get_algorithm_eras(window_days=7)
    assert result["eras"][0]["picks"] == 0
    assert result["all_time"]["picks"] == 1
    assert result["attribution"]["excluded"]["outside_report_window"] == 1


def test_unresolved_outcome_is_not_a_graded_loss(tmp_db):
    conn = tmp_db.get_conn()
    conn.execute("INSERT INTO tournaments (id, name, year, event_id) VALUES (1, 'T', 2026, 'event')")
    _era(conn, "first", "2026-01-01T00:00:00Z", "active")
    _pick(conn, 1, "2026-01-10T00:00:00Z", "first")
    conn.execute("UPDATE pick_outcomes SET hit = NULL, profit = NULL WHERE pick_id = 1")
    conn.commit()
    conn.close()

    result = op.get_algorithm_eras()
    assert result["eras"][0]["picks"] == 0
    assert result["eras"][0]["win_rate_pct"] is None
    assert result["all_time"]["picks"] == 0
