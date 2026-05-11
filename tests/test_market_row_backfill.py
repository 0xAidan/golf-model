"""Regression tests for gradeable completed market-row backfill."""


def test_backfill_completed_market_rows_into_picks_is_idempotent(tmp_db):
    from src.market_row_backfill import backfill_completed_market_rows_into_picks

    tid = tmp_db.get_or_create_tournament("Truist Championship", year=2025, event_id="480")
    tmp_db.store_market_prediction_rows(
        [
            _market_row(
                "dash-final",
                "upcoming",
                "480",
                "Dashboard Pick",
                "dashboard_pick",
                "Opponent",
                "opponent",
            ),
            _market_row(
                "lab-final",
                "lab_upcoming",
                "480",
                "Lab Pick",
                "lab_pick",
                "Opponent",
                "opponent",
            ),
        ]
    )

    first = backfill_completed_market_rows_into_picks("480", tid, source="dashboard")
    second = backfill_completed_market_rows_into_picks("480", tid, source="dashboard")
    lab = backfill_completed_market_rows_into_picks("480", tid, source="lab")

    conn = tmp_db.get_conn()
    rows = conn.execute(
        """
        SELECT source, model_variant, player_display, reasoning
        FROM picks
        WHERE tournament_id = ?
        ORDER BY source, player_display
        """,
        (tid,),
    ).fetchall()
    conn.close()

    assert first == 1
    assert second == 0
    assert lab == 1
    assert [(row["source"], row["model_variant"], row["player_display"]) for row in rows] == [
        ("cockpit", "baseline", "Dashboard Pick"),
        ("lab_sandbox", "v5", "Lab Pick"),
    ]
    assert all("market_prediction_rows" in row["reasoning"] for row in rows)


def test_backfill_completed_market_rows_normalizes_missing_player_keys(tmp_db):
    from src.market_row_backfill import backfill_completed_market_rows_into_picks

    tid = tmp_db.get_or_create_tournament("Truist Championship", year=2025, event_id="480")
    tmp_db.store_market_prediction_rows(
        [
            _market_row(
                "dash-final",
                "upcoming",
                "480",
                "Cameron Young",
                "",
                "Rory McIlroy",
                "",
            )
        ]
    )

    inserted = backfill_completed_market_rows_into_picks("480", tid, source="dashboard")

    conn = tmp_db.get_conn()
    row = conn.execute(
        """
        SELECT player_key, player_display, opponent_key, opponent_display
        FROM picks
        WHERE tournament_id = ?
        """,
        (tid,),
    ).fetchone()
    conn.close()

    assert inserted == 1
    assert dict(row) == {
        "player_key": "cameron_young",
        "player_display": "Cameron Young",
        "opponent_key": "rory_mcilroy",
        "opponent_display": "Rory McIlroy",
    }


def _market_row(
    snapshot_id: str,
    section: str,
    event_id: str,
    player_display: str,
    player_key: str,
    opponent_display: str,
    opponent_key: str,
) -> dict:
    return {
        "snapshot_id": snapshot_id,
        "generated_at": "2025-05-08T11:55:00+00:00",
        "tour": "pga",
        "section": section,
        "event_id": event_id,
        "event_name": "Truist Championship",
        "market_family": "matchup",
        "market_type": "tournament_matchups",
        "player_key": player_key,
        "player_display": player_display,
        "opponent_key": opponent_key,
        "opponent_display": opponent_display,
        "book": "fanduel",
        "odds": "-110",
        "model_prob": 0.56,
        "implied_prob": 0.52,
        "ev": 0.08,
        "is_value": 1,
        "payload_json": '{"tier":"GOOD","model_variant":"v5"}' if section.startswith("lab_") else '{"tier":"GOOD"}',
    }
