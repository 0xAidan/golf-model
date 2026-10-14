"""Contract tests for the lightweight operator read model."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from src.operator_read_model import build_board, build_bootstrap


NOW = datetime(2026, 7, 31, 16, 0, tzinfo=timezone.utc)


def _section(
    *,
    event_id: str = "evt-100",
    event_name: str = "The Open",
    rankings: list[dict] | None = None,
    matchup_bets: list[dict] | None = None,
    eligibility: dict | None = None,
) -> dict:
    return {
        "source_event_id": event_id,
        "event_name": event_name,
        "course_name": "Royal Test",
        "rankings": rankings if rankings is not None else [{"player_name": "Champion Player", "rank": 1}],
        "matchup_bets": matchup_bets if matchup_bets is not None else [{"player_name": "Champion Player", "ev": 0.12}],
        "value_bets": [],
        "leaderboard": [],
        "eligibility": eligibility if eligibility is not None else {"verified": True, "code": "field_verified"},
    }


def _snapshot(**overrides: object) -> dict:
    snapshot = {
        "snapshot_id": "snap-100",
        "generated_at": NOW.isoformat(),
        "live_tournament": _section(),
        "upcoming_tournament": _section(event_id="evt-101", event_name="Next Event"),
        "lab_live_tournament": _section(
            event_id="evt-100",
            rankings=[{"player_name": "Challenger Player", "rank": 1}],
            matchup_bets=[{"player_name": "Challenger Player", "ev": 0.14}],
        ),
        "lab_upcoming_tournament": None,
    }
    snapshot.update(overrides)
    return snapshot


def test_champion_board_extracts_only_champion_section():
    board = build_board(_snapshot(), track="champion", mode="live", now=NOW)

    assert board["state"] == "fresh"
    assert board["source"]["section"] == "live_tournament"
    assert board["rankings"] == [{"player_name": "Champion Player", "rank": 1}]
    assert board["picks"]["matchups"] == [{"player_name": "Champion Player", "ev": 0.12}]


def test_challenger_board_extracts_only_challenger_section_without_fallback():
    snapshot = _snapshot(lab_live_tournament=None)

    board = build_board(snapshot, track="challenger", mode="live", now=NOW)

    assert board["state"] == "unavailable"
    assert board["reason"]["code"] == "challenger_lane_unavailable"
    assert board["rankings"] == []
    assert board["picks"]["matchups"] == []


def test_partial_sections_are_returned_without_inventing_missing_rows():
    snapshot = _snapshot(live_tournament=_section(matchup_bets=[]))

    board = build_board(snapshot, track="champion", mode="live", now=NOW)

    assert board["state"] == "fresh"
    assert board["rankings"]
    assert board["picks"]["matchups"] == []


def test_missing_section_is_explicitly_unavailable():
    board = build_board(_snapshot(live_tournament=None), track="champion", mode="live", now=NOW)

    assert board["state"] == "unavailable"
    assert board["reason"]["code"] == "section_unavailable"


def test_same_event_identity_failure_withholds_rows():
    snapshot = _snapshot(live_tournament=_section(event_id="evt-100"))

    board = build_board(
        snapshot,
        track="champion",
        mode="live",
        event_id="evt-other",
        now=NOW,
    )

    assert board["state"] == "unavailable"
    assert board["reason"]["code"] == "event_identity_mismatch"
    assert board["rankings"] == []


def test_valid_empty_picks_remain_a_fresh_board():
    snapshot = _snapshot(live_tournament=_section(matchup_bets=[], rankings=[]))

    board = build_board(snapshot, track="champion", mode="live", now=NOW)

    assert board["state"] == "empty"
    assert board["reason"]["code"] == "no_display_rows"
    assert board["picks"]["matchups"] == []


def test_stale_metadata_is_explicit_and_preserves_source_values():
    snapshot = _snapshot(generated_at=(NOW - timedelta(minutes=31)).isoformat())
    original_snapshot = deepcopy(snapshot)

    board = build_board(snapshot, track="champion", mode="live", stale_after_seconds=900, now=NOW)

    assert board["state"] == "stale"
    assert board["reason"]["code"] == "snapshot_stale"
    assert board["source"]["age_seconds"] == 1860
    assert snapshot == original_snapshot


def test_bootstrap_fail_closed_for_split_brain():
    bootstrap = build_bootstrap(
        _snapshot(),
        split_brain_reasons=["runtime_identity_mismatch"],
        now=NOW,
    )

    assert bootstrap["state"] == "unavailable"
    assert bootstrap["reason"]["code"] == "split_brain_detected"
    assert bootstrap["tracks"]["champion"]["live"]["available"] is False
    assert bootstrap["tracks"]["challenger"]["live"]["available"] is False


def test_value_markets_flatten_without_repricing_or_mutating_snapshot():
    section = _section(rankings=[], matchup_bets=[])
    section["value_bets"] = {
        "top10": [{"player": "A", "odds": "+220", "model_prob": 0.4, "ev": 0.28}],
        "win": [{"player": "B", "bet_type": "outright", "market_prob": 0.03, "ev": 0.11}],
        "malformed": {"player": "Do not treat this dictionary as a row list"},
        "top20": [None, "invalid", {"player": "C", "bet_type": None, "ev": 0.02}],
    }
    snapshot = _snapshot(upcoming_tournament=section)
    original = deepcopy(snapshot)

    board = build_board(snapshot, track="champion", mode="upcoming", now=NOW)

    assert board["state"] == "fresh"
    assert board["picks"]["value_bets"] == [
        {"player": "A", "bet_type": "top10", "odds": "+220", "model_prob": 0.4, "ev": 0.28},
        {"player": "B", "bet_type": "outright", "market_prob": 0.03, "ev": 0.11},
        {"player": "C", "bet_type": "top20", "ev": 0.02},
    ]
    assert snapshot == original


def test_value_bet_list_remains_exact_and_ignores_non_rows():
    row = {"player": "A", "odds": "+105", "ev": 0.03, "model_prob": 0.51}
    section = _section()
    section["value_bets"] = [row, None, "invalid"]

    board = build_board(_snapshot(live_tournament=section), track="champion", mode="live", now=NOW)

    assert board["picks"]["value_bets"] == [row]
    assert board["picks"]["value_bets"][0] is not row


def test_all_book_matchups_retain_each_supplied_line_without_changing_values():
    section = _section()
    lines = [
        {"pick": "A", "opponent": "B", "book": "fd", "odds": "+105", "ev": 0.08},
        {"pick": "A", "opponent": "B", "book": "dk", "odds": "+110", "ev": 0.10},
    ]
    section["matchup_bets_all_books"] = [*lines, None]

    board = build_board(_snapshot(live_tournament=section), track="champion", mode="live", now=NOW)

    assert board["picks"]["matchups"] == lines


@pytest.mark.parametrize("all_books", [None, [], {}, "invalid", [None, "invalid"]])
def test_empty_or_malformed_all_books_falls_back_to_card_rows(all_books):
    section = _section()
    section["matchup_bets_all_books"] = all_books

    board = build_board(_snapshot(live_tournament=section), track="champion", mode="live", now=NOW)

    assert board["picks"]["matchups"] == section["matchup_bets"]


def test_optional_metadata_exposes_only_market_counts_and_research_row_count():
    section = _section()
    section["diagnostics"] = {
        "market_counts": {
            "tournament_matchups": {"raw_rows": 8, "reason_code": "ok", "debug_rows": [{"ev": 100}]},
            "three_ball": {"raw_rows": 0, "reason_code": "empty_match_list"},
            "invalid": {"raw_rows": -1, "reason_code": ["invalid"]},
            "malformed": "invalid",
        },
        "failed_candidates": [{"player": "Do not publish", "ev": 100}],
    }
    section["live_groups_shadow"] = [{"players": ["a", "b", "c"], "model_probs": {"a": 0.5}}, None]
    original = deepcopy(section)

    board = build_board(_snapshot(live_tournament=section), track="champion", mode="live", now=NOW)

    assert board["metadata"] == {
        "market_counts": {
            "tournament_matchups": {"raw_rows": 8, "reason_code": "ok"},
            "three_ball": {"raw_rows": 0, "reason_code": "empty_match_list"},
        },
        "research_counts": {"live_groups_shadow": 1},
    }
    assert board["picks"]["matchups"] == section["matchup_bets"]
    assert "live_groups_shadow" not in board
    assert "diagnostics" not in board
    assert section == original


@pytest.mark.parametrize("generated_at", [None, "", "not-a-date", 42, {"timestamp": "invalid"}])
@pytest.mark.parametrize("mode", ["live", "upcoming"])
def test_current_board_withholds_rows_when_timestamp_cannot_prove_freshness(generated_at, mode):
    snapshot = _snapshot(generated_at=generated_at)

    board = build_board(snapshot, track="champion", mode=mode, now=NOW)
    bootstrap = build_bootstrap(snapshot, now=NOW)

    assert board["state"] == "unavailable"
    assert board["reason"]["code"] == "snapshot_timestamp_invalid"
    assert board["rankings"] == []
    assert board["picks"] == {"matchups": [], "value_bets": []}
    assert bootstrap["state"] == "unavailable"
    assert bootstrap["tracks"]["champion"][mode]["available"] is False


@pytest.mark.parametrize("generated_at", [None, "invalid", "2025-01-01T00:00:00+00:00"])
def test_past_replay_retains_archive_rows_without_requiring_a_current_timestamp(generated_at):
    section = _section()

    board = build_board(
        {"completed": section, "generated_at": generated_at},
        track="champion", mode="past", now=NOW,
    )

    assert board["state"] == ("stale" if generated_at and generated_at.startswith("2025") else "fresh")
    assert board["picks"]["matchups"] == section["matchup_bets"]


@pytest.mark.parametrize("eligibility", [False, "invalid", ["verified"]])
def test_malformed_eligibility_is_unavailable_without_raising(eligibility):
    section = _section()
    section["eligibility"] = eligibility

    board = build_board(_snapshot(live_tournament=section), track="champion", mode="live", now=NOW)

    assert board["state"] == "unavailable"
    assert board["eligibility"] == {}
    assert board["picks"]["matchups"] == []
