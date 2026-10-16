"""New forecast writes remain usable when historical duplicates defer indexes."""

import json
from concurrent.futures import ThreadPoolExecutor


def _dirty_store(db):
    tournament = db.get_or_create_tournament("Preserved Duplicate Open", year=2026)
    conn = db.get_conn()
    db._migrate_prediction_log_timing(conn)
    for index in ("idx_picks_unique", "idx_results_unique", "idx_prediction_log_unique"):
        conn.execute(f"DROP INDEX {index}")
    for version in (1, 2):
        conn.execute("""INSERT INTO picks(tournament_id,model_variant,source,player_key,
            bet_type,market_type,opponent_key,opponent_display,market_book,market_odds,ev)
            VALUES(?,'baseline','cockpit','original','outright','outright','','','',?,0.2)""",
                     (tournament, f"+{500 + version}"))
        conn.execute("""INSERT INTO results(tournament_id,player_key,player_display,finish_position)
            VALUES(?,'original','Original',?)""", (tournament, version))
        conn.execute("""INSERT INTO prediction_log(tournament_id,player_key,bet_type,model_prob)
            VALUES(?,'original','outright',?)""", (tournament, version / 10))
    conn.commit()
    originals = {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
                 for table in ("picks", "results", "prediction_log")}
    conn.close()
    db.init_db()
    return tournament, originals


def _pick(tournament, player="new", **updates):
    return {"tournament_id": tournament, "player_key": player, "bet_type": "outright",
            "market_type": "outright", "market_odds": "+600", "model_prob": 0.2,
            "ev": 0.2, **updates}


def _result(player="new", **updates):
    return {"player_key": player, "player_display": player.title(), "finish_position": 3,
            "finish_text": "3", "made_cut": 1, **updates}


def _prediction(tournament, player="new", **updates):
    return {"tournament_id": tournament, "player_key": player, "bet_type": "outright",
            "model_prob": 0.2, "dg_prob": None, "market_implied_prob": None,
            "actual_outcome": None, "odds_decimal": 7, "profit": None,
            "odds_timing": "open", **updates}


def test_dirty_startup_admits_new_writes_without_changing_historical_duplicates(tmp_db, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tournament, originals = _dirty_store(tmp_db)
    tmp_db.store_picks([_pick(tournament)])
    tmp_db.store_results(tournament, [_result()])
    tmp_db.log_predictions([_prediction(tournament), _prediction(tournament, model_prob=0.9)])
    tmp_db.log_predictions([_prediction(tournament, "original", model_prob=0.99)])
    conn = tmp_db.get_conn()
    try:
        for table in originals:
            assert [dict(row) for row in conn.execute(
                f"SELECT * FROM {table} WHERE player_key='original' ORDER BY id"
            )] == originals[table]
            assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE player_key='new'").fetchone()[0] == 1
        assert conn.execute("SELECT model_prob FROM prediction_log WHERE player_key='new'").fetchone()[0] == 0.2
    finally:
        conn.close()


def test_dirty_current_corrections_retain_exact_original_row_versions(tmp_db, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tournament, originals = _dirty_store(tmp_db)
    tmp_db.store_picks([_pick(tournament, "original", market_odds="+900")])
    tmp_db.store_results(tournament, [_result("original", finish_position=4, finish_text="4")])
    conn = tmp_db.get_conn()
    try:
        archived = {}
        for row in conn.execute("SELECT source_table,payload_json FROM prediction_history_versions"):
            archived.setdefault(row["source_table"], []).append(json.loads(row["payload_json"]))
        for table in ("picks", "results"):
            current = [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
            assert len(current) == 2
            assert current[0] == originals[table][0]
            assert archived[table] == [originals[table][1]]
    finally:
        conn.close()


def test_dirty_writer_identity_checks_are_serialized_without_unique_indexes(tmp_db, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tournament, _ = _dirty_store(tmp_db)
    conn = tmp_db.get_conn()
    conn.execute("ALTER TABLE prediction_log DROP COLUMN odds_timing")
    conn.commit()
    conn.close()

    def write(_):
        tmp_db.store_picks([_pick(tournament)])
        tmp_db.store_results(tournament, [_result()])
        tmp_db.log_predictions([_prediction(tournament)])

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(write, range(8)))
    conn = tmp_db.get_conn()
    try:
        for table in ("picks", "results", "prediction_log"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE player_key='new'").fetchone()[0] == 1
    finally:
        conn.close()
