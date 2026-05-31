#!/usr/bin/env python3
"""Build committed anonymized SQLite fixture for CI regression tests."""

from __future__ import annotations

import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FIXTURE_PATH = os.path.join(ROOT, "tests", "fixtures", "golf_2026_one_event.db")


def main() -> int:
    import src.db as db

    if os.path.exists(FIXTURE_PATH):
        os.unlink(FIXTURE_PATH)

    db.DB_PATH = FIXTURE_PATH
    db._DB_INITIALIZED = False
    db.ensure_initialized()

    tid = db.get_or_create_tournament(
        "Fixture Invitational",
        course="Fixture Country Club",
        year=2026,
        date="2026-03-01",
    )

    players = [
        ("player_alpha", "Player Alpha", 1.2),
        ("player_beta", "Player Beta", 0.4),
        ("player_gamma", "Player Gamma", -0.3),
    ]
    rounds = []
    for key, display, skill in players:
        for i in range(6):
            rounds.append({
                "dg_id": 1000 + hash(key) % 100,
                "player_name": display,
                "player_key": key,
                "tour": "pga",
                "season": 2025,
                "year": 2025,
                "event_id": f"fx_prior_{i}",
                "event_name": f"Prior Event {i}",
                "event_completed": f"2025-11-{i + 1:02d}",
                "course_name": "Prior Course",
                "course_num": 900,
                "course_par": 72,
                "round_num": 1,
                "score": 70,
                "sg_total": skill,
                "sg_ott": skill * 0.3,
                "sg_app": skill * 0.3,
                "sg_arg": skill * 0.2,
                "sg_putt": skill * 0.2,
                "sg_t2g": skill * 0.8,
                "driving_dist": 300,
                "driving_acc": 60,
                "gir": 65,
                "scrambling": 55,
                "prox_fw": 30,
                "prox_rgh": 40,
                "great_shots": None,
                "poor_shots": None,
                "birdies": 4,
                "pars": 12,
                "bogies": 2,
                "doubles_or_worse": 0,
                "eagles_or_better": 0,
                "fin_text": "T10",
                "teetime": None,
                "start_hole": 1,
            })
        db.store_metrics([
            {
                "tournament_id": tid,
                "csv_import_id": None,
                "player_key": key,
                "player_display": display,
                "metric_category": "dg_skill",
                "data_mode": "pre_tournament",
                "round_window": "all",
                "metric_name": "dg_sg_total",
                "metric_value": skill,
                "metric_text": None,
            }
        ])

    db.store_rounds(rounds)

    pick_rows = [
        {
            "tournament_id": tid,
            "model_variant": "baseline",
            "source": "cockpit",
            "bet_type": "matchup",
            "player_key": "player_alpha",
            "player_display": "Player Alpha",
            "opponent_key": "player_beta",
            "opponent_display": "Player Beta",
            "composite_score": 1.0,
            "course_fit_score": 0.5,
            "form_score": 0.5,
            "momentum_score": 0.0,
            "model_prob": 0.58,
            "market_odds": "-110",
            "market_book": "draftkings",
            "market_implied_prob": 0.52,
            "ev": 0.06,
            "confidence": "medium",
            "reasoning": "fixture",
        }
    ]
    db.store_picks(pick_rows)

    db.log_predictions([
        {
            "tournament_id": tid,
            "player_key": "player_alpha|player_beta",
            "bet_type": "matchup",
            "model_prob": 0.58,
            "dg_prob": None,
            "market_implied_prob": 0.52,
            "actual_outcome": None,
            "odds_decimal": 1.91,
            "profit": None,
            "odds_timing": "pre_tournament",
        }
    ])

    meta = {
        "tournament_id": tid,
        "tournament_name": "Fixture Invitational",
        "year": 2026,
        "pick_fingerprint": "fixture-v1",
    }
    sidecar = FIXTURE_PATH + ".json"
    with open(sidecar, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"Wrote {FIXTURE_PATH} ({os.path.getsize(FIXTURE_PATH)} bytes)")
    print(f"Wrote {sidecar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
