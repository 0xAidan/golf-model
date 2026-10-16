"""Tests for immutable, retrospective paper analytics and clustered uncertainty."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from src.performance_analytics import build_performance_report


def decision(number=1, **changes):
    row = {
        "decision_id": f"d{number}", "event_name": "Early Open", "event_start": "2026-02-05", "event_end": "2026-02-08",
        "market": "72h", "lane": "dashboard", "player_display": f"Player {number}", "opponent_display": "Opponent",
        "book": "FanDuel", "odds": "+110", "probability": "0.6", "ev": "0.1", "model_variant": "baseline",
        "model_config_hash": "original", "recorded_at": "2026-02-04 18:00:00", "recorded_times": "[]",
        "status": "consistent", "settlement": "win", "profit": "1.1", "stake": "1", "issues": "[]",
        "chronology": "recorded_before_event", "included_in_paper_record": "True",
        "eligible_for_retrospective_selection": "True", "observation_count": "2", "source_count": "2",
    }
    row.update(changes)
    return row


def season():
    return {"basis": "stored_paper_records", "as_of": "2026-10-14", "markets": [{"key": "72h"}, {"key": "18h"}],
            "events": [{"key": "early", "name": "Early Open", "starts_on": "2026-02-05", "ends_on": "2026-02-08"},
                       {"key": "late", "name": "Late Open", "starts_on": "2026-03-05", "ends_on": "2026-03-08"}],
            "provenance": {"report_id": "fixture-only"}, "selection": {"protocol_id": "fixture-protocol"}}


def report(rows, **kwargs):
    return build_performance_report(rows, season(), replicates=100, **kwargs)


def summary(value, cohort="pre_event", lane="dashboard", market="all"):
    return value["scopes"][f"{cohort}|{lane}|{market}"]["summary"]


def test_normalizes_stored_stake_not_headline_odds_and_keeps_sources_immutable():
    rows = [decision(1, profit="4", stake="2", odds="+999"), decision(2, settlement="loss", profit="-10", stake="10")]
    before, original_season = deepcopy(rows), season()
    original_season_before = deepcopy(original_season)
    result = build_performance_report(rows, original_season, replicates=20)
    assert rows == before
    assert original_season == original_season_before
    metrics = summary(result)
    assert metrics["unit_profit"] == 1  # +2u then -1u, not +4/-10.
    assert metrics["unit_stake"] == 2
    assert metrics["unit_roi_pct"] == 50
    assert metrics["recorded_profit"] == -6
    assert metrics["recorded_roi_pct"] == -50
    json.dumps(result, allow_nan=False)


def test_event_equity_sorts_calendar_not_input_or_grading_order_and_drawdown_is_event_boundary():
    result = report([
        decision(1, event_name="Late Open", event_start="2026-03-05", event_end="2026-03-08", recorded_at="2026-03-04", settlement="loss", profit="-1"),
        decision(2, profit="2"),
    ])
    scope = result["scopes"]["pre_event|dashboard|all"]
    assert [point["event_key"] for point in scope["series"]] == ["early", "late"]
    assert [point["cumulative_profit"] for point in scope["series"]] == [2, 1]
    assert [point["drawdown_units"] for point in scope["series"]] == [0, -1]
    assert scope["summary"]["max_drawdown_units"] == 1
    assert [point["month"] for point in scope["monthly"]] == ["2026-02", "2026-03"]


def test_exact_duplicates_collapse_and_all_conflicting_identity_versions_are_excluded():
    first = decision(1)
    result = report([first, deepcopy(first), decision(2), decision(2, profit="-1", settlement="loss")])
    assert summary(result)["decisions"] == 1
    assert result["coverage"]["duplicate_input_rows_removed"] == 1
    assert result["coverage"]["conflicting_decision_ids"] == 1
    assert result["coverage"]["exclusion_reasons"]["conflicting_decision_identity"] == 2


@pytest.mark.parametrize("change", [
    {"status": "conflict"}, {"status": "incomplete"}, {"settlement": "void"}, {"settlement": "ungraded"},
    {"stake": "0"}, {"stake": "-1"}, {"profit": "nan"}, {"stake": ""}, {"decision_id": ""},
    {"included_in_paper_record": "False"}, {"market": "unspecified"},
    {"event_end": "2026-10-14"}, {"event_start": "invalid"},
])
def test_unreconciled_unsettled_or_invalid_rows_do_not_enter_either_cohort(change):
    result = report([decision(**change)])
    assert summary(result)["decisions"] == 0
    assert summary(result, "paper")["decisions"] == 0


@pytest.mark.parametrize("change", [
    {"eligible_for_retrospective_selection": "False"},
    {"chronology": "recorded_during_event", "recorded_at": "2026-02-06"},
    {"chronology": "recorded_after_event", "recorded_at": "2026-02-09"},
    {"recorded_at": "2026-02-05T00:01:00Z"}, {"recorded_at": ""},
])
def test_pre_event_eligibility_requires_both_reconciliation_flag_and_strict_date(change):
    result = report([decision(**change)])
    assert summary(result)["decisions"] == 0
    assert summary(result, "paper")["decisions"] == 1
    assert result["default_cohort"] == "pre_event"
    assert result["methodology"]["untouched_holdout"] is False


def test_binary_scoring_is_proper_and_excludes_zero_return_and_missing_probabilities():
    result = report([
        decision(1, probability="0.8"),
        decision(2, probability="0.25", settlement="loss", profit="-1"),
        decision(3, probability="", settlement="loss", profit="-1"),
        decision(4, probability="0.9", settlement="zero_return", profit="0"),
    ])
    metrics = summary(result)
    assert metrics["decisions"] == 4
    assert metrics["binary_outcome_n"] == 3
    assert metrics["probability_n"] == 2
    assert metrics["probability_missing_n"] == 1
    assert metrics["probability_coverage_pct"] == pytest.approx(200 / 3)
    assert metrics["brier"] == pytest.approx((0.2 ** 2 + 0.25 ** 2) / 2)
    assert metrics["log_loss"] == pytest.approx((-math.log(0.8) - math.log(0.75)) / 2)
    bins = result["scopes"]["pre_event|dashboard|all"]["reliability"]
    assert sum(bucket["n"] for bucket in bins) == 2
    assert bins == [{"lower": 0.2, "upper": 0.3, "n": 1, "predicted": 0.25, "observed": 0},
                    {"lower": 0.8, "upper": 0.9, "n": 1, "predicted": 0.8, "observed": 1}]


def test_invalid_probability_is_missing_and_endpoint_logloss_is_finite_and_disclosed():
    result = report([decision(1, probability="1", settlement="loss", profit="-1"),
                     decision(2, probability="1.1"), decision(3, probability="nan"), decision(4, probability="0")])
    metrics = summary(result)
    assert metrics["probability_n"] == 2
    assert metrics["endpoint_probability_n"] == 2
    assert metrics["brier"] == 1
    assert math.isfinite(metrics["log_loss"])
    assert result["methodology"]["log_loss_epsilon"] > 0
    json.dumps(result, allow_nan=False)


def test_empty_scope_is_unavailable_not_zero_roi_clv_or_calibration_success():
    result = report([])
    metrics = summary(result)
    assert metrics["unit_roi_pct"] is None
    assert metrics["brier"] is None
    assert metrics["log_loss"] is None
    assert metrics["clv_bps"] is None
    assert metrics["closing_line_n"] == 0
    assert metrics["closing_line_coverage_pct"] is None
    assert result["scopes"]["pre_event|dashboard|all"]["interval"]["unit_roi_pct_95"] is None


def test_bootstrap_resamples_whole_events_reproducibly_and_is_not_pick_iid():
    # Every event contributes one +2 and one -1. Each cluster has exactly +50% ROI;
    # an incorrect pick-level bootstrap would produce a non-degenerate interval.
    rows = [decision(1, profit="2"), decision(2, profit="-1", settlement="loss"),
            decision(3, event_name="Late Open", event_start="2026-03-05", event_end="2026-03-08", recorded_at="2026-03-04", profit="2"),
            decision(4, event_name="Late Open", event_start="2026-03-05", event_end="2026-03-08", recorded_at="2026-03-04", profit="-1", settlement="loss")]
    first, second = report(rows), report(reversed(rows))
    interval = first["scopes"]["pre_event|dashboard|all"]["interval"]
    assert interval["unit_roi_pct_95"] == [50, 50]
    assert interval["events"] == 2
    assert interval["replicates"] == 100
    assert interval == second["scopes"]["pre_event|dashboard|all"]["interval"]
    assert first == second
    single = report(rows[:2])["scopes"]["pre_event|dashboard|all"]["interval"]
    assert single["state"] == "insufficient_events"
    assert single["unit_roi_pct_95"] is None


def test_model_book_lane_market_strata_reconcile_with_primary_scope():
    result = report([decision(1), decision(2, book="fanduel", model_variant="v5"),
                     decision(3, lane="lab", market="top20", book="DraftKings")])
    scope = result["scopes"]["pre_event|dashboard|72h"]
    assert scope["summary"]["decisions"] == 2
    assert [(item["key"], item["decisions"]) for item in scope["books"]] == [("fanduel", 2)]
    assert [(item["key"], item["decisions"]) for item in scope["models"]] == [("baseline", 1), ("v5", 1)]
    cells = [item for item in result["strata"] if item["cohort"] == "pre_event" and item["lane"] == "dashboard" and item["market"] == "72h"]
    assert sum(item["decisions"] for item in cells) == scope["summary"]["decisions"]
    assert sum(item["unit_profit"] for item in cells) == scope["summary"]["unit_profit"]
    assert sum(item["brier_sum"] for item in cells) / sum(item["probability_n"] for item in cells) == pytest.approx(scope["summary"]["brier"])


def test_conflicting_official_calendar_is_rejected():
    result = report([decision(event_end="2026-02-09")])
    assert summary(result)["decisions"] == 0
    assert result["coverage"]["exclusion_reasons"]["conflicting_event_calendar"] == 1


def test_invalid_season_basis_or_cutoff_fails_explicitly():
    for changed in ({"as_of": "bad"}, {"basis": "live_bets"}):
        with pytest.raises(ValueError):
            build_performance_report([], {**season(), **changed})


def test_cli_generates_hash_verified_report_without_mutating_sources(tmp_path):
    import csv
    root = Path(__file__).resolve().parents[1]
    decisions_path, season_path, output = tmp_path / "decisions.csv", tmp_path / "season.json", tmp_path / "performance.json"
    with decisions_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(decision()))
        writer.writeheader()
        writer.writerow(decision())
    season_path.write_text(json.dumps(season()))
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (decisions_path, season_path)}
    result = subprocess.run([sys.executable, str(root / "scripts/build_performance_analytics.py"), "--decisions", str(decisions_path),
                             "--season", str(season_path), "--output", str(output), "--replicates", "20"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    generated = json.loads(output.read_text())
    assert generated["provenance"]["source_hashes"] == hashes
    assert {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (decisions_path, season_path)} == hashes
    assert summary(generated)["decisions"] == 1
