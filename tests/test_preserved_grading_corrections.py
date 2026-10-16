"""Preservation keeps original observations while legitimate grading progresses."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest


def result(player="review_player", finish=2):
    return {"player_key": player, "player_display": player.replace("_", " ").title(),
            "finish_position": finish, "finish_text": str(finish), "made_cut": 1}


def versions(conn, table):
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='prediction_history_versions'").fetchone():
        return []
    return [json.loads(r[0]) for r in conn.execute(
        "SELECT payload_json FROM prediction_history_versions WHERE source_table=? ORDER BY id", (table,))]


def test_identical_results_keep_original_time_without_journaling(tmp_db, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tid = tmp_db.get_or_create_tournament("Unchanged Results", year=2026)
    tmp_db.store_results(tid, [result()])
    conn = tmp_db.get_conn()
    conn.execute("UPDATE results SET entered_at='2026-01-01 12:00:00' WHERE tournament_id=?", (tid,))
    conn.commit()
    before = dict(conn.execute("SELECT * FROM results WHERE tournament_id=?", (tid,)).fetchone())
    conn.close()
    tmp_db.store_results(tid, [result(), result()])
    conn = tmp_db.get_conn()
    assert dict(conn.execute("SELECT * FROM results WHERE tournament_id=?", (tid,)).fetchone()) == before
    assert versions(conn, "results") == []
    conn.close()


def test_corrected_results_keep_exact_before_image_then_repeated_write_is_noop(tmp_db, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tid = tmp_db.get_or_create_tournament("Corrected Results", year=2026)
    tmp_db.store_results(tid, [result()])
    conn = tmp_db.get_conn()
    conn.execute("UPDATE results SET entered_at='2026-01-01 12:00:00' WHERE tournament_id=?", (tid,))
    conn.commit()
    before = dict(conn.execute("SELECT * FROM results WHERE tournament_id=?", (tid,)).fetchone())
    conn.close()
    tmp_db.store_results(tid, [result(finish=1)])
    conn = tmp_db.get_conn()
    after = dict(conn.execute("SELECT * FROM results WHERE tournament_id=?", (tid,)).fetchone())
    assert after["id"] == before["id"] and after["finish_position"] == 1
    assert after["entered_at"] != before["entered_at"]
    assert versions(conn, "results") == [before]
    conn.close()
    tmp_db.store_results(tid, [result(finish=1)])
    conn = tmp_db.get_conn()
    assert dict(conn.execute("SELECT * FROM results WHERE tournament_id=?", (tid,)).fetchone()) == after
    assert versions(conn, "results") == [before]
    conn.close()


def stub_pipeline(monkeypatch, corrected):
    monkeypatch.setattr("scripts.grade_tournament.fetch_event_results", lambda *a, **k: corrected)
    monkeypatch.setattr("scripts.grade_tournament.fetch_matchup_outcomes", lambda *a, **k: [])
    monkeypatch.setattr("src.market_row_backfill.backfill_completed_market_rows_into_picks", lambda *a, **k: 0)
    monkeypatch.setattr("src.learning.post_tournament_learn", lambda *a, **k: {})
    monkeypatch.setattr("src.grading_reconciliation.reconcile_grading", lambda **k: {"status": "ok", "events": []})
    monkeypatch.setattr("subprocess.run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""))


def seeded_grade(db):
    from src.learning import score_picks_for_tournament
    tid = db.get_or_create_tournament("Preserved Grading Review", year=2026, event_id="review")
    db.store_picks([{"tournament_id": tid, "model_variant": "baseline", "source": "cockpit",
                     "player_key": "review_player", "player_display": "Review Player",
                     "opponent_key": "", "bet_type": "outright", "market_type": "outright",
                     "market_odds": "+600", "model_prob": .2, "ev": .2}])
    db.store_results(tid, [result()])
    score_picks_for_tournament(tid)
    return tid


@pytest.mark.parametrize("finish,hit,profit", [(1, 1, 6), (3, 0, -1)])
def test_default_grade_rerun_corrects_unlocked_computed_loss_and_preserves_original(tmp_db, monkeypatch, finish, hit, profit):
    from scripts.grade_tournament import grade_tournament
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tid = seeded_grade(tmp_db)
    conn = tmp_db.get_conn()
    conn.execute("UPDATE pick_outcomes SET entered_at='2026-01-01 12:00:00'")
    conn.commit()
    original = dict(conn.execute("SELECT * FROM pick_outcomes").fetchone())
    assert original["hit"] == 0 and original["profit"] == -1
    conn.close()
    stub_pipeline(monkeypatch, [result(finish=finish)])
    report = grade_tournament("review", 2026, tournament_id=tid)
    conn = tmp_db.get_conn()
    current = dict(conn.execute("SELECT * FROM pick_outcomes").fetchone())
    assert current["hit"] == hit and current["profit"] == profit
    assert current["actual_finish"] == str(finish)
    assert current["id"] == original["id"] and current["entered_at"] == original["entered_at"]
    assert current["grading_authority"] == "computed" and current["outcome_locked"] == 0
    assert original in versions(conn, "pick_outcomes")
    assert conn.execute("SELECT COUNT(*) FROM pick_outcomes").fetchone()[0] == 1
    assert report["status"] == "complete" and report["steps"]["scoring"]["scored"] == 1
    conn.close()


@pytest.mark.parametrize("authority,locked,model_hit", [("computed", 1, 0), ("verified", 1, 0), ("verified", 0, 0), ("matchup_outcome", 0, 0), ("verified", 0, None)])
def test_default_grade_rerun_does_not_override_locked_or_authoritative_outcomes(tmp_db, monkeypatch, authority, locked, model_hit):
    from scripts.grade_tournament import grade_tournament
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tid = seeded_grade(tmp_db)
    conn = tmp_db.get_conn()
    conn.execute("UPDATE pick_outcomes SET grading_authority=?,outcome_locked=?,model_hit=?,notes='preserve authority',entered_at='2026-01-01 12:00:00'", (authority, locked, model_hit))
    conn.commit()
    original = dict(conn.execute("SELECT * FROM pick_outcomes").fetchone())
    conn.close()
    stub_pipeline(monkeypatch, [result(finish=1)])
    grade_tournament("review", 2026, tournament_id=tid)
    conn = tmp_db.get_conn()
    assert dict(conn.execute("SELECT * FROM pick_outcomes").fetchone()) == original
    assert original in versions(conn, "pick_outcomes")
    conn.close()


@pytest.mark.parametrize("existing_deferred_transaction", [False, True])
def test_outcome_journal_reserves_write_before_beforeimage_and_retains_it(tmp_db, monkeypatch, existing_deferred_transaction):
    from src.history_preservation import preserve_pick_outcome_versions
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tid = seeded_grade(tmp_db)
    conn = tmp_db.get_conn()
    original = dict(conn.execute("SELECT * FROM pick_outcomes").fetchone())
    if existing_deferred_transaction:
        conn.execute("BEGIN")
    trace = []
    conn.set_trace_callback(trace.append)
    preserve_pick_outcome_versions(conn, tid, reason="concurrent correction")
    assert conn.in_transaction
    if not existing_deferred_transaction:
        begin = next(i for i, q in enumerate(trace) if q == "BEGIN IMMEDIATE")
        read = next(i for i, q in enumerate(trace) if q.startswith("SELECT po.*"))
        assert begin < read

    def competing_write():
        other = sqlite3.connect(tmp_db.DB_PATH, timeout=.05)
        try:
            other.execute("UPDATE pick_outcomes SET notes='competing writer' WHERE id=?", (original["id"],))
            other.commit()
        finally:
            other.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        attempt = pool.submit(competing_write)
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            attempt.result(timeout=2)
    conn.execute("UPDATE pick_outcomes SET hit=1,model_hit=1,profit=6 WHERE id=?", (original["id"],))
    conn.commit()
    assert original in versions(conn, "pick_outcomes")
    assert conn.execute("SELECT hit,profit FROM pick_outcomes").fetchone()[0] == 1
    conn.close()


def test_scorer_rolls_back_and_releases_lock_on_error(tmp_db, monkeypatch):
    from src import learning
    tid = seeded_grade(tmp_db)
    conn = tmp_db.get_conn()
    original = dict(conn.execute("SELECT * FROM pick_outcomes").fetchone())
    conn.close()

    def interrupted(tournament_id, connection, **kwargs):
        assert connection.in_transaction
        connection.execute("UPDATE pick_outcomes SET notes='uncommitted scoring'")
        raise RuntimeError("interrupted scoring")

    monkeypatch.setattr(learning, "_score_picks_for_tournament", interrupted)
    with pytest.raises(RuntimeError, match="interrupted scoring"):
        learning.score_picks_for_tournament(tid, refresh_unlocked_computed=True)
    conn = tmp_db.get_conn()
    assert dict(conn.execute("SELECT * FROM pick_outcomes").fetchone()) == original
    conn.execute("BEGIN IMMEDIATE")  # The failed scorer no longer owns a write lock.
    conn.rollback()
    conn.close()


def test_results_share_caller_transaction_without_committing_or_deadlocking(tmp_db):
    tid = tmp_db.get_or_create_tournament("Atomic Fallback Results", year=2026)
    conn = tmp_db.get_conn()
    conn.execute("BEGIN IMMEDIATE")
    tmp_db.store_results(tid, [result()], conn=conn)
    assert conn.in_transaction
    assert conn.execute("SELECT COUNT(*) FROM results WHERE tournament_id=?", (tid,)).fetchone()[0] == 1
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM results WHERE tournament_id=?", (tid,)).fetchone()[0] == 0
    conn.close()


def test_ordinary_second_scoring_pass_keeps_authoritative_missing_model_hit(tmp_db):
    from src.learning import score_picks_for_tournament
    tid = seeded_grade(tmp_db)
    conn = tmp_db.get_conn()
    conn.execute("UPDATE pick_outcomes SET grading_authority='verified',model_hit=NULL,notes='verified source'")
    conn.commit()
    original = dict(conn.execute("SELECT * FROM pick_outcomes").fetchone())
    conn.close()
    tmp_db.store_results(tid, [result(finish=1)])
    score_picks_for_tournament(tid)  # post_tournament_learn uses this ordinary call.
    conn = tmp_db.get_conn()
    assert dict(conn.execute("SELECT * FROM pick_outcomes").fetchone()) == original
    conn.close()


def seeded_prediction(db):
    tid = db.get_or_create_tournament("Preserved Forecast Outcomes", year=2026)
    db.store_results(tid, [result()])
    db.log_predictions([{
        "tournament_id": tid, "player_key": "review_player", "bet_type": "outright",
        "model_prob": .23, "dg_prob": .2, "market_implied_prob": .15,
        "actual_outcome": 0, "odds_decimal": 7., "profit": -1.,
        "odds_timing": "pre_tournament",
    }])
    conn = db.get_conn()
    conn.execute("UPDATE prediction_log SET created_at='2026-01-01 12:00:00'")
    conn.commit()
    original = dict(conn.execute("SELECT * FROM prediction_log").fetchone())
    conn.close()
    return tid, original


def test_prediction_log_correction_preserves_full_before_image_and_forecast_then_noops(tmp_db, monkeypatch):
    from src.learning import update_prediction_outcomes
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tid, original = seeded_prediction(tmp_db)
    assert update_prediction_outcomes(tid) == 0
    tmp_db.store_results(tid, [result(finish=1)])
    assert update_prediction_outcomes(tid) == 1
    conn = tmp_db.get_conn()
    current = dict(conn.execute("SELECT * FROM prediction_log").fetchone())
    assert current == {**original, "actual_outcome": 1, "profit": 6.}
    assert versions(conn, "prediction_log") == [original]
    conn.close()
    assert update_prediction_outcomes(tid) == 0
    conn = tmp_db.get_conn()
    assert versions(conn, "prediction_log") == [original]
    assert dict(conn.execute("SELECT * FROM prediction_log").fetchone()) == current
    conn.close()


def test_prediction_log_correction_holds_write_lock_before_preservation(tmp_db, monkeypatch):
    from src import history_preservation, learning
    tid, original = seeded_prediction(tmp_db)
    tmp_db.store_results(tid, [result(finish=1)])
    preserve = history_preservation.preserve_prediction_row_versions
    captured = []

    def competing_write():
        other = sqlite3.connect(tmp_db.DB_PATH, timeout=.05)
        try:
            other.execute("UPDATE prediction_log SET actual_outcome=0,profit=-2 WHERE id=?", (original["id"],))
            other.commit()
        finally:
            other.close()

    def checked_preserve(conn, table, originals, **kwargs):
        assert conn.in_transaction and originals == [original]
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                pool.submit(competing_write).result(timeout=2)
        captured.extend(originals)
        return preserve(conn, table, originals, **kwargs)

    monkeypatch.setattr(history_preservation, "preserve_prediction_row_versions", checked_preserve)
    assert learning.update_prediction_outcomes(tid) == 1
    assert captured == [original]
    conn = tmp_db.get_conn()
    assert versions(conn, "prediction_log") == [original]
    assert conn.execute("SELECT actual_outcome,profit FROM prediction_log").fetchone()[1] == 6.
    conn.close()


def test_prediction_log_journal_and_update_roll_back_together_on_error(tmp_db, monkeypatch):
    from src import history_preservation, learning
    tid, original = seeded_prediction(tmp_db)
    tmp_db.store_results(tid, [result(finish=1)])
    preserve = history_preservation.preserve_prediction_row_versions

    def interrupted(conn, table, originals, **kwargs):
        preserve(conn, table, originals, **kwargs)
        raise RuntimeError("interrupted prediction correction")

    monkeypatch.setattr(history_preservation, "preserve_prediction_row_versions", interrupted)
    with pytest.raises(RuntimeError, match="interrupted prediction correction"):
        learning.update_prediction_outcomes(tid)
    conn = tmp_db.get_conn()
    assert dict(conn.execute("SELECT * FROM prediction_log").fetchone()) == original
    assert versions(conn, "prediction_log") == []
    conn.execute("BEGIN IMMEDIATE")
    conn.rollback()
    conn.close()
