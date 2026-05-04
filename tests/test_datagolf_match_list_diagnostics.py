"""Regression tests for `fetch_matchup_odds_with_diagnostics` payload handling.

Specifically: between events the DataGolf `betting-tools/matchups` endpoint
returns the literal string ``"no matchups posted."`` for the `match_list`
field. The diagnostics envelope must classify that as `empty_match_list`
rather than `invalid_match_list_type`, so downstream UIs treat it as the
benign "no markets posted yet" state and not as a hard API health alarm.
"""

from __future__ import annotations

import pytest

from src import datagolf


@pytest.mark.parametrize(
    "message",
    [
        "no matchups posted.",
        "No matchups posted.",
        "  no matchups posted.  ",
        "No markets posted yet.",
    ],
)
def test_no_matchups_string_classified_as_empty(monkeypatch, message):
    monkeypatch.setattr(
        datagolf,
        "_call_api",
        lambda endpoint, params, **kw: {"match_list": message},
    )
    rows, diag = datagolf.fetch_matchup_odds_with_diagnostics(
        market="tournament_matchups", tour="pga"
    )
    assert rows == []
    assert diag["reason_code"] == "empty_match_list"
    assert diag["match_list_type"] == "str"
    assert diag["match_list_message"] == message


def test_other_string_remains_invalid_match_list_type(monkeypatch):
    monkeypatch.setattr(
        datagolf,
        "_call_api",
        lambda endpoint, params, **kw: {"match_list": "unexpected garbage payload"},
    )
    rows, diag = datagolf.fetch_matchup_odds_with_diagnostics(
        market="tournament_matchups", tour="pga"
    )
    assert rows == []
    assert diag["reason_code"] == "invalid_match_list_type"


def test_list_payload_still_works(monkeypatch):
    monkeypatch.setattr(
        datagolf,
        "_call_api",
        lambda endpoint, params, **kw: {"match_list": [{"foo": 1}, {"foo": 2}]},
    )
    rows, diag = datagolf.fetch_matchup_odds_with_diagnostics(
        market="tournament_matchups", tour="pga"
    )
    assert len(rows) == 2
    assert diag["reason_code"] == "ok"
    assert diag["result_count"] == 2


def test_empty_list_payload_classified_empty(monkeypatch):
    monkeypatch.setattr(
        datagolf,
        "_call_api",
        lambda endpoint, params, **kw: {"match_list": []},
    )
    rows, diag = datagolf.fetch_matchup_odds_with_diagnostics(
        market="tournament_matchups", tour="pga"
    )
    assert rows == []
    assert diag["reason_code"] == "empty_match_list"
