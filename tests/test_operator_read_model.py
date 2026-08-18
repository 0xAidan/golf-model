"""Contract tests for the lightweight operator read model."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

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
