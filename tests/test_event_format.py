"""Tests for src.event_format classification."""

import pytest

from src.event_format import (
    EVENT_FORMAT_INDIVIDUAL,
    EVENT_FORMAT_TEAM,
    classify_event_format,
    is_team_event,
)


@pytest.mark.parametrize(
    "name",
    [
        "Zurich Classic of New Orleans",
        "zurich classic of new orleans",
        "ZURICH CLASSIC OF NEW ORLEANS",
        "The Zurich Classic",
        "Zurich Classic",
    ],
)
def test_zurich_is_classified_as_team(name):
    assert classify_event_format(name) == EVENT_FORMAT_TEAM
    assert is_team_event(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "RBC Heritage",
        "Masters Tournament",
        "The Players Championship",
        "Cognizant Classic",  # 'Classic' alone must not match Zurich
        "Arnold Palmer Invitational",
        "U.S. Open",
        "PGA Championship",
        "Valero Texas Open",
        "3M Open",
        "",
    ],
)
def test_regular_events_are_individual(name):
    assert classify_event_format(name) == EVENT_FORMAT_INDIVIDUAL
    assert is_team_event(name) is False


def test_none_event_name_defaults_to_individual():
    assert classify_event_format(None) == EVENT_FORMAT_INDIVIDUAL
    assert is_team_event(None) is False


def test_event_id_argument_is_accepted_and_ignored():
    # Reserved for future schedule-based classification; must not raise.
    assert classify_event_format("Zurich Classic", event_id="480") == EVENT_FORMAT_TEAM
    assert classify_event_format("RBC Heritage", event_id="012") == EVENT_FORMAT_INDIVIDUAL


def test_whitespace_is_tolerated():
    assert classify_event_format("  Zurich Classic of New Orleans  ") == EVENT_FORMAT_TEAM
