"""Verification script tests against restored trackRecord picks."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from src import db
from scripts.restore_season_record import import_track_record
from scripts.verify_season_record import verify


def test_verify_passes_after_trackrecord_import(tmp_db):
    track = {
        "headline": {"wins": 1, "losses": 0, "pushes": 0, "profit_units": 1.03, "units_staked": 1},
        "events": [
            {
                "name": "Verify Event",
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
        ],
    }
    baseline = Path("/tmp/verify_track.json")
    with open(baseline, "w", encoding="utf-8") as f:
        json.dump(track, f)

    conn = db.get_conn()
    conn.execute(
        """
        INSERT INTO rounds (dg_id, player_name, player_key, tour, season, year, event_id, event_name, event_completed, round_num, score)
        VALUES (1, 'Shane Lowry', 'shane_lowry', 'pga', 2026, 2026, '14', 'Verify Event', '2026-03-01', 1, 70)
        """
    )
    conn.commit()
    conn.close()

    with patch("scripts.restore_season_record.TRACK_RECORD", baseline):
        import_track_record(dry_run=False)

    report = verify(baseline)
    assert report["ok"] is True
    assert report["picks_checked"] == 1
