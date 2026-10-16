"""A season-wide pick migration must never deduplicate across tournaments."""

import pytest

from src.official_pick_record import dedupe_grading_picks, dedupe_picks_by_grading_identity


def _pick(tournament_id, **overrides):
    return {
        "tournament_id": tournament_id,
        "source": "cockpit",
        "model_variant": "baseline",
        "bet_type": "matchup",
        "market_type": "tournament_matchups",
        "player_key": "scottie_scheffler",
        "player_display": "Scottie Scheffler",
        "opponent_key": "rory_mcilroy",
        "opponent_display": "Rory McIlroy",
        "market_odds": "-110",
        "market_book": "fd",
        **overrides,
    }


@pytest.mark.parametrize("bet_type", ["matchup", "outright", "top10"])
def test_grading_record_keeps_repeated_players_in_different_events(bet_type):
    market_type = "tournament_matchups" if bet_type == "matchup" else bet_type
    first = _pick(10, bet_type=bet_type, market_type=market_type)
    second = _pick(20, bet_type=bet_type, market_type=market_type, market_odds="+120")

    assert dedupe_grading_picks([first, second]) == [first, second]


def test_same_event_best_odds_still_respects_market_lane_and_model():
    base = _pick(10)
    better_line = _pick(10, market_odds="+120", market_book="dk")
    round_pick = _pick(10, market_type="round_matchups")
    lab_pick = _pick(10, source="lab_sandbox")
    alternate_model = _pick(10, model_variant="v5")

    assert dedupe_grading_picks(
        [base, better_line, round_pick, lab_pick, alternate_model],
    ) == [better_line, round_pick, lab_pick, alternate_model]


def _insert_pick(conn, pick):
    columns = ", ".join(pick)
    placeholders = ", ".join("?" for _ in pick)
    return conn.execute(
        f"INSERT INTO picks ({columns}) VALUES ({placeholders})",
        tuple(pick.values()),
    ).lastrowid


def _rows(conn, table):
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]


@pytest.mark.parametrize("full_init", [False, True])
def test_unique_index_migration_preserves_each_events_canonical_outcomes(tmp_db, full_init):
    first_event = tmp_db.get_or_create_tournament("The Masters", year=2025)
    second_event = tmp_db.get_or_create_tournament("The Masters", year=2026)
    conn = tmp_db.get_conn()
    try:
        # Reproduce the real migration entrypoint for the old book-specific index.
        conn.execute("DROP INDEX idx_picks_unique")
        conn.execute(
            "CREATE UNIQUE INDEX idx_picks_unique ON picks "
            "(tournament_id, player_key, opponent_key, market_book, market_odds)",
        )
        first_pick = _insert_pick(conn, _pick(first_event))
        second_pick = _insert_pick(conn, _pick(second_event, market_odds="+120"))
        for pick_id, hit, profit in [(first_pick, 0, -1.0), (second_pick, 1, 1.2)]:
            conn.execute(
                """INSERT INTO pick_outcomes
                   (pick_id, hit, model_hit, profit, stake, grading_authority, outcome_locked, notes)
                   VALUES (?, ?, ?, ?, 1.0, 'trackRecord_json', 1, 'canonical season result')""",
                (pick_id, hit, hit, profit),
            )
        conn.commit()
        original_picks = _rows(conn, "picks")
        original_outcomes = _rows(conn, "pick_outcomes")

        if full_init:
            tmp_db.init_db()
        else:
            tmp_db._migrate_picks_unique_index(conn)

        assert _rows(conn, "picks") == original_picks
        assert _rows(conn, "pick_outcomes") == original_outcomes
        assert dedupe_picks_by_grading_identity(conn) == {"removed": 0, "kept": 2}
        assert _rows(conn, "pick_outcomes") == original_outcomes
    finally:
        conn.close()


def test_persistent_rows_without_event_identity_are_never_deleted(tmp_db):
    conn = tmp_db.get_conn()
    try:
        first = _insert_pick(conn, _pick(None))
        second = _insert_pick(conn, _pick(None, market_odds="+120"))
        for pick_id in [first, second]:
            conn.execute(
                "INSERT INTO pick_outcomes (pick_id, hit, profit, outcome_locked) VALUES (?, 1, 1.0, 1)",
                (pick_id,),
            )
        conn.commit()
        original_picks = _rows(conn, "picks")
        original_outcomes = _rows(conn, "pick_outcomes")

        assert dedupe_picks_by_grading_identity(conn) == {"removed": 0, "kept": 2}
        assert _rows(conn, "picks") == original_picks
        assert _rows(conn, "pick_outcomes") == original_outcomes
    finally:
        conn.close()


@pytest.mark.parametrize("endpoint", ["history", "season"])
def test_grading_api_season_summary_counts_same_matchup_at_each_event(tmp_db, monkeypatch, endpoint):
    import app as app_module
    from fastapi.testclient import TestClient
    from src.routes import grading_season

    monkeypatch.setattr(grading_season, "_load_track_record_events", lambda: [])
    conn = tmp_db.get_conn()
    try:
        event_ids = []
        for index, (hit, profit, odds) in enumerate([(0, -1.0, "-110"), (1, 1.2, "+120")]):
            tournament_id = tmp_db.get_or_create_tournament(f"Isolation Open {index}", year=2026)
            event_ids.append(tournament_id)
            conn.execute(
                "UPDATE tournaments SET event_id = ? WHERE id = ?",
                (f"isolation-{index}", tournament_id),
            )
            for source, variant in [("cockpit", "baseline"), ("lab_sandbox", "v5")]:
                pick_id = _insert_pick(conn, _pick(
                    tournament_id, market_odds=odds, source=source, model_variant=variant,
                ))
                conn.execute(
                    """INSERT INTO pick_outcomes
                       (pick_id, hit, profit, stake, grading_authority, outcome_locked)
                       VALUES (?, ?, ?, 1.0, 'trackRecord_json', 1)""",
                    (pick_id, hit, profit),
                )
            conn.commit()
        original_picks = _rows(conn, "picks")
        original_outcomes = _rows(conn, "pick_outcomes")

        client = TestClient(app_module.app)
        if endpoint == "history":
            response = client.get("/api/grading/history?pick_source=cockpit")
            assert response.status_code == 200
            payload = response.json()
            summary = payload["summary"]["combined"]
            rows = [pick for event in payload["tournaments"] for pick in event["picks"]]
            summaries = [summary]
        else:
            response = client.get("/api/grading/season?year=2026&include_picks=true")
            assert response.status_code == 200
            payload = response.json()
            summaries = [payload["summary"][lane] for lane in ["dashboard", "lab"]]
            rows = [pick for event in payload["events"] for pick in event["lanes"]["dashboard"]["picks"]]

        for summary in summaries:
            assert summary["picks"] == 2
            assert summary["wins"] == 1
            assert summary["losses"] == 1
            assert summary["profit"] == pytest.approx(0.2)
        assert {pick["tournament_id"] for pick in rows} == set(event_ids)
        assert _rows(conn, "picks") == original_picks
        assert _rows(conn, "pick_outcomes") == original_outcomes
    finally:
        conn.close()


def test_global_dedupe_only_collapses_true_duplicates_within_each_event(tmp_db, monkeypatch):
    monkeypatch.setenv("PRESERVE_PREDICTION_HISTORY", "0")
    first_event = tmp_db.get_or_create_tournament("First Event", year=2026)
    second_event = tmp_db.get_or_create_tournament("Second Event", year=2026)
    conn = tmp_db.get_conn()
    try:
        conn.execute("DROP INDEX idx_picks_unique")
        duplicate = _insert_pick(conn, _pick(first_event))
        retained = _insert_pick(conn, _pick(first_event, market_odds="+120", market_book="dk"))
        other_event = _insert_pick(conn, _pick(second_event, market_odds="+130"))
        round_pick = _insert_pick(conn, _pick(first_event, market_type="round_matchups"))
        lab_pick = _insert_pick(conn, _pick(first_event, source="lab_sandbox"))
        alternate_model = _insert_pick(conn, _pick(first_event, model_variant="v5"))
        conn.execute(
            """INSERT INTO pick_outcomes
               (pick_id, hit, profit, grading_authority, outcome_locked)
               VALUES (?, 1, 1.2, 'trackRecord_json', 1)""",
            (retained,),
        )
        conn.commit()
        original_outcomes = _rows(conn, "pick_outcomes")

        assert dedupe_picks_by_grading_identity(conn) == {"removed": 1, "kept": 5}

        assert {row["id"] for row in _rows(conn, "picks")} == {
            retained, other_event, round_pick, lab_pick, alternate_model,
        }
        assert conn.execute("SELECT 1 FROM picks WHERE id = ?", (duplicate,)).fetchone() is None
        assert _rows(conn, "pick_outcomes") == original_outcomes
    finally:
        conn.close()
