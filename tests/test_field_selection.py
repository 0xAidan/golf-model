"""Tests for strict field parsing, storage, and filtering."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_store_field_as_metrics_marks_confirmed_field_and_primary_teetime(tmp_db):
    from src.datagolf import _store_field_as_metrics

    tid = tmp_db.get_or_create_tournament("Masters Tournament", year=2026)

    stored = _store_field_as_metrics(
        [
            {
                "player_name": "Collin Morikawa",
                "dg_id": 555,
                "teetimes": [
                    {
                        "round_num": 1,
                        "teetime": "2026-04-09 10:04",
                        "course_name": "Augusta National Golf Club",
                        "course_num": 14,
                    },
                    {
                        "round_num": 2,
                        "teetime": "2026-04-10 13:08",
                        "course_name": "Augusta National Golf Club",
                        "course_num": 14,
                    },
                ],
            }
        ],
        tid,
    )

    assert stored > 0
    rows = tmp_db.get_player_metrics(tid, "collin_morikawa")

    assert any(
        row["metric_name"] == "field_status" and row["metric_text"] == "confirmed"
        for row in rows
    )
    assert any(
        row["metric_name"] == "teetime" and row["metric_text"] == "2026-04-09 10:04"
        for row in rows
    )


def test_get_all_players_prefers_explicit_confirmed_field_rows(tmp_db):
    tid = tmp_db.get_or_create_tournament("Strict Field", year=2026)

    tmp_db.store_metrics(
        [
            {
                "tournament_id": tid,
                "csv_import_id": None,
                "player_key": "in_field_a",
                "player_display": "In Field A",
                "metric_category": "meta",
                "data_mode": "recent_form",
                "round_window": "all",
                "metric_name": "field_status",
                "metric_value": None,
                "metric_text": "confirmed",
            },
            {
                "tournament_id": tid,
                "csv_import_id": None,
                "player_key": "in_field_b",
                "player_display": "In Field B",
                "metric_category": "meta",
                "data_mode": "recent_form",
                "round_window": "all",
                "metric_name": "field_status",
                "metric_value": None,
                "metric_text": "confirmed",
            },
            {
                "tournament_id": tid,
                "csv_import_id": None,
                "player_key": "phantom_meta_player",
                "player_display": "Phantom Meta Player",
                "metric_category": "meta",
                "data_mode": "recent_form",
                "round_window": "all",
                "metric_name": "dg_id",
                "metric_value": 777,
                "metric_text": None,
            },
            {
                "tournament_id": tid,
                "csv_import_id": None,
                "player_key": "phantom_sim_player",
                "player_display": "Phantom Sim Player",
                "metric_category": "sim",
                "data_mode": "recent_form",
                "round_window": "all",
                "metric_name": "Win %",
                "metric_value": 1.2,
                "metric_text": None,
            },
        ]
    )

    strict_players = tmp_db.get_all_players(tid, confirmed_field_only=True)
    loose_players = tmp_db.get_all_players(tid, confirmed_field_only=False)

    assert set(strict_players) == {"in_field_a", "in_field_b"}
    assert set(loose_players) == {
        "in_field_a",
        "in_field_b",
        "phantom_meta_player",
        "phantom_sim_player",
    }


def test_filter_rows_to_field_reports_missing_and_extra_players():
    from src.field_selection import filter_rows_to_field

    rows = [
        {"player_key": "scottie_scheffler", "player_display": "Scottie Scheffler"},
        {"player_key": "ghost_player", "player_display": "Ghost Player"},
    ]

    filtered, audit = filter_rows_to_field(
        rows,
        ["scottie_scheffler", "rory_mcilroy"],
    )

    assert [row["player_key"] for row in filtered] == ["scottie_scheffler"]
    assert audit["extra_player_keys"] == ["ghost_player"]
    assert audit["missing_player_keys"] == ["rory_mcilroy"]


def test_get_all_players_strict_mode_fails_closed_without_field_markers(tmp_db):
    tid = tmp_db.get_or_create_tournament("No Field Markers", year=2026)
    tmp_db.store_metrics(
        [
            {
                "tournament_id": tid,
                "csv_import_id": None,
                "player_key": "phantom_player",
                "player_display": "Phantom Player",
                "metric_category": "sim",
                "data_mode": "recent_form",
                "round_window": "all",
                "metric_name": "Win %",
                "metric_value": 1.5,
                "metric_text": None,
            }
        ]
    )

    strict_players = tmp_db.get_all_players(tid, confirmed_field_only=True)
    loose_players = tmp_db.get_all_players(tid, confirmed_field_only=False)

    assert strict_players == []
    assert loose_players == ["phantom_player"]


def test_get_all_players_strict_mode_fails_closed_with_legacy_meta_only(tmp_db):
    tid = tmp_db.get_or_create_tournament("Legacy Meta Only", year=2026)
    tmp_db.store_metrics(
        [
            {
                "tournament_id": tid,
                "csv_import_id": None,
                "player_key": "legacy_player",
                "player_display": "Legacy Player",
                "metric_category": "meta",
                "data_mode": "recent_form",
                "round_window": "all",
                "metric_name": "dg_id",
                "metric_value": 321,
                "metric_text": None,
            }
        ]
    )

    strict_players = tmp_db.get_all_players(tid, confirmed_field_only=True)
    loose_players = tmp_db.get_all_players(tid, confirmed_field_only=False)

    assert strict_players == []
    assert loose_players == ["legacy_player"]


def test_filter_rows_to_field_drops_rows_with_missing_player_key():
    from src.field_selection import filter_rows_to_field

    rows = [
        {"player_key": "", "player_display": "Missing Key Player"},
        {"player_key": "scottie_scheffler", "player_display": "Scottie Scheffler"},
    ]

    filtered, audit = filter_rows_to_field(rows, ["scottie_scheffler"])

    assert [row["player_key"] for row in filtered] == ["scottie_scheffler"]
    assert "<missing_player_key>" in audit["extra_player_keys"]


def test_filter_rows_to_field_fails_closed_when_field_missing():
    from src.field_selection import filter_rows_to_field

    rows = [
        {"player_key": "scottie_scheffler", "player_display": "Scottie Scheffler"},
        {"player_key": "jon_rahm", "player_display": "Jon Rahm"},
    ]

    filtered, audit = filter_rows_to_field(rows, [])

    assert filtered == []
    assert audit["strict_field_missing"] is True
    assert audit["kept_rows"] == 0


def test_sync_tournament_returns_raw_decompositions_for_profile_fallback(monkeypatch):
    from src.datagolf import sync_tournament

    monkeypatch.setattr("src.datagolf.fetch_historical_rounds", lambda tour, event_id, year: [])
    monkeypatch.setattr("src.datagolf._parse_rounds_response", lambda raw, tour, year: [])
    monkeypatch.setattr("src.db.get_rounds_count", lambda: 0)
    monkeypatch.setattr("src.db.store_rounds", lambda rows: None)
    monkeypatch.setattr("src.datagolf.fetch_pre_tournament", lambda tour: [])
    monkeypatch.setattr("src.datagolf._store_predictions_as_metrics", lambda preds, tournament_id: 0)
    monkeypatch.setattr("src.datagolf.fetch_decompositions", lambda tour: [{"player_name": "Scottie Scheffler"}])
    monkeypatch.setattr("src.datagolf._store_decompositions_as_metrics", lambda decomps, tournament_id: 1)
    monkeypatch.setattr("src.datagolf.fetch_field_updates", lambda tour: [])
    monkeypatch.setattr("src.datagolf._store_field_as_metrics", lambda field, tournament_id: 0)

    summary = sync_tournament(7, tour="pga")

    assert summary["decompositions_raw"] == [{"player_name": "Scottie Scheffler"}]
