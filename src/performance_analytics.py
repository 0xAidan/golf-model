"""Pure, retrospective analytics over the preserved reconciled decision export.

No database, model or runtime imports. A 1u series normalizes each stored profit
by its stored positive stake; it does not reconstruct payouts from headline odds.
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

SCHEMA_VERSION = 1
BOOTSTRAP_REPLICATES = 1000
BOOTSTRAP_SEED = 20261015
LOG_LOSS_EPSILON = 1e-15
SETTLED = frozenset({"win", "loss", "zero_return"})
EXPLICIT_MARKETS = frozenset({"72h", "18h", "group", "top5", "top10", "top20", "outright", "make_cut", "miss_cut"})


def _text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _true(value: Any) -> bool:
    return value is True or isinstance(value, str) and value.strip().lower() == "true"


def _day(value: Any) -> date | None:
    text = _text(value)
    try:
        return date.fromisoformat(text) if len(text) == 10 else datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return None


def _rounded(value: float | None) -> float | None:
    return round(value, 8) if value is not None else None


def _book(value: Any) -> str:
    # Case/whitespace aliases do not constitute distinct bookmakers.
    return "".join(_text(value).lower().split()) or "unknown"


def _signature(row: Mapping) -> str:
    # Attachment counts and repeated source times are not decision identity.
    fields = ("event_name", "event_start", "event_end", "market", "lane", "player_display", "opponent_display",
              "book", "odds", "probability", "ev", "model_variant", "model_config_hash", "recorded_at", "status",
              "settlement", "profit", "stake", "issues", "chronology", "included_in_paper_record",
              "eligible_for_retrospective_selection")
    return json.dumps([row.get(key) for key in fields], sort_keys=True, default=str, separators=(",", ":"))


def _canonical_rows(rows: Iterable[Mapping], cutoff: date, season: Mapping) -> tuple[list[dict], dict]:
    grouped: dict[str, dict[str, Mapping]] = defaultdict(dict)
    counts = Counter(input_rows=0, duplicate_input_rows_removed=0, missing_decision_id=0)
    for row in rows:
        counts["input_rows"] += 1
        identity = _text(row.get("decision_id"))
        if not identity:
            counts["missing_decision_id"] += 1
            continue
        signature = _signature(row)
        if signature in grouped[identity]:
            counts["duplicate_input_rows_removed"] += 1
        grouped[identity][signature] = row

    calendar = {(event.get("name"), event.get("starts_on")): event for event in season.get("events", [])}
    excluded, admitted = Counter(), []
    for identity, versions in sorted(grouped.items()):
        if len(versions) != 1:
            counts["conflicting_decision_ids"] += 1
            excluded["conflicting_decision_identity"] += len(versions)
            continue
        row = next(iter(versions.values()))
        reasons = []
        if row.get("status") != "consistent":
            reasons.append("conflict_or_incomplete")
        if not _true(row.get("included_in_paper_record")):
            reasons.append("not_in_reconciled_paper_record")
        if row.get("market") not in EXPLICIT_MARKETS:
            reasons.append("unspecified_market")
        if row.get("settlement") not in SETTLED:
            reasons.append("void_or_unsettled")
        stake, profit = _number(row.get("stake")), _number(row.get("profit"))
        if stake is None or stake <= 0 or profit is None:
            reasons.append("invalid_stake_or_profit")
        start, end = _day(row.get("event_start")), _day(row.get("event_end"))
        if start is None or end is None or end < start or not _text(row.get("event_name")):
            reasons.append("invalid_event_calendar")
        if end is None or end >= cutoff:
            reasons.append("event_not_completed_before_cutoff")
        if reasons:
            excluded.update(reasons)
            continue
        event = calendar.get((row.get("event_name"), start.isoformat()), {})
        # A contradictory official calendar is excluded, not silently relabelled.
        if event.get("ends_on") and event["ends_on"] != end.isoformat():
            excluded["conflicting_event_calendar"] += 1
            continue
        event_key = _text(event.get("key")) or f"{start.isoformat()}|{_text(row.get('event_name'))}"
        recorded = _day(row.get("recorded_at"))
        eligible = (_true(row.get("eligible_for_retrospective_selection"))
                    and row.get("chronology") == "recorded_before_event"
                    and recorded is not None and recorded < start)
        probability = _number(row.get("probability"))
        if probability is None or not 0 <= probability <= 1:
            probability = None
        binary = row["settlement"] in {"win", "loss"}
        outcome = int(row["settlement"] == "win") if binary else None
        brier = (probability - outcome) ** 2 if probability is not None and binary else None
        clipped = min(1 - LOG_LOSS_EPSILON, max(LOG_LOSS_EPSILON, probability)) if probability is not None else None
        log_loss = -(outcome * math.log(clipped) + (1 - outcome) * math.log1p(-clipped)) if clipped is not None and binary else None
        admitted.append({
            "decision_id": identity, "event_key": event_key, "event_name": _text(row["event_name"]),
            "event_start": start.isoformat(), "event_end": end.isoformat(), "market": row["market"],
            "lane": _text(row.get("lane")) or "unknown", "model": _text(row.get("model_variant")) or "unknown",
            "config": _text(row.get("model_config_hash")), "book": _book(row.get("book")),
            "settlement": row["settlement"], "stake": stake, "profit": profit, "return_units": profit / stake,
            "pre_event": eligible, "probability": probability, "outcome": outcome,
            "brier": brier, "log_loss": log_loss,
        })
    # Same named event with contradictory dates must not become two independent clusters.
    dates: dict[str, set] = defaultdict(set)
    for row in admitted:
        dates[row["event_key"]].add((row["event_start"], row["event_end"]))
    bad_events = {key for key, values in dates.items() if len(values) > 1}
    if bad_events:
        excluded["conflicting_event_calendar"] += sum(row["event_key"] in bad_events for row in admitted)
        admitted = [row for row in admitted if row["event_key"] not in bad_events]
    counts.update(paper_decisions=len(admitted), pre_event_decisions=sum(row["pre_event"] for row in admitted))
    return admitted, {**dict(counts), "exclusion_reasons": dict(sorted(excluded.items()))}


def _summary(rows: list[dict]) -> dict:
    count = len(rows)
    settlements = Counter(row["settlement"] for row in rows)
    binary_n = settlements["win"] + settlements["loss"]
    valid = [row for row in rows if row["brier"] is not None]
    profit = math.fsum(row["return_units"] for row in rows)
    recorded_stake = math.fsum(row["stake"] for row in rows)
    recorded_profit = math.fsum(row["profit"] for row in rows)
    return {
        "decisions": count, "events": len({row["event_key"] for row in rows}),
        "wins": settlements["win"], "losses": settlements["loss"], "zero_return": settlements["zero_return"],
        "unit_profit": _rounded(profit), "unit_stake": count, "unit_roi_pct": _rounded(100 * profit / count) if count else None,
        "recorded_profit": _rounded(recorded_profit), "recorded_stake": _rounded(recorded_stake),
        "recorded_roi_pct": _rounded(100 * recorded_profit / recorded_stake) if recorded_stake else None,
        "win_rate_pct": _rounded(100 * settlements["win"] / binary_n) if binary_n else None,
        "binary_outcome_n": binary_n, "probability_n": len(valid), "probability_missing_n": binary_n - len(valid),
        "probability_coverage_pct": _rounded(100 * len(valid) / binary_n) if binary_n else None,
        "brier": _rounded(math.fsum(row["brier"] for row in valid) / len(valid)) if valid else None,
        "log_loss": _rounded(math.fsum(row["log_loss"] for row in valid) / len(valid)) if valid else None,
        "endpoint_probability_n": sum(row["probability"] in {0, 1} for row in valid),
        "missing_config_n": sum(not row["config"] for row in rows),
        "clv_bps": None, "closing_line_n": 0, "closing_line_coverage_pct": 0.0 if count else None,
    }


def _series(rows: list[dict]) -> tuple[list[dict], list[dict], float]:
    events: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        events[row["event_key"]].append(row)
    ordered = sorted(events.values(), key=lambda group: (group[0]["event_end"], group[0]["event_start"], group[0]["event_key"]))
    cumulative, peak, worst, series = 0.0, 0.0, 0.0, []
    for group in ordered:
        summary = _summary(group)
        cumulative += math.fsum(row["return_units"] for row in group)
        peak = max(peak, cumulative)
        drawdown = cumulative - peak
        worst = min(worst, drawdown)
        first = group[0]
        series.append({**{key: first[key] for key in ("event_key", "event_name", "event_start", "event_end")},
                       **{key: summary[key] for key in ("decisions", "unit_profit", "unit_roi_pct", "brier", "probability_n")},
                       "cumulative_profit": _rounded(cumulative), "drawdown_units": _rounded(drawdown)})
    months: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        months[row["event_end"][:7]].append(row)
    monthly = [{"month": key, **_summary(group)} for key, group in sorted(months.items())]
    return series, monthly, abs(worst)


def _reliability(rows: list[dict]) -> list[dict]:
    buckets: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        if row["brier"] is not None:
            buckets[min(9, int(row["probability"] * 10))].append(row)
    return [{"lower": index / 10, "upper": (index + 1) / 10, "n": len(group),
             "predicted": _rounded(math.fsum(row["probability"] for row in group) / len(group)),
             "observed": _rounded(math.fsum(row["outcome"] for row in group) / len(group))}
            for index, group in sorted(buckets.items())]


def _quantile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _interval(rows: list[dict], key: str, replicates: int) -> dict:
    events: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        events[row["event_key"]].append(row)
    result = {"method": "event_cluster_percentile_bootstrap", "confidence": 0.95, "events": len(events),
              "replicates": 0, "unit_roi_pct_95": None, "brier_95": None, "state": "insufficient_events"}
    if len(events) < 2 or replicates < 1:
        return result
    stats = [(math.fsum(row["return_units"] for row in group), len(group),
              math.fsum(row["brier"] for row in group if row["brier"] is not None),
              sum(row["brier"] is not None for row in group)) for _, group in sorted(events.items())]
    seed = BOOTSTRAP_SEED + int(hashlib.sha256(key.encode()).hexdigest()[:12], 16)
    rng, rois, briers = random.Random(seed), [], []
    for _ in range(replicates):
        selected = [stats[rng.randrange(len(stats))] for _ in stats]
        profit, count, error, probability_n = map(math.fsum, zip(*selected))
        rois.append(100 * profit / count)
        if probability_n:
            briers.append(error / probability_n)
    result.update(replicates=replicates, state="descriptive_interval", unit_roi_pct_95=[_rounded(_quantile(rois, p)) for p in (0.025, 0.975)],
                  brier_95=[_rounded(_quantile(briers, p)) for p in (0.025, 0.975)] if briers else None)
    return result


def _breakdown(rows: list[dict], dimension: str) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row[dimension]].append(row)
    return [{"key": key, **_summary(group)} for key, group in sorted(grouped.items())]


def _scope(rows: list[dict], key: str, replicates: int) -> dict:
    series, monthly, drawdown = _series(rows)
    return {"summary": {**_summary(rows), "max_drawdown_units": _rounded(drawdown)},
            "interval": _interval(rows, key, replicates), "series": series, "monthly": monthly,
            "reliability": _reliability(rows), "models": _breakdown(rows, "model"), "books": _breakdown(rows, "book")}


def build_performance_report(rows: Iterable[Mapping], season: Mapping, *, source_hashes: Mapping | None = None,
                             replicates: int = BOOTSTRAP_REPLICATES) -> dict:
    """Build aggregate scopes without altering any input or historical source.

    Scope keys are ``cohort|lane|market`` with ``all`` wildcards. Strata retain
    additive event/model/book sufficient statistics for further exact filtering.
    All percentages are 0..100 units; probabilities and Brier are 0..1 units.
    """
    cutoff = _day(season.get("as_of"))
    if cutoff is None:
        raise ValueError("The preserved season report needs a valid as_of date")
    if season.get("basis") != "stored_paper_records":
        raise ValueError("Expected preserved stored_paper_records basis")
    admitted, coverage = _canonical_rows(rows, cutoff, season)
    reported_markets = [item["key"] for item in season.get("markets", []) if item.get("key") in EXPLICIT_MARKETS]
    markets = sorted(set(reported_markets) | {row["market"] for row in admitted})
    lanes = sorted({"dashboard", "lab"} | {row["lane"] for row in admitted})
    scopes, strata = {}, []
    for cohort in ("pre_event", "paper"):
        cohort_rows = [row for row in admitted if cohort == "paper" or row["pre_event"]]
        for lane in ["all", *lanes]:
            for market in ["all", *markets]:
                selected = [row for row in cohort_rows if (lane == "all" or row["lane"] == lane) and (market == "all" or row["market"] == market)]
                key = f"{cohort}|{lane}|{market}"
                scopes[key] = _scope(selected, key, replicates)
        grouped: dict[tuple, list[dict]] = defaultdict(list)
        for row in cohort_rows:
            grouped[tuple(row[field] for field in ("event_key", "market", "lane", "model", "book"))].append(row)
        for (event_key, market, lane, model, book), group in sorted(grouped.items()):
            valid = [row for row in group if row["brier"] is not None]
            strata.append({"cohort": cohort, "event_key": event_key, "event_name": group[0]["event_name"],
                           "event_start": group[0]["event_start"], "event_end": group[0]["event_end"],
                           "market": market, "lane": lane, "model": model, "book": book,
                           "decisions": len(group), "unit_profit": _rounded(math.fsum(row["return_units"] for row in group)),
                           "wins": sum(row["settlement"] == "win" for row in group),
                           "losses": sum(row["settlement"] == "loss" for row in group),
                           "zero_return": sum(row["settlement"] == "zero_return" for row in group),
                           "probability_n": len(valid), "brier_sum": _rounded(math.fsum(row["brier"] for row in valid)),
                           "log_loss_sum": _rounded(math.fsum(row["log_loss"] for row in valid))})
    return {
        "schema_version": SCHEMA_VERSION, "as_of": cutoff.isoformat(), "basis": "stored_paper_records", "default_cohort": "pre_event",
        "dimensions": {"markets": markets, "lanes": lanes, "models": sorted({row["model"] for row in admitted}),
                       "books": sorted({row["book"] for row in admitted})},
        "cohorts": {
            "pre_event": {"label": "Before the event", "decisions": coverage["pre_event_decisions"],
                          "description": "Reconciliation-eligible decisions recorded on an earlier calendar day than the event start."},
            "paper": {"label": "Inclusive paper record", "decisions": coverage["paper_decisions"],
                      "description": "Consistent settled paper decisions, including those recorded during or after an event; descriptive only."},
        },
        "coverage": coverage, "scopes": scopes, "strata": strata,
        "methodology": {"untouched_holdout": False, "retrospective": True, "normalization": "stored_profit_divided_by_positive_stored_stake",
                        "equity_order": "event_end_then_event_start_then_event_key", "drawdown_basis": "event_boundary",
                        "monthly_basis": "event_end_calendar_month", "binary_outcomes": ["win", "loss"],
                        "probability_bins": "ten_equal_width_bins_final_bin_includes_one", "log_loss_epsilon": LOG_LOSS_EPSILON,
                        "bootstrap_unit": "whole_event", "bootstrap_seed": BOOTSTRAP_SEED,
                        "clv_state": "closing_quotes_not_in_preserved_export"},
        "provenance": {"source_hashes": dict(source_hashes or {}), "season_provenance": dict(season.get("provenance", {})),
                       "selection_protocol_id": season.get("selection", {}).get("protocol_id")},
        "caveats": [
            "Retrospective model selections, not verified placed bets, an untouched holdout, or a profitability forecast.",
            "One unit per decision normalizes stored profit by stored stake. Multiple books and overlapping picks are correlated quote decisions, not an executable portfolio.",
            "Conflicts, incomplete contracts, voids, unresolved outcomes and invalid stakes are excluded; original records remain intact in the source export.",
            "The inclusive paper cohort includes records first observed during or after events and must not be treated as pre-event predictive performance.",
            "Calibration scores use only valid probabilities with win/loss outcomes. Qualified zero returns remain in ROI but are excluded from binary scoring.",
            "Intervals resample whole events, are descriptive, and do not correct for prior model search. Sparse cohorts remain uncertain.",
            "Equity and drawdown are measured at event boundaries; ordering and drawdown within an event are unavailable.",
            "Closing quotes are absent from this export. CLV is unavailable, not zero, and no improvement is inferred from paper ROI.",
            "Model version and bookmaker cohorts can cover different events. Their aggregate differences are not paired causal comparisons.",
        ],
    }
