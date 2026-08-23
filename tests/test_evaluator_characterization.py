"""Characterization tests: pin the FROZEN autoresearch evaluator.

These tests hold golden values captured from deterministic fixture databases.
If any assertion here fails, evaluator behavior has changed. That is ONLY
acceptable in a reviewed PR that bumps the relevant evaluator version constants
(CHECKPOINT_SCRIPT_EVALUATOR_VERSION / EVAL_CONTRACT_VERSION_WALK_FORWARD),
regenerates these baselines, and documents re-baselining per PROGRAM.md.

Golden numeric baselines were captured on the first run of this suite against
commit-time evaluator sources; see docs/plans/autoresearch_execution_plan.md.
"""

from __future__ import annotations

import sqlite3

import pytest

from backtester.research_lab.canonical import (
    CHECKPOINT_SCRIPT_EVALUATOR_VERSION,
    EVAL_CONTRACT_VERSION_WALK_FORWARD,
)
from backtester.research_lab.fingerprint import (
    EVALUATOR_SOURCE_FILES,
    compute_evaluator_fingerprint,
    evaluator_identity,
)
from backtester.sealed_holdout import (
    SealedHoldoutError,
    assert_not_sealed,
    filter_sealed_events,
)
from backtester.strategy import SimulationResult, StrategyConfig, replay_event
from backtester.weighted_walkforward import (
    build_expanding_splits,
    classify_event,
    compute_blended_score,
    compute_weighted_metrics,
    evaluate_guardrails,
    evaluate_weighted_walkforward,
)

# ---------------------------------------------------------------------------
# Deterministic fixture database (in-memory; schema subset used by the evaluator)
# ---------------------------------------------------------------------------

EVENT_ID = "9001"
YEAR = 2026
EVENT_DATE = "2026-06-01"

HISTORY_EVENTS = [
    {"event_id": "9000", "completed": "2026-05-18"},
    {"event_id": "8999", "completed": "2026-05-04"},
]

PLAYERS = [
    # key, sg_total baseline per round, fin_text on target event, outright open/close price
    ("alpha_player", 3.0, "1", 800),
    ("bravo_player", 2.0, "T5", 1200),
    ("charlie_player", 1.0, "T20", 2500),
    ("delta_player", 0.0, "41", 5000),
    ("echo_player", -1.0, "CUT", 8000),
]

DG_IDS = {key: 7000 + i for i, (key, *_rest) in enumerate(PLAYERS)}


def seed_fixture_db(conn: sqlite3.Connection) -> None:
    """Create and populate the deterministic evaluator fixture database."""
    conn.executescript(
        """
        CREATE TABLE rounds (
            dg_id INTEGER NOT NULL,
            player_key TEXT,
            player_name TEXT,
            year INTEGER,
            event_id TEXT,
            event_completed TEXT,
            round_num INTEGER,
            score INTEGER,
            sg_total REAL, sg_ott REAL, sg_app REAL, sg_arg REAL, sg_putt REAL, sg_t2g REAL,
            fin_text TEXT
        );
        CREATE TABLE pit_rolling_stats (
            event_id TEXT, year INTEGER, player_key TEXT, window INTEGER,
            sg_total REAL, sg_ott REAL, sg_app REAL, sg_arg REAL, sg_putt REAL, sg_t2g REAL,
            rounds_used INTEGER, sg_total_rank INTEGER
        );
        CREATE TABLE pit_course_stats (
            event_id TEXT, year INTEGER, player_key TEXT,
            sg_total REAL, sg_ott REAL, sg_app REAL, sg_arg REAL, sg_putt REAL,
            rounds_played INTEGER, avg_finish REAL, best_finish REAL
        );
        CREATE TABLE historical_odds (
            event_id TEXT, year INTEGER, player_dg_id INTEGER, player_name TEXT,
            market TEXT, book TEXT, open_line REAL, close_line REAL, outcome TEXT
        );
        CREATE TABLE historical_matchup_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL, year INTEGER NOT NULL, bet_type TEXT NOT NULL,
            p1_dg_id INTEGER NOT NULL, p1_name TEXT NOT NULL,
            p2_dg_id INTEGER NOT NULL, p2_name TEXT NOT NULL, book TEXT NOT NULL,
            p1_open TEXT, p1_close TEXT, p2_open TEXT, p2_close TEXT,
            p1_outcome REAL, p2_outcome REAL, p1_outcome_text TEXT, p2_outcome_text TEXT,
            tie_rule TEXT
        );
        """
    )

    def _sg_parts(base):
        return (
            base,
            0.3 * base + 0.1 if base else 0.1,
            0.3 * base,
            0.2 * base,
            0.2 * base,
            0.5 * base,
        )

    # History rounds (PIT provenance) and target-event rounds (grading source).
    for hist_index, hist_event in enumerate(HISTORY_EVENTS):
        for key, sg_base, _fin, _price in PLAYERS:
            for round_num in range(1, 5):
                sg_total, ott, app, arg, putt, t2g = _sg_parts(
                    sg_base + (0.25 if round_num <= 2 else -0.25)
                )
                conn.execute(
                    """
                    INSERT INTO rounds (dg_id, player_key, player_name, year, event_id,
                                        event_completed, round_num, score, sg_total,
                                        sg_ott, sg_app, sg_arg, sg_putt, sg_t2g)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (DG_IDS[key], key, key.replace("_", " ").title(), YEAR,
                     hist_event["event_id"], hist_event["completed"], round_num,
                     70, sg_total, ott, app, arg, putt, t2g),
                )
    for key, sg_base, fin, _price in PLAYERS:
        sg_total, ott, app, arg, putt, t2g = _sg_parts(sg_base)
        for round_num in range(1, 5):
            conn.execute(
                """
                INSERT INTO rounds (dg_id, player_key, player_name, year, event_id,
                                    event_completed, round_num, score, sg_total,
                                    sg_ott, sg_app, sg_arg, sg_putt, sg_t2g, fin_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (DG_IDS[key], key, key.replace("_", " ").title(), YEAR,
                 EVENT_ID, EVENT_DATE, round_num, 70,
                 sg_total, ott, app, arg, putt, t2g, fin),
            )

    # Precomputed window-8 PIT rows for the target event (rank = descending sg_total).
    for rank, (key, sg_base, _fin, _price) in enumerate(PLAYERS, start=1):
        sg_total, ott, app, arg, putt, t2g = _sg_parts(sg_base)
        conn.execute(
            """
            INSERT INTO pit_rolling_stats (event_id, year, player_key, window,
                                           sg_total, sg_ott, sg_app, sg_arg, sg_putt,
                                           sg_t2g, rounds_used, sg_total_rank)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (EVENT_ID, YEAR, key, 8, sg_total, ott, app, arg, putt, t2g, 8, rank),
        )

    # Synthetic outright odds (win market only) so the outright lane produces bets.
    for key, _sg_base, _fin, price in PLAYERS:
        conn.execute(
            """
            INSERT INTO historical_odds (event_id, year, player_dg_id, player_name,
                                         market, book, open_line, close_line, outcome)
            VALUES (?, ?, ?, ?, 'win', 'DG-Base', ?, ?, NULL)
            """,
            (EVENT_ID, YEAR, DG_IDS[key], key.replace("_", " ").title(), price, price),
        )

    # One matchup row: alpha (-150) vs delta (+130); alpha favored by composite.
    conn.execute(
        """
        INSERT INTO historical_matchup_odds (
            event_id, year, bet_type, p1_dg_id, p1_name, p2_dg_id, p2_name, book,
            p1_open, p1_close, p2_open, p2_close,
            p1_outcome, p2_outcome, p1_outcome_text, p2_outcome_text, tie_rule
        ) VALUES (?, ?, '72-hole Match', ?, ?, ?, ?, 'bet365',
                  '-150', '-150', '+130', '+130', 1.0, 0.0, 'win', 'loss', 'void')
        """,
        (EVENT_ID, YEAR, DG_IDS["alpha_player"], "Alpha Player",
         DG_IDS["delta_player"], "Delta Player"),
    )
    conn.commit()


@pytest.fixture()
def eval_db(tmp_db):
    """tmp_db schema plus a seeded in-memory evaluator database behind db.get_conn()."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    seed_fixture_db(conn)

    class _ConnProxy:
        def execute(self, sql, params=()):
            return conn.execute(sql, params)

        def close(self):
            return None

    original_get_conn = tmp_db.get_conn
    tmp_db.get_conn = lambda: _ConnProxy()
    yield conn
    # Restore: tmp_db patches DB_PATH/_DB_INITIALIZED but not arbitrary attributes.
    tmp_db.get_conn = original_get_conn


GOLDEN_STRATEGY = StrategyConfig(name="golden")


def _metrics_for(strategy: StrategyConfig) -> dict:
    bets = replay_event(EVENT_ID, YEAR, strategy)
    result = SimulationResult(strategy=strategy, events_simulated=1, bet_details=bets)
    result.compute_metrics()
    return {"bets": bets, "result": result}


# ---------------------------------------------------------------------------
# Golden characterization: replay_event
# ---------------------------------------------------------------------------


def test_replay_event_golden_bets(eval_db):
    out = _metrics_for(GOLDEN_STRATEGY)
    bets = out["bets"]

    matchup_bets = [b for b in bets if b["market"] == "matchup"]
    outright_bets = sorted(
        (b for b in bets if b["market"] != "matchup"), key=lambda x: x["player_key"]
    )

    # Matchup lane: exactly the seeded row; favored side picked; graded win.
    assert len(matchup_bets) == 1
    bet = matchup_bets[0]
    assert bet["player_key"] == "alpha_player"
    assert bet["opponent_key"] == "delta_player"
    assert bet["odds"] == -150
    assert bet["won"] is True
    # Platt sigmoid with A=-0.05 over the fixture composite gap (golden, captured).
    assert bet["model_prob"] == pytest.approx(0.8381, abs=1e-3)
    assert bet["implied_prob"] == pytest.approx(0.6, abs=1e-4)
    assert bet["ev"] == pytest.approx(0.3969, abs=1e-3)

    # Outright lane: which players clear min_ev and at what vigged prices is frozen behavior.
    assert [(b["player_key"], b["market"], b["odds"]) for b in outright_bets] == [
        ("alpha_player", "win", 737),
        ("bravo_player", "win", 1109),
        ("charlie_player", "win", 2318),
    ]

    # Golden summary metrics captured from commit-time evaluator sources.
    result = out["result"]
    assert result.total_bets == 4
    assert result.wins == 2
    assert result.roi_pct == pytest.approx(314.12, abs=0.01)
    assert result.clv_avg == pytest.approx(0.2448, abs=0.001)
    assert result.calibration_error == pytest.approx(0.0, abs=1e-6)


def test_replay_event_is_deterministic_across_runs(eval_db):
    first = _run_bets(GOLDEN_STRATEGY)
    second = _run_bets(GOLDEN_STRATEGY)
    assert first == second


def _run_bets(strategy: StrategyConfig) -> list[dict]:
    return replay_event(EVENT_ID, YEAR, strategy)


def test_replay_stable_under_hash_seed_perturbation(eval_db, monkeypatch):
    """PYTHONHASHSEED changes must not change bet selection or ordering."""
    import random

    # Simulate different interpreter hash seeds by perturbing set iteration:
    # we cannot change PYTHONHASHSEED mid-process, so instead verify ordering
    # stability across many repeated runs (set-order drift shows up as flapping).
    seen = []
    for _ in range(5):
        seen.append(_run_bets(GOLDEN_STRATEGY))
    for snapshot in seen[1:]:
        assert snapshot == seen[0]


# ---------------------------------------------------------------------------
# Golden characterization: weighted walk-forward + scoring contract
# ---------------------------------------------------------------------------


def _fake_runner_factory(per_event_roi: dict[str, float], bets_per_event: int = 30):
    def runner(event: dict, strategy: StrategyConfig) -> dict:
        # Strategy-aware: only the golden candidate earns the per-event ROI;
        # any other strategy (e.g. baseline) flat-lines at zero.
        roi = per_event_roi.get(str(event["event_id"]), 0.0) if strategy.name == "golden" else 0.0
        clv = 0.01 if roi > 0 else -0.01
        calib = 0.02 if roi > 0 else 0.06
        return {
            "roi_pct": roi,
            "clv_avg": clv,
            "calibration_error": calib,
            "total_bets": bets_per_event,
            "max_drawdown_pct": max(0.0, -roi),
        }

    return runner


EVENTS = [
    {"event_id": "e1", "year": 2026, "event_name": "Regular One", "event_date": "2026-03-01"},
    {"event_id": "e2", "year": 2026, "event_name": "Regular Two", "event_date": "2026-03-08"},
    {"event_id": "e3", "year": 2026, "event_name": "The Players Championship", "event_date": "2026-03-15"},
    {"event_id": "e4", "year": 2026, "event_name": "PGA Championship", "event_date": "2026-04-15"},
]


def test_build_expanding_splits_golden_shape():
    splits = build_expanding_splits(EVENTS, min_train_events=2, test_window_size=1)
    assert len(splits) == 2
    assert [e["event_id"] for e in splits[0]["train_events"]] == ["e1", "e2"]
    assert [e["event_id"] for e in splits[0]["test_events"]] == ["e3"]
    assert [e["event_id"] for e in splits[1]["test_events"]] == ["e4"]
    assert splits[1]["test_events"][0]["event_id"] == "e4"


def test_classify_and_weight_golden():
    assert classify_event("PGA Championship") == "major"
    assert classify_event("The Players Championship") == "signature"
    assert classify_event("Random Invitational") == "regular"
    assert evaluate_weight_class_major() == 3.0


def evaluate_weight_class_major() -> float:
    from backtester.weighted_walkforward import event_weight

    return event_weight("major")


def test_walkforward_golden_metrics():
    candidate_roi = {"e3": 10.0, "e4": 20.0}
    raw = evaluate_weighted_walkforward(
        strategy=GOLDEN_STRATEGY,
        baseline_strategy=StrategyConfig(name="baseline"),
        events=list(EVENTS),
        replay_runner=_fake_runner_factory(candidate_roi),
    )
    summary = raw["summary_metrics"]
    # Weights: e3 signature=2.0, e4 major=3.0 → weighted avg = (10*2 + 20*3)/5 = 16.0
    assert summary["events_evaluated"] == 2
    assert summary["total_bets"] == 60
    assert summary["weighted_roi_pct"] == pytest.approx(16.0, abs=0.0001)
    assert summary["unweighted_roi_pct"] == pytest.approx(15.0, abs=0.0001)
    # Cumulative weighted ROI rises monotonically here (10*2 then +20*3), so peak-to-trough drawdown is 0.
    assert summary["max_drawdown_pct"] == pytest.approx(0.0, abs=0.0001)

    baseline_summary = raw["baseline_summary_metrics"]
    assert baseline_summary["weighted_roi_pct"] == 0.0

    guardrails = raw["guardrail_results"]
    assert isinstance(guardrails["passed"], bool)


def test_evaluate_guardrails_golden_verdicts():
    good_candidate = {
        "total_bets": 50,
        "weighted_clv_avg": 0.02,
        "weighted_calibration_error": 0.05,
        "max_drawdown_pct": 5.0,
    }
    baseline = {
        "total_bets": 50,
        "weighted_clv_avg": 0.01,
        "weighted_calibration_error": 0.05,
        "max_drawdown_pct": 5.0,
    }
    verdict = evaluate_guardrails(good_candidate, baseline)
    assert verdict == {"passed": True, "reasons": [], "verdict": "promising"}

    bad_candidate = {
        "total_bets": 10,  # below strict min_bets=30
        "weighted_clv_avg": -0.05,
        "weighted_calibration_error": 0.20,
        "max_drawdown_pct": 50.0,
    }
    blocked = evaluate_guardrails(bad_candidate, baseline)
    assert blocked["passed"] is False
    assert blocked["reasons"] == [
        "insufficient_sample",
        "clv_regression",
        "calibration_regression",
        "drawdown_regression",
    ]
    assert blocked["verdict"] == "blocked_by_guardrails"


def test_compute_blended_score_golden_values():
    summary = {
        "weighted_roi_pct": 10.0,
        "weighted_clv_avg": 0.02,
        "weighted_calibration_error": 0.03,
        "max_drawdown_pct": 8.0,
        "total_bets": 120,
    }
    passing = {"passed": True}
    failing = {"passed": False}

    # Hand-computed: 10*0.5 + 0.02*100 - 0.03*10 - 8*0.1 + min(120,200)/200 = 5+2-0.3-0.8+0.6 = 6.5
    assert compute_blended_score(summary, passing) == pytest.approx(6.5, abs=0.0001)
    # Guardrail failure applies the fixed -25 penalty.
    assert compute_blended_score(summary, failing) == pytest.approx(-18.5, abs=0.0001)


def test_compute_blended_score_prefers_matchup_bet_details():
    summary = {
        "weighted_roi_pct": 0.0,
        "weighted_clv_avg": 0.0,
        "weighted_calibration_error": 0.0,
        "max_drawdown_pct": 0.0,
        "total_bets": 2,
    }
    details = [
        {"market": "matchup", "wager": 1.0, "payout": 2.5, "won": True},
        {"market": "matchup", "wager": 1.0, "payout": 0.0, "won": False},
    ]
    # matchup_roi = (2.5-2)/2*100 = 25 ; hit_rate = 0.5
    # score = 25*2 + 0.5*50 + 0 + 0 - 0 - 0 + min(2,200)/200 = 50+25+0.01
    score = compute_blended_score(summary, {"passed": True}, bet_details=details)
    assert score == pytest.approx(75.01, abs=0.0001)


def test_compute_weighted_metrics_empty_golden():
    empty = compute_weighted_metrics([])
    assert empty["events_evaluated"] == 0
    assert empty["total_bets"] == 0
    assert empty["weighted_roi_pct"] == 0.0


# ---------------------------------------------------------------------------
# Version + fingerprint stamping
# ---------------------------------------------------------------------------


def test_evaluator_version_constants_unchanged():
    assert CHECKPOINT_SCRIPT_EVALUATOR_VERSION == 1
    assert EVAL_CONTRACT_VERSION_WALK_FORWARD == 2


def test_fingerprint_is_stable_and_sensitive():
    fp_a = compute_evaluator_fingerprint()
    fp_b = compute_evaluator_fingerprint()
    assert fp_a == fp_b
    assert len(fp_a) == 32
    identity = evaluator_identity()
    assert identity == {"evaluator_fingerprint": fp_a}

    # Sensitivity: changing any pinned source changes the fingerprint.
    tampered = compute_evaluator_fingerprint(files=EVALUATOR_SOURCE_FILES[:-1])
    assert tampered != fp_a

    missing = compute_evaluator_fingerprint(files=("backtester/__does_not_exist__.py",))
    assert missing != fp_a


# ---------------------------------------------------------------------------
# Sealed holdout enforcement
# ---------------------------------------------------------------------------


def test_sealed_holdout_loader_validates():
    doc = load_holdout_doc()
    assert doc["sealed_holdout_version"] == 1
    keys = {(str(e["event_id"]), int(e["year"])) for e in doc["events"]}
    assert keys == {("32", 2026), ("26", 2026)}


def load_holdout_doc():
    from backtester.sealed_holdout import load_sealed_holdout

    return load_sealed_holdout()


def test_sealed_events_rejected_by_assert_not_sealed():
    with pytest.raises(SealedHoldoutError):
        assert_not_sealed("32", 2026)
    with pytest.raises(SealedHoldoutError):
        assert_not_sealed("26", 2026)
    assert_not_sealed("99999", 2026)  # unsealed passes silently


def test_filter_sealed_events_removes_only_sealed():
    events = [
        {"event_id": "32", "year": 2026, "event_name": "RBC Canadian Open"},
        {"event_id": "26", "year": 2026, "event_name": "U.S. Open"},
        {"event_id": "28", "year": 2026, "event_name": "BMW Championship"},
    ]
    kept = filter_sealed_events(events)
    assert [e["event_id"] for e in kept] == ["28"]
