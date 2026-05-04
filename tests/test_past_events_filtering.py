"""Regression tests for the past-events selector data layer.

Two long-standing defects motivated these tests:

1. The currently upcoming or live event was leaking into the past-events list
   because its pre-teeoff/upcoming snapshots accumulate in
   `live_snapshot_history`. The fix accepts an `exclude_event_ids` set.

2. When an event has been renamed mid-season (e.g. WGC Cadillac \u2192 Miami
   Championship \u2192 Cadillac Championship), the prior alphabetical-MAX query
   would return the wrong (often older) name. The fix uses the most recent
   `generated_at` row's name.
"""

from __future__ import annotations

import json


def _seed_history_row(
    db_mod,
    *,
    snapshot_id: str,
    generated_at: str,
    section: str,
    source_event_id: str,
    source_event_name: str,
    event_name: str | None = None,
    active: int = 0,
    payload: dict | None = None,
) -> None:
    conn = db_mod.get_conn()
    conn.execute(
        """
        INSERT INTO live_snapshot_history (
            snapshot_id, generated_at, tour, cadence_mode, section,
            event_id, event_name, source_event_id, source_event_name,
            active, payload_json
        )
        VALUES (?, ?, 'pga', 'live', ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_id,
            generated_at,
            section,
            source_event_id,
            event_name or source_event_name,
            source_event_id,
            source_event_name,
            int(active),
            json.dumps(payload or {}),
        ),
    )
    conn.commit()
    conn.close()


def test_past_events_uses_most_recent_event_name(tmp_db):
    """When an event is renamed, the latest name wins (not alphabetical MAX)."""
    # Older snapshot rows recorded the old name "Miami Championship".
    _seed_history_row(
        tmp_db,
        snapshot_id="s1",
        generated_at="2024-03-01T00:00:00+00:00",
        section="upcoming",
        source_event_id="556",
        source_event_name="Miami Championship",
    )
    # The most recent rows record the current name "Cadillac Championship".
    _seed_history_row(
        tmp_db,
        snapshot_id="s2",
        generated_at="2026-04-26T00:00:00+00:00",
        section="upcoming",
        source_event_id="556",
        source_event_name="Cadillac Championship",
    )

    rows = tmp_db.list_past_snapshot_events(limit=10)
    assert len(rows) == 1
    assert rows[0]["event_id"] == "556"
    # Crucially: NOT "Miami Championship" (which would win alphabetical MAX).
    assert rows[0]["event_name"] == "Cadillac Championship"


def test_past_events_excludes_active_event_id(tmp_db):
    """Excluded ids never appear in the result (live/upcoming guard)."""
    _seed_history_row(
        tmp_db,
        snapshot_id="s_zur",
        generated_at="2026-04-26T20:00:00+00:00",
        section="live",
        source_event_id="18",
        source_event_name="Zurich Classic of New Orleans",
    )
    _seed_history_row(
        tmp_db,
        snapshot_id="s_cad",
        generated_at="2026-04-27T16:00:00+00:00",
        section="upcoming",
        source_event_id="556",
        source_event_name="Cadillac Championship",
    )

    # Without exclusion both events show up.
    no_filter = tmp_db.list_past_snapshot_events(limit=10)
    assert {r["event_id"] for r in no_filter} == {"18", "556"}

    # With Cadillac excluded (it's the upcoming event) only Zurich remains.
    filtered = tmp_db.list_past_snapshot_events(
        limit=10, exclude_event_ids={"556"}
    )
    assert [r["event_id"] for r in filtered] == ["18"]
    assert filtered[0]["event_name"] == "Zurich Classic of New Orleans"


def test_completed_events_propagates_exclusion(tmp_db):
    """`list_completed_snapshot_events` must honour `exclude_event_ids`."""
    _seed_history_row(
        tmp_db,
        snapshot_id="s_zur",
        generated_at="2026-04-26T20:00:00+00:00",
        section="live",
        source_event_id="18",
        source_event_name="Zurich Classic of New Orleans",
    )
    _seed_history_row(
        tmp_db,
        snapshot_id="s_cad",
        generated_at="2026-04-27T16:00:00+00:00",
        section="upcoming",
        source_event_id="556",
        source_event_name="Cadillac Championship",
    )

    out = tmp_db.list_completed_snapshot_events(
        limit=10, exclude_event_ids={"556"}
    )
    assert [r["event_id"] for r in out] == ["18"]
