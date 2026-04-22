"""Event format classification.

The production pipeline (composite scoring, placement value, individual H2H
matchups, card grading, calibration) assumes **individual stroke play**.

Tour events that use team formats (currently only the Zurich Classic of New
Orleans on the PGA Tour, played as Foursomes + Fourball) violate those
assumptions: a "player" row from DataGolf is really half of a pair, and
sportsbook placement markets / individual H2H lines do not exist or carry
entirely different pricing mechanics.

This module centralises event-format detection so the pipeline can guard
against producing misleading placement picks or individual matchups for
team events. Name-based classification is used because the DataGolf
`get-schedule` endpoint does not expose a reliable `format` field.

Add new team events here as the PGA Tour / DP World Tour schedule evolves.
"""

from __future__ import annotations

import re

EVENT_FORMAT_INDIVIDUAL = "individual"
EVENT_FORMAT_TEAM = "team"

# Case-insensitive regex patterns that identify team-format events.
# Keep this list small and well-justified: a false positive silently kills
# placement + matchup output for a week.
_TEAM_EVENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Zurich Classic of New Orleans — two-man teams, Foursomes + Fourball.
    re.compile(r"\bzurich\s+classic\b", re.IGNORECASE),
)


def classify_event_format(event_name: str | None, event_id: str | None = None) -> str:
    """Return ``"team"`` for known team-format events, else ``"individual"``.

    Parameters
    ----------
    event_name:
        Human-readable event name from DataGolf / schedule (e.g. ``"Zurich
        Classic of New Orleans"``). May be ``None``.
    event_id:
        DataGolf event_id. Currently unused — reserved for future
        schedule-driven classification.

    Returns
    -------
    str
        One of :data:`EVENT_FORMAT_INDIVIDUAL` or :data:`EVENT_FORMAT_TEAM`.
    """
    del event_id  # reserved for future schedule-based detection
    if not event_name:
        return EVENT_FORMAT_INDIVIDUAL

    name = event_name.strip()
    for pattern in _TEAM_EVENT_PATTERNS:
        if pattern.search(name):
            return EVENT_FORMAT_TEAM
    return EVENT_FORMAT_INDIVIDUAL


def is_team_event(event_name: str | None, event_id: str | None = None) -> bool:
    """Convenience wrapper: ``True`` if the event uses a team format."""
    return classify_event_format(event_name, event_id) == EVENT_FORMAT_TEAM


__all__ = [
    "EVENT_FORMAT_INDIVIDUAL",
    "EVENT_FORMAT_TEAM",
    "classify_event_format",
    "is_team_event",
]
