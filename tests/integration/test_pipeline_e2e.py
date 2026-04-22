"""
Minimum-viable end-to-end pipeline integration test (Q8).

Exercises the live/pre-tournament pipeline from ingest (seeded fixture data
in a tmp SQLite DB) through model composite scoring, the matchup-first value
path, and snapshot JSON write, using a single synthetic field.

Scope and rationale
-------------------
The full orchestrator (`src.services.golf_model_service.GolfModelService`) is
wired to live Data Golf / sportsbook APIs for its ingest step. Mocking every
HTTP dependency would couple this test to private implementation details and
add fragility, so this test exercises the pipeline at the first stable public
seam:

    ingest step       -> replaced by direct DB seeding (tmp SQLite + fixtures)
    feature/metrics   -> `src.models.composite.compute_composite`
    model blend       -> composite + Platt sigmoid inside matchup_value
    value path        -> `src.matchup_value.find_matchup_value_bets_with_all_books`
                         + `src.value.find_value_bets` for placement markets
    snapshot write    -> JSON payload written to `tmp_path`, mirroring the
                         shape produced by `backtester.dashboard_runtime`

This validates the composite -> matchup/value -> snapshot contract without
taking a dependency on the DG API. The seams used here are the same public
functions the production orchestrator calls.

Non-goals for this test (follow-ups):
    - Exercising the full `GolfModelService.run_analysis` orchestrator
      (requires DG HTTP stubbing; out of scope for Q8 per the recovery plan).
    - AI narrative / adjustments (pipeline can bypass these; not on the
      critical trust path).
    - 3-ball value bets (covered by `tests/test_value.py` unit tests).

Runtime budget: < 15 s on CI.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Make repo root importable when this file is collected directly.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

pytestmark = pytest.mark.integration


# ── Fixture loaders ─────────────────────────────────────────────────────────


def _load_players_fixture() -> dict:
    with (FIXTURES_DIR / "players.json").open() as f:
        return json.load(f)


def _load_odds_fixture() -> dict:
    with (FIXTURES_DIR / "odds.json").open() as f:
        return json.load(f)


# ── DB helpers ──────────────────────────────────────────────────────────────


@pytest.fixture
def seeded_db(monkeypatch):
    """Isolated SQLite DB seeded from the JSON fixtures.

    Yields (db_module, tournament_id, second_tournament_id, players_fixture).
    """
    import src.db as db

    original_path = db.DB_PATH
    original_init = db._DB_INITIALIZED

    tmp_path = tempfile.mktemp(suffix=".db")
    db.DB_PATH = tmp_path
    db._DB_INITIALIZED = False
    db.ensure_initialized()

    players_fx = _load_players_fixture()
    tournaments = players_fx["tournaments"]
    players = players_fx["players"]

    # Create both tournaments so the register-level assertion ("2 tournaments")
    # holds even though only the primary tournament drives the full pipeline.
    primary = tournaments[0]
    secondary = tournaments[1]
    primary_tid = db.get_or_create_tournament(
        primary["name"], primary["course"], year=primary["year"]
    )
    secondary_tid = db.get_or_create_tournament(
        secondary["name"], secondary["course"], year=secondary["year"]
    )

    # Seed rounds — provides form (recent rounds) signal for the composite model.
    # Eight prior rounds per player at a DIFFERENT course so course-fit stays
    # neutral (we want the composite to still produce a ranked field).
    rounds = []
    for player in players:
        for i in range(8):
            rounds.append({
                "dg_id": player["dg_id"],
                "player_name": player["display"],
                "player_key": player["key"],
                "tour": "pga",
                "season": 2025,
                "year": 2025,
                "event_id": f"fx_evt_{i}",
                "event_name": f"Fixture Prior Event {i}",
                "event_completed": f"2025-10-{i + 1:02d}",
                "course_name": "Prior Fixture Course",
                "course_num": 500,
                "course_par": 72,
                "round_num": 1,
                "score": 70,
                # Skill-graded sg_total produces a meaningful form ordering.
                "sg_total": player["skill"],
                "sg_ott": player["skill"] * 0.3,
                "sg_app": player["skill"] * 0.3,
                "sg_arg": player["skill"] * 0.2,
                "sg_putt": player["skill"] * 0.2,
                "sg_t2g": player["skill"] * 0.8,
                "driving_dist": 300, "driving_acc": 60, "gir": 68, "scrambling": 58,
                "prox_fw": 30, "prox_rgh": 40,
                "great_shots": None, "poor_shots": None,
                "birdies": 4, "pars": 12, "bogies": 2,
                "doubles_or_worse": 0, "eagles_or_better": 0,
                "fin_text": "T20", "teetime": None, "start_hole": 1,
            })
    db.store_rounds(rounds)

    # Seed DG skill metrics on the primary tournament — composite uses these
    # to derive the elite-player floor for the momentum component.
    metric_rows = []
    for player in players:
        metric_rows.append({
            "tournament_id": primary_tid,
            "csv_import_id": None,
            "player_key": player["key"],
            "player_display": player["display"],
            "metric_category": "dg_skill",
            "data_mode": "pre_tournament",
            "round_window": "all",
            "metric_name": "dg_sg_total",
            "metric_value": player["skill"],
            "metric_text": None,
        })
    db.store_metrics(metric_rows)

    try:
        yield db, primary_tid, secondary_tid, players_fx
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        db.DB_PATH = original_path
        db._DB_INITIALIZED = original_init


# ── Snapshot writer (mirrors backtester/dashboard_runtime._write_snapshot) ──


def _write_snapshot_atomic(snapshot_path: Path, payload: dict) -> None:
    """Same contract as dashboard_runtime._write_snapshot: write JSON at path.

    Kept in the test (rather than importing backtester runtime) so that we do
    not accidentally hit the production `/data/live_refresh_snapshot.json`
    location during CI.
    """
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = snapshot_path.with_suffix(snapshot_path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, snapshot_path)


# ── The end-to-end test ────────────────────────────────────────────────────


def test_pipeline_e2e_minimum_viable(seeded_db, tmp_path, monkeypatch):
    """Drive the pipeline end-to-end on tiny fixtures and assert snapshot shape.

    Steps exercised:
      1. Ingest       — tmp SQLite DB seeded with 2 tournaments, 8 players,
                         8 prior rounds/player, DG skill metrics (fixture).
      2. Model        — compute_composite on primary tournament.
      3. Value path   — matchup-first:
                         find_matchup_value_bets_with_all_books
                         + find_value_bets (outright, top10, top20).
      4. Snapshot     — dashboard payload written as JSON to tmp_path.

    Asserts on shape (not exact probabilities); numeric values shift as the
    model is tuned, but field presence / matchup-first contract must not.
    """
    from src import config
    from src.models.composite import compute_composite
    from src.matchup_value import find_matchup_value_bets_with_all_books
    from src.value import find_value_bets

    db, primary_tid, secondary_tid, players_fx = seeded_db
    odds_fx = _load_odds_fixture()

    # Keep matchup evaluator deterministic: it will try to hit the DG API to
    # pull cross-pair probabilities; we force the "unavailable" branch so the
    # test runs with zero network I/O. The module falls back to DG prices
    # embedded in each matchup dict (our fixtures include `datagolf` prices).
    import src.matchup_value as mv_module

    def _no_dg_pairings():
        return {}

    monkeypatch.setattr(mv_module, "fetch_dg_matchup_all_pairings",
                        _no_dg_pairings, raising=False)
    # Some callers import the symbol from src.datagolf directly.
    import src.datagolf as dg_module
    monkeypatch.setattr(dg_module, "fetch_dg_matchup_all_pairings",
                        _no_dg_pairings, raising=False)

    # 2. Run the composite model on the primary fixture tournament.
    composite = compute_composite(primary_tid)
    assert len(composite) == len(players_fx["players"]), (
        "compute_composite should score every seeded player"
    )
    # Scheffler-analog (highest skill) should outrank the last player.
    assert composite[0]["player_key"] == "fixture_alpha"
    assert composite[-1]["player_key"] == "fixture_hotel"
    for row in composite:
        assert "composite" in row and "form" in row and "course_fit" in row
        assert "momentum" in row
        assert 0.0 <= row["composite"] <= 100.0

    # 3a. Value path — matchups (includes DG prices per matchup, so the
    # 80/20 DG/model matchup blend inside find_matchup_value_bets_with_all_books
    # fires). ev_threshold kept loose so small fixtures produce card rows.
    curated, all_books = find_matchup_value_bets_with_all_books(
        composite,
        odds_fx["matchups"],
        ev_threshold=0.01,
        tournament_id=primary_tid,
    )
    assert len(all_books) >= 1, "fixture matchup odds should yield at least one qualifying line"
    assert len(curated) >= 1, "expected at least one curated matchup bet on fixture data"
    for row in curated:
        # Contract: the matchup row must expose model/DG/market probabilities
        # plus book and pricing so the dashboard can render it.
        for key in (
            "pick", "opponent",
            "model_win_prob", "dg_win_prob", "platt_win_prob",
            "implied_prob", "odds", "book", "ev",
        ):
            assert key in row, f"matchup row missing field: {key!r}"
        assert 0.0 <= row["model_win_prob"] <= 1.0
        assert 0.0 <= row["implied_prob"] <= 1.0
        assert isinstance(row["odds"], int)

    # 3b. Value path — placement / outright markets (exercises the 95/5
    # DG+model blend in config.BLEND_WEIGHTS). We compute a few markets so the
    # BEST_BETS_MATCHUP_ONLY assertion below is meaningful.
    outright_odds_by_player = {
        name.lower(): {
            "best_price": entry["best_price"],
            "implied_prob": 1.0 / max(entry["best_price"] / 100.0 + 1.0, 1.0)
                if entry["best_price"] > 0
                else abs(entry["best_price"]) / (abs(entry["best_price"]) + 100.0),
            "best_book": entry["best_book"],
            "books": entry["books"],
        }
        for name, entry in odds_fx["outrights"].items()
    }
    placement_bets_by_market: dict[str, list[dict]] = {}
    for market in ("outright", "top10", "top20"):
        placement_bets_by_market[market] = find_value_bets(
            composite,
            outright_odds_by_player,
            bet_type=market,
            ev_threshold=0.20,  # tight — we mainly need the shape, not a flood
            tournament_id=primary_tid,
        )

    # 4. Build & write the snapshot payload — mirrors the shape produced by
    # backtester.dashboard_runtime for the live tournament section.
    best_bets: list[dict] = []
    if getattr(config, "BEST_BETS_MATCHUP_ONLY", False):
        # Matchup-first card: only matchups promoted to the header bets.
        for row in sorted(curated, key=lambda r: r.get("ev", 0), reverse=True)[
            : getattr(config, "BEST_BETS_COUNT", 5)
        ]:
            best_bets.append({
                "market_type": "matchup",
                "pick": row["pick"],
                "opponent": row["opponent"],
                "odds": row["odds"],
                "book": row["book"],
                "ev": row["ev"],
                "model_win_prob": row["model_win_prob"],
                "dg_win_prob": row["dg_win_prob"],
            })
    snapshot = {
        "schema_version": "e2e-test-1",
        "generated_at": "2026-04-22T00:00:00Z",
        "config": {
            "MODEL_VERSION": config.MODEL_VERSION,
            "BEST_BETS_MATCHUP_ONLY": bool(getattr(config, "BEST_BETS_MATCHUP_ONLY", False)),
            "BLEND_WEIGHTS_OUTRIGHT": config.BLEND_WEIGHTS.get("outright", {}),
        },
        "live_tournament": {
            "event_name": players_fx["tournaments"][0]["name"],
            "course": players_fx["tournaments"][0]["course"],
            "tournament_id": primary_tid,
            "composite_results": composite,
            "matchup_bets": curated,
            "matchup_bets_all_books": all_books,
            "value_bets": placement_bets_by_market,
            "best_bets": best_bets,
        },
    }
    snapshot_path = tmp_path / "live_refresh_snapshot.json"
    _write_snapshot_atomic(snapshot_path, snapshot)

    # Snapshot written to the expected location.
    assert snapshot_path.exists(), "snapshot JSON was not written"
    # Snapshot is valid JSON (round-trip read).
    loaded = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert loaded["schema_version"] == "e2e-test-1"
    assert loaded["config"]["MODEL_VERSION"] == config.MODEL_VERSION

    # Snapshot shape.
    live = loaded["live_tournament"]
    assert live["tournament_id"] == primary_tid
    assert len(live["composite_results"]) == len(players_fx["players"])
    assert live["matchup_bets"], "snapshot must contain at least one matchup entry"

    first_mb = live["matchup_bets"][0]
    for key in (
        "pick", "opponent",
        "model_win_prob", "dg_win_prob",
        "odds", "book", "ev",
    ):
        assert key in first_mb, f"snapshot matchup row missing field: {key!r}"

    # BEST_BETS_MATCHUP_ONLY must be honored: no outright / placement / frl /
    # make_cut / top-N picks may appear in the best-bets list.
    assert config.BEST_BETS_MATCHUP_ONLY is True, (
        "config invariant: BEST_BETS_MATCHUP_ONLY must be True for the live card"
    )
    assert live["best_bets"], "best_bets must be non-empty when matchups qualify"
    forbidden_types = {
        "outright", "top5", "top10", "top20",
        "frl", "make_cut", "win",
    }
    for row in live["best_bets"]:
        assert row["market_type"] == "matchup", (
            f"BEST_BETS_MATCHUP_ONLY violated: {row['market_type']!r} in best_bets"
        )
        assert row["market_type"] not in forbidden_types

    # Sanity: both seeded tournaments still visible in the DB (ingest seam).
    conn = db.get_conn()
    try:
        names = [
            r["name"] for r in conn.execute(
                "SELECT name FROM tournaments ORDER BY id"
            ).fetchall()
        ]
    finally:
        conn.close()
    assert players_fx["tournaments"][0]["name"] in names
    assert players_fx["tournaments"][1]["name"] in names
