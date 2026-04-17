"""Tests for profile-oriented DB helper queries."""


def _metric_row(
    tournament_id: int,
    player_key: str,
    player_display: str,
    metric_category: str,
    metric_name: str,
    metric_value,
    *,
    data_mode: str = "recent_form",
    round_window: str = "all",
    metric_text=None,
):
    return {
        "tournament_id": tournament_id,
        "csv_import_id": None,
        "player_key": player_key,
        "player_display": player_display,
        "metric_category": metric_category,
        "data_mode": data_mode,
        "round_window": round_window,
        "metric_name": metric_name,
        "metric_value": metric_value,
        "metric_text": metric_text,
    }


def test_get_player_metrics_by_categories_filters_rows(tmp_db):
    tid = tmp_db.get_or_create_tournament("Filter Test", year=2026)
    tmp_db.store_metrics(
        [
            _metric_row(tid, "player_a", "Player A", "dg_skill", "sg_total", 1.2),
            _metric_row(tid, "player_a", "Player A", "meta", "teetime", None, metric_text="8:00 AM"),
            _metric_row(tid, "player_a", "Player A", "dg_approach", "approach_sg_composite", 0.15),
            _metric_row(tid, "player_b", "Player B", "dg_skill", "sg_total", 0.8),
        ]
    )

    rows = tmp_db.get_player_metrics_by_categories(tid, "player_a", ["dg_skill", "dg_approach"])
    assert len(rows) == 2
    assert {row["metric_category"] for row in rows} == {"dg_skill", "dg_approach"}
    assert {row["player_key"] for row in rows} == {"player_a"}


def test_get_tournament_metric_values_and_field_size_helpers(tmp_db):
    tid = tmp_db.get_or_create_tournament("Window Test", year=2026)
    tmp_db.store_metrics(
        [
            _metric_row(tid, "player_a", "Player A", "strokes_gained", "SG:TOT", 1.1, round_window="8"),
            _metric_row(tid, "player_b", "Player B", "strokes_gained", "SG:TOT", 0.6, round_window="8"),
            _metric_row(tid, "player_c", "Player C", "strokes_gained", "SG:TOT", -0.2, round_window="8"),
            _metric_row(tid, "player_a", "Player A", "meta", "field_status", None, metric_text="confirmed"),
            _metric_row(tid, "player_b", "Player B", "meta", "field_status", None, metric_text="confirmed"),
            _metric_row(tid, "player_c", "Player C", "meta", "teetime", None, metric_text="9:20 AM"),
        ]
    )

    values = tmp_db.get_tournament_metric_values(
        tid,
        "strokes_gained",
        "SG:TOT",
        data_mode="recent_form",
        round_window="8",
    )
    assert sorted(values) == [-0.2, 0.6, 1.1]
    assert tmp_db.get_tournament_field_size(tid) == 2

    fallback_tid = tmp_db.get_or_create_tournament("Fallback Field Size", year=2026)
    tmp_db.store_metrics(
        [
            _metric_row(fallback_tid, "player_x", "Player X", "dg_skill", "sg_total", 0.3),
            _metric_row(fallback_tid, "player_y", "Player Y", "dg_skill", "sg_total", 0.2),
        ]
    )
    assert tmp_db.get_tournament_field_size(fallback_tid) == 2
