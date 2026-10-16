"""Outcome-blind selection rules evaluated against reconciled historical decisions.

Pure, report-only code: no application/model/database imports, I/O, tuning or
promotion. All historical results remain retrospective, including the later
validation events; the history was already inspected during reconciliation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import date, datetime
import hashlib
import json
import math
import random
from typing import Any

PROTOCOL_ID = "frozen-model-selection-2026-10-14-v2"
MIN_TRAIN_EVENTS = 8
MIN_VALIDATION_EVENTS = 5
MIN_VALIDATION_DECISIONS = 30
BOOTSTRAP_REPLICATES = 1000
RULES = (
    ("baseline", "All eligible historical decisions"),
    ("positive_ev", "Stored EV greater than zero"),
    ("top_five_ev", "Positive EV; at most five highest-EV decisions per event"),
    ("one_quote_exposure_two", "Positive EV; one quote per contract; at most two exposures per player per event"),
)
EXPLICIT_MARKETS = frozenset({"72h", "18h", "group", "top5", "top10", "top20", "outright", "make_cut", "miss_cut"})
SETTLED = frozenset({"win", "loss", "zero_return"})


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _text(value: Any) -> str:
    return str(value or "").strip()


def _day(value: Any) -> date | None:
    text = _text(value)
    try:
        return date.fromisoformat(text) if len(text) == 10 else datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def _decimal_odds(value: Any) -> float | None:
    odds = _number(value)
    if odds is None or abs(odds) < 100:
        return None
    return 1 + (odds / 100 if odds > 0 else 100 / abs(odds))


def _round(row: Mapping) -> int | None:
    value = row.get("round", row.get("round_number"))
    number = _number(value)
    return int(number) if number in (1, 2, 3, 4) else None


def _participants(row: Mapping) -> tuple[str, ...]:
    if row.get("market") == "group":
        values = row.get("participants")
        if not isinstance(values, (list, tuple)):
            return ()
        return tuple(sorted({_text(v) for v in values if _text(v)}))
    return tuple(sorted({_text(row.get("player")), _text(row.get("opponent"))} - {""}))


def _signature(row: Mapping) -> str:
    # Source attachments do not distinguish an already canonical decision.
    fields = (
        "event_key", "event_name", "season", "event_start", "event_end", "market", "lane", "player", "opponent",
        "book", "odds", "probability", "ev", "model_variant", "model_config_hash", "recorded_at", "status",
        "settlement", "profit", "stake", "return_units", "issues", "chronology", "eligible_for_retrospective_selection",
        "round", "round_number", "group_id", "participants", "source_origin",
    )
    return json.dumps([row.get(k) for k in fields], sort_keys=True, default=str, separators=(",", ":"))


def _admit(row: Mapping, cutoff: date) -> tuple[dict | None, list[str]]:
    reasons = []
    if row.get("status") != "consistent":
        reasons.append("inconsistent_or_unresolved")
    if row.get("eligible_for_retrospective_selection") is not True:
        reasons.append("reconciliation_not_eligible")
    if not _text(row.get("event_key")) or not _text(row.get("player")):
        reasons.append("missing_event_or_selection")
    market = row.get("market")
    if market not in EXPLICIT_MARKETS:
        reasons.append("unspecified_market")
    participants = _participants(row)
    if market in {"72h", "18h"} and len(participants) != 2:
        reasons.append("missing_matchup_opponent")
    if market == "18h" and _round(row) is None:
        reasons.append("missing_round")
    if market == "group" and (not _text(row.get("group_id")) or len(participants) < 3 or _text(row.get("player")) not in participants):
        reasons.append("incomplete_group_contract")
    odds = _decimal_odds(row.get("odds"))
    if _text(row.get("book")).lower() in {"", "unknown", "unavailable", "n/a", "none", "null"} or odds is None:
        reasons.append("missing_or_invalid_quote")
    if row.get("settlement") not in SETTLED:
        reasons.append("not_settled")
    stake, profit = _number(row.get("stake")), _number(row.get("profit"))
    if stake is None or stake <= 0 or profit is None:
        reasons.append("invalid_stake_or_return")
    return_units = _number(row.get("return_units"))
    if return_units is not None and stake is not None and stake > 0 and profit is not None:
        if not math.isclose(return_units, profit / stake, rel_tol=1e-8, abs_tol=1e-8):
            reasons.append("conflicting_unit_return")
    if row.get("chronology") != "recorded_before_event":
        reasons.append("not_recorded_before_event")
    issues = row.get("issues") if isinstance(row.get("issues"), (list, tuple)) else []
    if row.get("chronology") == "restore_placeholder" or _text(row.get("source_origin")).lower() == "restore" or any("restore_placeholder" in _text(issue).lower() for issue in issues):
        reasons.append("restoration_placeholder")
    recorded, start, end = _day(row.get("recorded_at")), _day(row.get("event_start")), _day(row.get("event_end"))
    # Official calendar dates are not tee times. Reject same-day records rather
    # than invent a timezone or claim a pre-teeoff decision from ingest time.
    if recorded is None or start is None or end is None or end < start or recorded >= start:
        reasons.append("unverified_pre_event_date")
    if end is None or end >= cutoff:
        reasons.append("event_not_completed_before_cutoff")
    if reasons:
        return None, sorted(set(reasons))
    return {
        "decision_id": _text(row["decision_id"]), "event_key": _text(row["event_key"]),
        "event_start": start, "event_end": end, "market": market, "round": _round(row),
        "group_id": _text(row.get("group_id")), "participants": participants, "player": _text(row.get("player")),
        "book": _text(row.get("book")), "decimal_odds": odds, "ev": _number(row.get("ev")),
        "lane": _text(row.get("lane")) or "unknown",
        "model_variant": _text(row.get("model_variant")) or "unknown", "model_config_hash": _text(row.get("model_config_hash")),
        "settlement": row["settlement"], "stake": stake, "profit": profit, "return_units": profit / stake,
    }, []


def _contract(row: dict) -> tuple:
    # Direction and book are omitted intentionally: opposing sides and multiple
    # books belong to one contract for the one-quote rule.
    return (row["event_key"], row["market"], row["round"], row["group_id"], row["participants"])


def _select(rows: list[dict], rule: str) -> list[dict]:
    if rule == "baseline":
        return sorted(rows, key=lambda r: r["decision_id"])
    candidates = [row for row in rows if row["ev"] is not None and row["ev"] > 0]
    candidates.sort(key=lambda r: (r["event_key"], -r["ev"], -r["decimal_odds"], r["decision_id"]))
    if rule == "positive_ev":
        return candidates
    selected, event_count, exposure, contracts = [], Counter(), Counter(), set()
    for row in candidates:
        event = row["event_key"]
        if rule == "top_five_ev" and event_count[event] >= 5:
            continue
        if rule == "one_quote_exposure_two":
            contract = _contract(row)
            if contract in contracts or any(exposure[(event, player)] >= 2 for player in row["participants"]):
                continue
            contracts.add(contract)
            for player in row["participants"]:
                exposure[(event, player)] += 1
        selected.append(row)
        event_count[event] += 1
    return selected


def _metrics(rows: list[dict]) -> dict:
    returns = sum(row["return_units"] for row in rows)
    stake, profit = sum(row["stake"] for row in rows), sum(row["profit"] for row in rows)
    count = len(rows)
    variants = Counter(row["model_variant"] for row in rows)
    configs = Counter((row["model_variant"], row["model_config_hash"] or "unknown") for row in rows)
    identities = sorted(row["decision_id"] for row in rows)
    return {
        "decisions": count, "events": len({row["event_key"] for row in rows}),
        "settlements": dict(Counter(row["settlement"] for row in rows)),
        "unit_profit": round(returns, 8), "unit_stake": count,
        "unit_roi": round(returns / count, 8) if count else None,
        "recorded_profit": round(profit, 8), "recorded_stake": round(stake, 8),
        "recorded_roi": round(profit / stake, 8) if stake else None,
        "model_variants": dict(sorted(variants.items())),
        "model_config_strata": [{"variant": key[0], "config_hash": key[1], "decisions": n} for key, n in sorted(configs.items())],
        "missing_config_decisions": sum(not row["model_config_hash"] for row in rows),
        "selection_sha256": hashlib.sha256(json.dumps(identities, separators=(",", ":")).encode()).hexdigest(),
    }


def _quantile(values: list[float], p: float) -> float:
    values = sorted(values)
    position = (len(values) - 1) * p
    low = int(position)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def _bounds(selected: list[dict], baseline: list[dict], event_keys: list[str]) -> dict:
    # Resample whole events with the same draw for rule and baseline. Picks
    # within an event are never treated as independent bootstrap observations.
    by_rule, by_base = defaultdict(list), defaultdict(list)
    for row in selected:
        by_rule[row["event_key"]].append(row["return_units"])
    for row in baseline:
        by_base[row["event_key"]].append(row["return_units"])
    summaries = [(sum(by_rule[key]), len(by_rule[key]), sum(by_base[key]), len(by_base[key])) for key in event_keys]
    rng, rois, deltas = random.Random(20261014), [], []
    for _ in range(BOOTSTRAP_REPLICATES):
        draws = [summaries[rng.randrange(len(summaries))] for _ in summaries]
        selected_profit, selected_n, base_profit, base_n = map(sum, zip(*draws))
        if selected_n and base_n:
            roi = selected_profit / selected_n
            rois.append(roi)
            deltas.append(roi - base_profit / base_n)
    if not rois:
        return {"state": "insufficient_resamples", "unit_roi_95": None, "delta_vs_baseline_95": None}
    return {
        "state": "retrospective_event_bootstrap", "unit": "whole_event", "replicates": BOOTSTRAP_REPLICATES,
        "valid_replicates": len(rois), "event_count": len(event_keys),
        "unit_roi_95": [round(_quantile(rois, p), 8) for p in (0.025, 0.975)],
        "delta_vs_baseline_95": [round(_quantile(deltas, p), 8) for p in (0.025, 0.975)],
    }


def evaluate_selection(rows: Iterable[Mapping], cutoff: str = "2026-10-14") -> dict:
    """Compare a frozen protocol; never change, fit, save or promote a model/rule.

    ``return_units`` means net profit divided by source stake. Comparisons use
    one unit per selected historical decision; recorded-stake summaries are
    separate. The input is read without modification. Bad/conflicting records
    are counted and excluded rather than silently repaired.
    """
    cutoff_day = _day(cutoff)
    if cutoff_day is None:
        raise ValueError("cutoff must be an ISO date")
    grouped, exclusions, input_count = defaultdict(list), Counter(), 0
    for row in rows:
        input_count += 1
        if not isinstance(row, Mapping) or not _text(row.get("decision_id")):
            exclusions["missing_decision_id"] += 1
        else:
            grouped[_text(row["decision_id"])].append(row)
    eligible, duplicate_rows, excluded_rows, conflicting_ids = [], 0, exclusions["missing_decision_id"], 0
    for group in grouped.values():
        if len({_signature(row) for row in group}) != 1:
            exclusions["conflicting_decision_id"] += len(group)
            excluded_rows += len(group)
            conflicting_ids += 1
            continue
        duplicate_rows += len(group) - 1
        row, reasons = _admit(group[0], cutoff_day)
        if reasons:
            excluded_rows += 1
            exclusions.update(reasons)
        else:
            eligible.append(row)
    event_dates = defaultdict(set)
    for row in eligible:
        event_dates[row["event_key"]].add((row["event_start"], row["event_end"]))
    conflicting_events = {key for key, values in event_dates.items() if len(values) != 1}
    if conflicting_events:
        rejected = [row for row in eligible if row["event_key"] in conflicting_events]
        exclusions["conflicting_event_calendar"] += len(rejected)
        excluded_rows += len(rejected)
        eligible = [row for row in eligible if row["event_key"] not in conflicting_events]
    events = {row["event_key"]: (row["event_start"], row["event_end"]) for row in eligible}
    scopes = sorted({(row["lane"], row["market"], row["model_variant"]) for row in eligible})
    mixed_scope = len(scopes) > 1
    ordered = sorted(events, key=lambda key: (*events[key], key)) if not mixed_scope else []
    split_index = max(1, int(len(ordered) * 0.7))
    if len(ordered) >= MIN_TRAIN_EVENTS + MIN_VALIDATION_EVENTS:
        split_index = min(len(ordered) - MIN_VALIDATION_EVENTS, max(MIN_TRAIN_EVENTS, split_index))
    boundary = events[ordered[min(len(ordered) - 1, split_index)]][0] if len(ordered) >= 2 else None
    train_keys = [key for key in ordered if boundary is not None and events[key][1] < boundary]
    validation_keys = [key for key in ordered if boundary is not None and events[key][0] >= boundary]
    purged_keys = [key for key in ordered if key not in train_keys and key not in validation_keys] if boundary is not None else []
    train_set, validation_set = set(train_keys), set(validation_keys)
    training = [row for row in eligible if row["event_key"] in train_set]
    validation = [row for row in eligible if row["event_key"] in validation_set]
    sufficient_split = len(train_keys) >= MIN_TRAIN_EVENTS and len(validation_keys) >= MIN_VALIDATION_EVENTS
    comparisons = []
    for key, label in (() if mixed_scope else RULES):
        selected_all, selected_train, selected_validation = (_select(cohort, key) for cohort in (eligible, training, validation))
        validation_metrics = _metrics(selected_validation)
        adequate = sufficient_split and validation_metrics["events"] >= MIN_VALIDATION_EVENTS and len(selected_validation) >= MIN_VALIDATION_DECISIONS
        comparisons.append({
            "rule": key, "label": label, "all_history": _metrics(selected_all), "earlier_events": _metrics(selected_train),
            "later_events": validation_metrics,
            "comparison_state": "retrospective_only" if adequate else "insufficient_evidence",
            "bounds": _bounds(selected_validation, validation, validation_keys) if adequate else None,
            "promotion_allowed": False,
        })
    sufficient = any(row["comparison_state"] == "retrospective_only" for row in comparisons)
    return {
        "schema_version": 1, "state": "scope_required" if mixed_scope else "retrospective_evaluation" if sufficient else "insufficient_evidence",
        "cutoff": cutoff_day.isoformat(),
        "protocol": {
            "id": PROTOCOL_ID, "frozen_rules": True, "outcome_based_rule_search": False, "parameter_fitting": False,
            "model_changes": False, "report_only": True, "automatic_promotion": False,
            "required_scope": ["lane", "market", "model_variant"],
            "rules": [{"id": key, "label": label} for key, label in RULES],
            "ranking": "stored EV descending, decimal odds descending, decision ID ascending; no outcomes",
            "evaluation_stake": "One unit per selected decision; source stakes reported separately.",
            "minimum_earlier_events": MIN_TRAIN_EVENTS, "minimum_later_events": MIN_VALIDATION_EVENTS,
            "minimum_later_decisions_per_rule": MIN_VALIDATION_DECISIONS,
            "prospective_gate": "Freeze before unseen future events; no retrospective comparison can authorize promotion.",
        },
        "cohort": {
            "input_rows": input_count, "eligible_decisions": len(eligible), "eligible_events": len(events),
            "scopes": [{"lane": lane, "market": market, "model_variant": variant} for lane, market, variant in scopes],
            "duplicate_input_rows_removed": duplicate_rows, "excluded_input_rows": excluded_rows,
            "conflicting_decision_ids": conflicting_ids, "exclusion_reasons": dict(sorted(exclusions.items())),
            "markets": dict(sorted(Counter(row["market"] for row in eligible).items())),
            "missing_config_decisions": sum(not row["model_config_hash"] for row in eligible),
        },
        "split": {
            "kind": "chronological_whole_events_with_boundary_overlap_purged", "target_earlier_fraction": 0.7,
            "boundary": boundary.isoformat() if boundary else None,
            "earlier_events": train_keys, "later_events": validation_keys, "boundary_overlap_events": purged_keys,
            "untouched_holdout": False,
        },
        "comparisons": comparisons,
        "verdict": "Evaluate each lane, market and model variant separately; pooled selection comparisons are disabled." if mixed_scope else "Insufficient event-level evidence for a selection improvement claim." if not sufficient else "Retrospective comparisons only; no profitable or improved policy has been established prospectively.",
        "limitations": [
            "Stored selections are paper decisions; actual wager placement is unknown.",
            "Historical data was inspected; later events are retrospective validation, not an untouched holdout.",
            "Pre-event eligibility uses recorded calendar dates, not verified decision or bookmaker quote timestamps.",
            "Missing or conflicting records can bias the eligible subset; full-season coverage is reported separately.",
            "Variant/configuration strata describe archived outputs, not proof of performance for today's model.",
            "Baseline may contain multiple model decisions for the same wager; only the one-quote rule caps that exposure.",
            "Event bootstrap preserves within-event dependence; cross-event dependence and selection bias remain possible.",
            "Multiple fixed comparisons are descriptive; intervals are not multiplicity-adjusted significance tests.",
        ],
    }
