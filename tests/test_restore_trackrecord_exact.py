"""Restore imports trackRecord pl/result verbatim."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src import db
from scripts.restore_season_record import import_track_record


def test_import_trackrecord_copies_pl_verbatim(tmp_db):
    track = {
        "events": [
            {
                "name": "Test Event",
                "course": "Test Course",
                "picks": [
                    {
                        "pick": "Shane Lowry",
                        "opponent": "Sam Burns",
                        "odds": "+103",
                        "result": "win",
                        "pl": 1.03,
                    }
                ],
            }
        ]
    }
    conn = db.get_conn()
    conn.execute(
        """
        INSERT INTO rounds (dg_id, player_name, player_key, tour, season, year, event_id, event_name, event_completed, round_num, score)
        VALUES (1, 'Shane Lowry', 'shane_lowry', 'pga', 2026, 2026, '14', 'Test Event', '2026-03-01', 1, 70)
        """
    )
    conn.commit()
    conn.close()

    with patch("scripts.restore_season_record.TRACK_RECORD", Path("/tmp/track.json")):
        with open("/tmp/track.json", "w", encoding="utf-8") as f:
            json.dump(track, f)
        stats = import_track_record(dry_run=False)

    assert stats["picks_imported"] == 1
    conn = db.get_conn()
    row = conn.execute(
        """
        SELECT po.profit, po.hit, po.outcome_locked, po.grading_authority
        FROM pick_outcomes po
        JOIN picks p ON p.id = po.pick_id
        """
    ).fetchone()
    conn.close()
    assert float(row["profit"]) == 1.03
    assert int(row["hit"]) == 1
    assert int(row["outcome_locked"]) == 1
    assert row["grading_authority"] == "trackRecord_json"
