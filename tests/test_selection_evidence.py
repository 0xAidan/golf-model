"""Contract-level checks for the read-only frozen selection protocol."""
from copy import deepcopy
from datetime import date, timedelta
import json

import pytest

from src.selection_evidence import evaluate_selection


def row(number=1, **changes):
    value = {
        "decision_id": f"d{number}", "event_key": "event-1", "event_name": "Fixture event", "season": 2026,
        "event_start": "2026-02-05", "event_end": "2026-02-08", "market": "72h", "lane": "cockpit",
        "player": f"player-{number}", "opponent": f"opponent-{number}", "book": "Fixture book", "odds": "+110",
        "probability": 0.55, "ev": 0.155, "model_variant": "baseline", "model_config_hash": "fixed-config",
        "recorded_at": "2026-02-04 18:00:00", "status": "consistent", "settlement": "win", "profit": 1.1,
        "stake": 1.0, "return_units": 1.1, "issues": [], "chronology": "recorded_before_event",
        "eligible_for_retrospective_selection": True,
    }
    value.update(changes)
    return value


def rule(report, key):
    return next(item for item in report["comparisons"] if item["rule"] == key)


def season(events=20, decisions=10):
    result = []
    for event in range(events):
        start = date(2026, 2, 5) + timedelta(days=7 * event)
        for pick in range(decisions):
            won = (event + pick) % 3 != 0
            result.append(row(
                event * decisions + pick, event_key=f"event-{event:02}", event_start=start.isoformat(),
                event_end=(start + timedelta(days=3)).isoformat(), recorded_at=(start - timedelta(days=1)).isoformat(),
                profit=1.1 if won else -1, return_units=1.1 if won else -1, settlement="win" if won else "loss",
                ev=0.3 - 0.02 * pick,
            ))
    return result


def test_empty_history_is_explicit_insufficiency_not_zero_profit_claim():
    report = evaluate_selection([])
    assert report["state"] == "insufficient_evidence"
    assert report["cohort"]["eligible_decisions"] == 0
    assert rule(report, "baseline")["all_history"]["unit_roi"] is None
    assert all(item["bounds"] is None and not item["promotion_allowed"] for item in report["comparisons"])
    assert report["protocol"]["outcome_based_rule_search"] is False


def test_input_is_unchanged_and_report_is_json_serializable():
    original = [row(), row(2, market="18h", round=1)]
    before = deepcopy(original)
    report = evaluate_selection(iter(original))
    assert original == before
    json.dumps(report, allow_nan=False)
    assert report["cohort"]["eligible_decisions"] == 2
    assert report["split"]["untouched_holdout"] is False


@pytest.mark.parametrize("changes,reason", [
    ({"status": "conflict"}, "inconsistent_or_unresolved"),
    ({"eligible_for_retrospective_selection": False}, "reconciliation_not_eligible"),
    ({"market": "unspecified"}, "unspecified_market"),
    ({"market": "18h"}, "missing_round"),
    ({"opponent": ""}, "missing_matchup_opponent"),
    ({"book": ""}, "missing_or_invalid_quote"),
    ({"book": "unknown"}, "missing_or_invalid_quote"),
    ({"odds": "2.1"}, "missing_or_invalid_quote"),
    ({"settlement": "void"}, "not_settled"),
    ({"stake": 0}, "invalid_stake_or_return"),
    ({"profit": float("nan")}, "invalid_stake_or_return"),
    ({"return_units": 99}, "conflicting_unit_return"),
    ({"recorded_at": "2026-02-05T00:01:00Z"}, "unverified_pre_event_date"),
    ({"recorded_at": "not a date"}, "unverified_pre_event_date"),
    ({"chronology": "recorded_after_event"}, "not_recorded_before_event"),
    ({"chronology": "restore_placeholder"}, "restoration_placeholder"),
    ({"source_origin": "restore"}, "restoration_placeholder"),
    ({"issues": ["restore_placeholder_timestamp"]}, "restoration_placeholder"),
    ({"event_end": "2026-10-14"}, "event_not_completed_before_cutoff"),
])
def test_excludes_unreliable_or_future_evidence(changes, reason):
    report = evaluate_selection([row(**changes)])
    assert report["cohort"]["eligible_decisions"] == 0
    assert report["cohort"]["exclusion_reasons"][reason] == 1


def test_group_contract_requires_identity_and_all_participants_including_pick():
    records = [
        row(1, market="group"),
        row(2, market="group", group_id="a", participants=["other", "opponent-2", "third"]),
        row(3, market="group", group_id="a", participants=["player-3", "opponent-3", "third"]),
        row(4, market="18h", round_number=2),
    ]
    report = evaluate_selection(records)
    assert report["cohort"]["eligible_decisions"] == 2
    assert report["cohort"]["exclusion_reasons"]["incomplete_group_contract"] == 2


def test_identical_input_duplicates_collapse_conflicting_ids_are_fully_excluded():
    report = evaluate_selection([row(), row(), row(2), row(2, profit=-1, return_units=-1, settlement="loss")])
    assert report["cohort"]["input_rows"] == 4
    assert report["cohort"]["eligible_decisions"] == 1
    assert report["cohort"]["duplicate_input_rows_removed"] == 1
    assert report["cohort"]["conflicting_decision_ids"] == 1
    assert report["cohort"]["excluded_input_rows"] == 2


def test_conflicting_calendar_drops_entire_event():
    report = evaluate_selection([row(), row(2, event_end="2026-02-09")])
    assert report["cohort"]["eligible_decisions"] == 0
    assert report["cohort"]["exclusion_reasons"]["conflicting_event_calendar"] == 2


def test_rule_selection_does_not_change_when_outcomes_change():
    records = season()
    before = evaluate_selection(records)
    modified = deepcopy(records)
    for value in modified:
        value.update(settlement="loss", profit=-1, return_units=-1)
    after = evaluate_selection(modified)
    assert before["split"] == after["split"]
    for left, right in zip(before["comparisons"], after["comparisons"]):
        assert left["all_history"]["selection_sha256"] == right["all_history"]["selection_sha256"]
        assert left["later_events"]["selection_sha256"] == right["later_events"]["selection_sha256"]
        assert left["later_events"]["unit_roi"] != right["later_events"]["unit_roi"]


def test_fixed_rules_rank_ev_apply_event_cap_and_exclude_nonpositive_ev():
    records = [row(i, ev=(10 - i) / 100) for i in range(12)]
    report = evaluate_selection(records)
    assert rule(report, "baseline")["all_history"]["decisions"] == 12
    assert rule(report, "positive_ev")["all_history"]["decisions"] == 10
    assert rule(report, "top_five_ev")["all_history"]["decisions"] == 5
    expected = evaluate_selection(records[:5])
    assert rule(report, "top_five_ev")["all_history"]["selection_sha256"] == rule(expected, "baseline")["all_history"]["selection_sha256"]


def test_one_quote_rule_removes_opposing_sides_and_caps_player_exposure():
    records = [
        row(1, player="A", opponent="B", ev=0.5),
        row(2, player="B", opponent="A", book="Another book", ev=0.4),
        row(3, player="A", opponent="C", ev=0.3),
        row(4, player="A", opponent="D", ev=0.2),
    ]
    report = evaluate_selection(records)
    assert rule(report, "one_quote_exposure_two")["all_history"]["decisions"] == 2
    expected = evaluate_selection([records[0], records[2]])
    assert rule(report, "one_quote_exposure_two")["all_history"]["selection_sha256"] == rule(expected, "baseline")["all_history"]["selection_sha256"]


def test_rounds_and_groups_remain_distinct_contracts():
    records = [
        row(1, market="18h", round=1, player="A", opponent="B"),
        row(2, market="18h", round=2, player="A", opponent="B"),
    ]
    report = evaluate_selection(records)
    assert rule(report, "one_quote_exposure_two")["all_history"]["decisions"] == 2


def test_normalizes_evaluation_stake_without_modifying_original_stakes():
    report = evaluate_selection([row(1, profit=11, stake=10, return_units=1.1), row(2, profit=-1, return_units=-1, settlement="loss")])
    metrics = rule(report, "baseline")["all_history"]
    assert metrics["unit_profit"] == pytest.approx(0.1)
    assert metrics["unit_roi"] == pytest.approx(0.05)
    assert metrics["recorded_profit"] == 10
    assert metrics["recorded_stake"] == 11


def test_whole_event_split_and_bootstrap_never_claim_untouched_validation_or_promotion():
    report = evaluate_selection(season())
    assert report["state"] == "retrospective_evaluation"
    assert len(report["split"]["earlier_events"]) == 14
    assert len(report["split"]["later_events"]) == 6
    assert not set(report["split"]["earlier_events"]) & set(report["split"]["later_events"])
    baseline = rule(report, "baseline")
    assert baseline["later_events"]["decisions"] == 60
    assert baseline["bounds"]["unit"] == "whole_event"
    assert baseline["bounds"]["event_count"] == 6
    assert baseline["bounds"]["delta_vs_baseline_95"] == [0.0, 0.0]
    assert all(not value["promotion_allowed"] for value in report["comparisons"])
    assert report["protocol"]["parameter_fitting"] is False


def test_boundary_overlap_is_purged_not_used_as_past_training():
    records = season()
    for value in records:
        if value["event_key"] == "event-13":
            value["event_end"] = "2026-05-17"  # overlaps event 14 beginning May 14
    report = evaluate_selection(records)
    assert "event-13" in report["split"]["boundary_overlap_events"]
    assert "event-13" not in report["split"]["earlier_events"]


def test_tiny_later_sample_has_no_spurious_bounds():
    report = evaluate_selection(season(events=13, decisions=2))
    assert report["state"] == "insufficient_evidence"
    assert all(value["bounds"] is None for value in report["comparisons"])


def test_unknown_configuration_is_disclosed_not_invented():
    report = evaluate_selection([row(model_config_hash=None)])
    assert report["cohort"]["missing_config_decisions"] == 1
    assert rule(report, "baseline")["all_history"]["model_config_strata"] == [{"variant": "baseline", "config_hash": "unknown", "decisions": 1}]


def test_invalid_cutoff_fails_explicitly():
    with pytest.raises(ValueError, match="cutoff"):
        evaluate_selection([], cutoff="not a date")


def test_minimum_event_counts_are_reserved_without_changing_rules():
    report = evaluate_selection(season(events=13))
    assert len(report["split"]["earlier_events"]) == 8
    assert len(report["split"]["later_events"]) == 5
    assert rule(report, "baseline")["comparison_state"] == "retrospective_only"
    assert rule(report, "top_five_ev")["comparison_state"] == "insufficient_evidence"


@pytest.mark.parametrize("different", [
    {"lane": "lab_sandbox"}, {"market": "top10", "opponent": ""}, {"model_variant": "v5"},
])
def test_scope_gate_prevents_combining_lanes_markets_or_model_variants(different):
    records = [row(1), row(2, **different)]
    report = evaluate_selection(records)
    assert report["state"] == "scope_required"
    assert report["comparisons"] == []
    assert len(report["cohort"]["scopes"]) == 2
    assert report["split"]["earlier_events"] == []
    assert report["split"]["later_events"] == []
    assert report["protocol"]["required_scope"] == ["lane", "market", "model_variant"]


def test_ineligible_other_scope_does_not_change_admitted_comparison():
    report = evaluate_selection([row(1), row(2, lane="lab_sandbox", status="conflict")])
    assert report["state"] == "insufficient_evidence"
    assert rule(report, "baseline")["all_history"]["decisions"] == 1
