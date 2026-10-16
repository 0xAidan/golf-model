"""Retained source versions must not inflate incumbent learning sample sizes."""
from src import db
from src.adaptation import aggregate_market_performance_for_tournament
from src.calibration import get_calibration_correction, update_calibration_curve


def test_retained_duplicate_versions_do_not_activate_calibration_or_count_as_extra_bets(tmp_db, monkeypatch):
    monkeypatch.setenv("PRESERVE_PREDICTION_HISTORY", "1")
    event = tmp_db.get_or_create_tournament("Preserved versions", year=2026)
    conn = tmp_db.get_conn()
    conn.execute("DROP INDEX idx_prediction_log_unique")
    conn.executemany("""INSERT INTO prediction_log
        (tournament_id,player_key,bet_type,model_prob,actual_outcome,profit)
        VALUES (?,?,?,?,?,?)""", [(event, "player_a", "top10", 0.1, 1, 9.0)] * 49)
    conn.execute("""INSERT INTO prediction_log
        (tournament_id,player_key,bet_type,model_prob,actual_outcome,profit)
        VALUES (?,?,?,?,?,?)""", (event, "player_a", "top10", 0.1, 0, -1.0))
    conn.commit()
    tmp_db._add_unique_constraints(conn)
    assert conn.execute("SELECT count(*) FROM prediction_log").fetchone()[0] == 50
    conn.close()

    observations = db.get_calibration_data()
    assert len(observations) == 1
    assert observations[0]["actual_outcome"] == 0
    curves = update_calibration_curve()
    assert curves["top10"]["10-20%"]["sample_size"] == 1
    assert get_calibration_correction(0.1, "top10") == 1.0
    record = aggregate_market_performance_for_tournament(event)["top10"]
    assert record["bets_placed"] == 1
    assert record["wins"] == 0
    assert record["losses"] == 1
    assert record["units_returned"] == 0
    with tmp_db.get_conn() as check:
        assert check.execute("SELECT count(*) FROM prediction_log").fetchone()[0] == 50


def test_operational_identity_keeps_events_players_and_markets_separate(tmp_db):
    first = tmp_db.get_or_create_tournament("First identity", year=2026)
    second = tmp_db.get_or_create_tournament("Second identity", year=2026)
    conn = tmp_db.get_conn()
    conn.execute("DROP INDEX idx_prediction_log_unique")
    identities = [(first, "a", "top10"), (first, "b", "top10"), (first, "a", "top20"), (second, "a", "top10")]
    conn.executemany("INSERT INTO prediction_log(tournament_id,player_key,bet_type) VALUES (?,?,?)", identities * 3)
    conn.commit()
    conn.close()
    assert len(tmp_db.get_calibration_data()) == 4
