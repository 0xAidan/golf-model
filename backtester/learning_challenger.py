"""Reproducible chronological training, evaluation and artifacts for a shadow ranker.

Source stores are read only. The live model, evaluator and historical ledgers are
never modified. Betting returns require actual recorded, pre-event bookmaker quotes.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import patch

import numpy as np

from src.models.learning_challenger import (
    FEATURE_NAMES, SG_COMPONENTS, day, eligible_history, finite, player_features,
    predict_expected_sg, rank_players,
    provider_player_key,
)

ROOT = Path(__file__).resolve().parents[1]
FROZEN_BASELINE_FILENAME = "original-453f49ec24f0e48a.json"


class ComparatorSourceChanged(ValueError):
    """The pinned comparator cannot be faithfully executed by this checkout."""


PROTOCOL = {
    "id": "expected-strokes-shadow-v1",
    "feature_names": list(FEATURE_NAMES),
    "ridge_grid": [0.001, 0.01, 0.1, 1.0, 10.0],
    "event_split": [0.6, 0.2, 0.2],
    "minimum_history_rounds": 8,
    "minimum_event_players": 20,
    "selection_objective": "validation_pair_log_loss",
    "calibration": "expanding-event-out-of-fold, pre-test only",
    "probability_target": "finish order conditional on a decisive, non-withdrawal pair",
    "automatic_promotion": False,
    "tour_scope": "pga_only",
    "calendar_alignment": "all source completion dates agree and lie within official PGA start plus seven days",
    "test_status": "exposed_retrospective_integrity_repair_after_cross_tour_and_provider_identity_collisions",
    "player_identity": "tour:datagolf:dg_id; human aliases are provenance only",
}


def implementation_fingerprint() -> dict[str, str]:
    """Separate code identity from the frozen experiment protocol and data identity."""
    paths = ("backtester/learning_challenger.py", "src/models/learning_challenger.py")
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def load_source(path: str | Path, *, include_quotes=True) -> tuple[dict[str, list[dict]], dict]:
    """Load an exported sports-data snapshot or take a read-only SQLite snapshot."""
    path = Path(path)
    tables: dict[str, list[dict]] = defaultdict(list)
    if path.suffix == ".gz":
        with gzip.open(path, "rt") as handle:
            for line in handle:
                item = json.loads(line)
                tables[item["table"]].append(item["row"])
    else:
        conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            present = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ("rounds", "historical_event_info", "track_configs", "weight_sets", "active_strategy", "live_model_registry", "research_model_registry"):
                if table in present:
                    tables[table] = [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]
            if include_quotes and "market_prediction_rows" in present:
                tables["market_prediction_rows"] = [dict(r) for r in conn.execute(
                    "SELECT * FROM market_prediction_rows WHERE market_family='matchup' AND section IN ('upcoming', 'legacy')"
                )]
        finally:
            conn.close()
    # Hash the exact extracted transaction, including WAL-visible rows. The main
    # SQLite file alone can remain byte-identical while committed WAL data change.
    snapshot_digest = hashlib.sha256()
    for table in sorted(name for name in tables if not name.startswith("_")):
        snapshot_digest.update((table + "\n").encode())
        records = sorted(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) for row in tables[table])
        for record in records:
            snapshot_digest.update((record + "\n").encode())
    digest = snapshot_digest.hexdigest()
    metadata = dict((tables.get("_manifest") or [{}])[0])
    if not metadata:
        git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
        metadata = {"source": "sqlite_read_only_transaction", "git_commit": git.stdout.strip() or None}
    metadata.update({"source_sha256": digest, "table_counts": {k: len(v) for k, v in tables.items() if not k.startswith("_")}})
    return dict(tables), metadata


def preserve_baseline(tables: dict, source: dict) -> dict:
    """Read the pinned original; future live settings cannot redefine this comparator."""
    frozen = ROOT / "config" / "model-baselines" / FROZEN_BASELINE_FILENAME
    if not frozen.is_file():
        raise ComparatorSourceChanged("comparator_source_missing: pinned original model manifest is required")
    baseline = json.loads(frozen.read_text())
    if canonical_hash({k: v for k, v in baseline.items() if k != "hash"}) != baseline.get("hash"):
        raise ComparatorSourceChanged("comparator_source_changed: pinned baseline manifest integrity check failed")
    mismatches = [name for name, digest in baseline.get("source_hashes", {}).items()
                  if not (ROOT / name).is_file() or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
    if mismatches:
        raise ComparatorSourceChanged("comparator_source_changed: " + ", ".join(sorted(mismatches)))
    return baseline


def _finish(value: Any) -> float | None:
    text = str(value or "").strip().upper()
    if text in {"CUT", "MC", "MDF"}:
        return 1000.0
    text = text.removeprefix("T")
    return float(text) if text.isdigit() and int(text) > 0 else None


def build_dataset(tables: dict, as_of: str, *, feature_builder=player_features, calendar_course_only=False) -> tuple[list[dict], dict, list[dict]]:
    """Build event-level rows with independently recomputed, strictly prior features."""
    cutoff = day(as_of)
    if cutoff is None:
        raise ValueError("as_of must be an ISO date")
    calendar = {(str(r.get("tour") or "").strip().lower(), str(r.get("event_id")), int(r.get("year") or 0)): r for r in tables.get("historical_event_info", [])}
    events: dict[tuple, list] = defaultdict(list)
    histories: dict[str, list] = defaultdict(list)
    exclusions: Counter = Counter()
    rounds = tables.get("rounds", [])
    for row in rounds:
        tour = str(row.get("tour") or "").strip().lower()
        if tour != "pga":
            exclusions["round_outside_pga_scope"] += 1
            continue
        completed = day(row.get("event_completed"))
        identity = provider_player_key(row)
        if identity is None:
            exclusions["missing_provider_player_identity"] += 1
            continue
        if completed is None or completed >= cutoff:
            exclusions["unknown_or_unfinished_round"] += 1
            continue
        events[(tour, str(row.get("event_id")), int(row.get("year") or 0))].append(row)
        histories[identity].append(row)
    try:
        from backtester.sealed_holdout import sealed_event_keys
        sealed = sealed_event_keys()
    except FileNotFoundError:
        sealed = set()
    dataset, pit_rows, course_rows = [], [], []
    for key, current in events.items():
        info = calendar.get(key)
        start = day((info or {}).get("start_date"))
        end = max(day(r["event_completed"]) for r in current)
        if not info or start is None or start > end or end >= cutoff:
            exclusions["event_without_verified_calendar"] += 1
            continue
        if len({day(r["event_completed"]) for r in current}) != 1 or end > start + timedelta(days=7):
            exclusions["event_source_calendar_mismatch"] += 1
            continue
        if (key[1], key[2]) in sealed:
            exclusions["sealed_holdout_event"] += 1
            continue
        name = str(info.get("event_name") or current[0].get("event_name") or "")
        from src.event_format import EVENT_FORMAT_TEAM, classify_event_format
        if classify_event_format(name, key[1]) == EVENT_FORMAT_TEAM:
            exclusions["team_format_event"] += 1
            continue
        course = Counter(str(r.get("course_num")) for r in current).most_common(1)[0][0]
        if calendar_course_only:
            course = str(info.get("course_id") or "")
            course = course if course and ";" not in course and "," not in course else None
        by_player: dict[str, list] = defaultdict(list)
        for row in current:
            by_player[provider_player_key(row)].append(row)
        cohort = []
        for player, outcomes in by_player.items():
            finishes = {_finish(r.get("fin_text")) for r in outcomes}
            if None in finishes or len(finishes) != 1:
                exclusions["withdrawn_or_ambiguous_player_event"] += 1
                continue
            # Reuse the identity/conflict filter for targets, without admitting future events.
            target_rows = eligible_history(outcomes, cutoff.isoformat())
            if not target_rows:
                exclusions["missing_or_conflicting_target"] += 1
                continue
            profile = feature_builder(histories[player], as_of=start.isoformat(), course_num=course)
            if profile["history_rounds"] < PROTOCOL["minimum_history_rounds"]:
                exclusions["insufficient_prior_rounds"] += 1
                continue
            prior = eligible_history(histories[player], start.isoformat())
            row = {
                "event_id": key[1], "year": key[2], "event_key": f"{key[2]}:{key[1]}", "tour": key[0],
                "event_name": name, "start": start.isoformat(), "end": end.isoformat(),
                "player_key": player, "player_display": outcomes[0].get("player_name") or player,
                "provider_player_key": player, "dg_id": int(player.rsplit(":", 1)[1]),
                "player_aliases": sorted({str(r.get("player_key")) for r in histories[player] if r.get("player_key")}),
                "features": profile["values"], "target_sg": sum(float(r["sg_total"]) for r in target_rows) / len(target_rows),
                "finish": next(iter(finishes)), "naive_sg": profile["naive_sg"],
                "history_rounds": profile["history_rounds"], "last_observed": profile["last_observed"],
            }
            cohort.append(row)
            for window in (8, 12, 16, 20, 24, 50):
                sample = prior[-window:]
                values = {component: sum(float(r.get(component) or 0.0) for r in sample) / len(sample) for component in SG_COMPONENTS}
                values["sg_t2g"] = values["sg_total"] - values["sg_putt"]
                pit_rows.append({"event_id": key[1], "year": key[2], "player_key": player, "window": window, "rounds_used": len(sample), **values})
            same_course = [r for r in prior if str(r.get("course_num")) == course]
            if same_course:
                values = {component: sum(float(r.get(component) or 0.0) for r in same_course) / len(same_course) for component in SG_COMPONENTS}
                historical_finishes = [f for r in same_course if (f := _finish(r.get("fin_text"))) is not None]
                course_rows.append({"event_id": key[1], "year": key[2], "player_key": player, "rounds_played": len(same_course),
                                    "avg_finish": sum(historical_finishes) / len(historical_finishes) if historical_finishes else None,
                                    "best_finish": min(historical_finishes) if historical_finishes else None, **values})
        if len(cohort) < PROTOCOL["minimum_event_players"]:
            exclusions["insufficient_event_cohort"] += 1
            continue
        if len({r["finish"] for r in cohort}) < 2:
            exclusions["event_without_decisive_comparisons"] += 1
            continue
        dataset.extend(cohort)
    # The unchanged baseline scorer receives independently reconstructed PIT tables.
    return sorted(dataset, key=lambda r: (r["start"], r["event_key"], r["player_key"])), dict(exclusions), [pit_rows, course_rows]


def attach_baseline(dataset: list[dict], pit_tables: list[list], baseline: dict) -> None:
    from backtester.pit_models import compute_pit_composite
    from src import db

    pit_rows, course_rows = pit_tables
    by_event_window: dict[tuple, list] = defaultdict(list)
    for row in pit_rows:
        by_event_window[(row["event_id"], row["year"], row["window"])].append(row)
    for rows in by_event_window.values():
        for index, row in enumerate(sorted(rows, key=lambda r: (-r["sg_total"], r["player_key"])), 1):
            row["sg_total_rank"] = index
    with tempfile.TemporaryDirectory(prefix="golf-frozen-pit-") as temp:
        path = Path(temp) / "pit.sqlite"
        conn = sqlite3.connect(path)
        for table, rows, columns in (
            ("pit_rolling_stats", pit_rows, ("event_id", "year", "player_key", "window", *SG_COMPONENTS, "sg_t2g", "rounds_used", "sg_total_rank")),
            ("pit_course_stats", course_rows, ("event_id", "year", "player_key", *SG_COMPONENTS, "rounds_played", "avg_finish", "best_finish")),
        ):
            conn.execute(f"CREATE TABLE {table} ({','.join(columns)})")
            conn.executemany(f"INSERT INTO {table} VALUES ({','.join('?' for _ in columns)})", [[r.get(k) for k in columns] for r in rows])
            conn.execute(f"CREATE INDEX idx_{table} ON {table}(event_id,year)")
        conn.commit()
        conn.close()
        connections = []

        def readonly():
            c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            c.row_factory = sqlite3.Row
            connections.append(c)
            return c

        strategy = baseline["strategy"]
        grouped = group_events(dataset)
        with patch.object(db, "get_conn", readonly):
            for rows in grouped.values():
                first = rows[0]
                scores = compute_pit_composite(first["event_id"], first["year"],
                    w_course_fit=strategy["w_sub_course_fit"], w_form=strategy["w_sub_form"], w_momentum=strategy["w_sub_momentum"])
                for row in rows:
                    row["baseline_score"] = float(scores.get(row["player_key"], {}).get("composite", 50.0))
                for c in connections:
                    c.close()
                connections.clear()


def group_events(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["event_key"]].append(row)
    return dict(grouped)


def chronological_split(rows: list[dict]) -> dict[str, list[dict]]:
    """Keep same-day events together and purge events overlapping later split starts."""
    dates = sorted({r["start"] for r in rows})
    if len(dates) < 20:
        return {"train": [], "validation": [], "test": []}
    train_end = dates[int(len(dates) * 0.6)]
    test_start = dates[int(len(dates) * 0.8)]
    return {
        "train": [r for r in rows if r["start"] < train_end and r["end"] < train_end],
        "validation": [r for r in rows if train_end <= r["start"] < test_start and r["end"] < test_start],
        "test": [r for r in rows if r["start"] >= test_start],
    }


def fit_ridge(rows: list[dict], ridge: float) -> dict:
    x = np.asarray([r["features"] for r in rows], dtype=float)
    y = np.asarray([r["target_sg"] for r in rows], dtype=float)
    counts = Counter(r["event_key"] for r in rows)
    weights = np.asarray([1.0 / counts[r["event_key"]] for r in rows])
    weights /= weights.sum()
    mean = (x * weights[:, None]).sum(axis=0)
    scale = np.sqrt(((x - mean) ** 2 * weights[:, None]).sum(axis=0))
    scale[scale < 1e-8] = 1.0
    z = (x - mean) / scale
    intercept = float((y * weights).sum())
    coef = np.linalg.solve(z.T @ (z * weights[:, None]) + ridge * np.eye(z.shape[1]), z.T @ (weights * (y - intercept)))
    return {"schema_version": 1, "feature_names": list(FEATURE_NAMES), "feature_mean": mean.tolist(), "feature_scale": scale.tolist(),
            "coefficients": coef.tolist(), "intercept": intercept, "ridge": ridge, "pair_slope": 1.0,
            "minimum_history_rounds": PROTOCOL["minimum_history_rounds"]}


def predict_rows(model: Mapping, rows: list[dict]) -> np.ndarray:
    return np.asarray([predict_expected_sg(model, r["features"]) for r in rows])


def pair_arrays(rows: list[dict], scores: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    event_indices: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        event_indices[row["event_key"]].append(index)
    gaps, outcomes, weights = [], [], []
    for indices in event_indices.values():
        ii, jj = np.triu_indices(len(indices), 1)
        positions = np.asarray([rows[k]["finish"] for k in indices])
        valid = positions[ii] != positions[jj]
        ii, jj = ii[valid], jj[valid]
        if not len(ii):
            continue
        values = scores[indices]
        gaps.extend((values[ii] - values[jj]).tolist())
        outcomes.extend((positions[ii] < positions[jj]).astype(float).tolist())
        weights.extend([1.0 / len(ii)] * len(ii))
    return np.asarray(gaps), np.asarray(outcomes), np.asarray(weights)


def fit_pair_slope(rows: list[dict], scores: np.ndarray) -> float:
    gaps, outcomes, weights = pair_arrays(rows, scores)
    if len(gaps) == 0:
        return 1.0
    weights /= weights.sum()
    slope = 1.0
    for _ in range(40):
        p = 1 / (1 + np.exp(-np.clip(slope * gaps, -30, 30)))
        grad = np.sum(weights * (p - outcomes) * gaps) + 0.001 * slope
        curvature = np.sum(weights * p * (1 - p) * gaps ** 2) + 0.001
        updated = min(10.0, max(0.01, slope - grad / curvature))
        if abs(updated - slope) < 1e-8:
            break
        slope = updated
    return float(slope)


def crossfit_scores(rows: list[dict], ridge: float) -> tuple[list[dict], np.ndarray]:
    """Expanding forecasts for calibration; a forecast's event is absent from its fit."""
    dates = sorted({r["start"] for r in rows})
    first = max(8, len(dates) // 3)
    step = max(1, (len(dates) - first + 3) // 4)
    held_rows, predictions = [], []
    for start in range(first, len(dates), step):
        dates_held = set(dates[start:start + step])
        training = [r for r in rows if r["end"] < dates[start]]
        held = [r for r in rows if r["start"] in dates_held]
        if not training or not held:
            continue
        model = fit_ridge(training, ridge)
        held_rows.extend(held)
        predictions.extend(predict_rows(model, held).tolist())
    return held_rows, np.asarray(predictions)


def _correlation(predicted: np.ndarray, actual: np.ndarray) -> float | None:
    def ranks(values):
        order = values.argsort(kind="stable")
        ranks = np.empty(len(values), dtype=float)
        start = 0
        while start < len(order):
            end = start + 1
            while end < len(order) and values[order[end]] == values[order[start]]:
                end += 1
            ranks[order[start:end]] = (start + end - 1) / 2
            start = end
        return ranks
    a, b = ranks(predicted), ranks(actual)
    return float(np.corrcoef(a, b)[0, 1]) if np.std(a) > 0 and np.std(b) > 0 else None


def evaluate(rows: list[dict], scores: np.ndarray, slope: float, *, sg_scores: bool = True) -> dict:
    gaps, outcomes, weights = pair_arrays(rows, scores)
    if not len(gaps):
        return {"events": 0, "player_events": len(rows), "pairs": 0, "pair_log_loss": None, "brier": None, "pair_accuracy": None, "rank_correlation": None, "sg_rmse": None}
    p = 1 / (1 + np.exp(-np.clip(slope * gaps, -30, 30)))
    weights /= weights.sum()
    reliability = []
    for lower in np.arange(0, 1, 0.1):
        mask = (p >= lower) & (p < lower + 0.1)
        if mask.any():
            reliability.append({"predicted": float(np.average(p[mask], weights=weights[mask])),
                                "observed": float(np.average(outcomes[mask], weights=weights[mask])), "pairs": int(mask.sum())})
    grouped = group_events(rows)
    rank_correlations, sg_errors = [], []
    for key, event in grouped.items():
        indices = [i for i, r in enumerate(rows) if r["event_key"] == key]
        corr = _correlation(scores[indices], -np.asarray([r["finish"] for r in event]))
        if corr is not None:
            rank_correlations.append(corr)
        sg_errors.append(float(np.mean((scores[indices] - np.asarray([r["target_sg"] for r in event])) ** 2)))
    return {
        "events": len(grouped), "player_events": len(rows), "pairs": len(gaps),
        "pair_log_loss": round(float(np.sum(weights * (-outcomes * np.log(p) - (1 - outcomes) * np.log1p(-p)))), 6),
        "brier": round(float(np.sum(weights * (p - outcomes) ** 2)), 6),
        "pair_accuracy": round(float(np.sum(weights * np.where(p == 0.5, 0.5, (p > 0.5) == outcomes))), 6),
        "rank_correlation": round(float(np.mean(rank_correlations)), 6) if rank_correlations else None,
        "sg_rmse": round(math.sqrt(float(np.mean(sg_errors))), 6) if sg_scores else None,
        "calibration": reliability,
        "sample_unit": "events; player pairs are correlated and not independent bets",
    }


def _split_summary(rows: list[dict]) -> dict:
    return {"events": len(group_events(rows)), "player_events": len(rows), "start": min((r["start"] for r in rows), default=None),
            "end": max((r["end"] for r in rows), default=None), "event_ids": sorted(group_events(rows))}


def train_and_evaluate(tables: dict, source: dict, *, as_of: str, current_field: dict | None = None) -> tuple[dict, dict | None, list[dict], dict]:
    baseline = preserve_baseline(tables, source)
    rows, exclusions, pit = build_dataset(tables, as_of)
    generated = datetime.now(timezone.utc).isoformat()
    splits = chronological_split(rows)
    report: dict[str, Any] = {
        "schema_version": 1, "generated_at": generated, "as_of": as_of, "state": "insufficient_data",
        "protocol": PROTOCOL, "protocol_hash": canonical_hash(PROTOCOL),
        "candidate": {"id": "expected-strokes-shadow-v1", "hash": None, "label": "Learning challenger", "method": "regularized_expected_strokes", "feature_names": list(FEATURE_NAMES), "ranking_unit": "expected_sg_per_round"},
        "baseline": {k: baseline[k] for k in ("id", "label", "hash", "source_commit", "preserved", "comparison_kind", "comparison_limit")},
        "data": {"rounds": len(tables.get("rounds", [])), "player_events": len(rows), "events": len(group_events(rows)), "first_event": min((r["start"] for r in rows), default=None), "last_event": max((r["end"] for r in rows), default=None), "source_sha256": source["source_sha256"], "exclusions": exclusions},
        "implementation_sha256": implementation_fingerprint(),
        "splits": {k: _split_summary(v) for k, v in splits.items()},
        "selection": {"objective": PROTOCOL["selection_objective"], "trials": [], "selected_ridge": None},
        "comparisons": {"test": {}, "delta": {}, "event_series": []},
        "market_evidence": {"state": "insufficient_pre_event_quotes", "quote_count": 0, "clv_count": 0, "roi_pct": None, "avg_clv_pct": None, "reason": "No historical sportsbook matchup odds corpus. DataGolf model prices are not executable bookmaker quotes; no ROI or CLV inferred from them."},
        "promotion": {"eligible": False, "decision": "shadow_only", "reasons": ["Prospective independently recorded market evidence is required before promotion.", "Retrospective score improvement does not establish profitable betting."]},
        "learning": {"last_trained": generated, "next_rule": "Refresh completed rounds weekly, append a versioned report, retain the original model and every prior run."},
        "current_event": current_field and {k: current_field.get(k) for k in ("event_id", "event_name", "as_of")},
        "current_rankings": [],
        "limitations": [
            "Historical archive was acquired after events; retrospective event-date separation is not proof of contemporaneous publication or original vendor revisions.",
            "Only PGA events with verified calendar dates, at least 20 covered players, and at least 8 prior rounds per player are included; team events, sealed holdouts, withdrawals and ambiguous finishes are excluded.",
            "Mean SG is measured over rounds actually played. Missed-cut players have fewer outcome rounds; no hypothetical weekend rounds are invented.",
            "Binary pair probabilities are conditional on decisive finish order; they do not price tie, withdrawal, dead-heat, 3-ball or placement settlement rules.",
            "Equal event weighting and event-bootstrap intervals account for event concentration; overlapping players and years can still create dependence.",
            "The frozen PIT comparator lacks historical DG and simulation inputs present in the live blend. Current model stays accessible and unchanged.",
            "This is a retrospective integrity repair after an invalid cross-tour run exposed the test period; it is not a fresh untouched holdout or prospective evidence. Test targets remain absent from fitting and selection.",
        ],
    }
    quote_rows = tables.get("market_prediction_rows", [])
    calendar = {(str(r.get("event_id")), int(r.get("year") or 0)): r for r in tables.get("historical_event_info", []) if str(r.get("tour") or "").lower() == "pga"}
    admitted_quotes = set()
    for row in quote_rows:
        generated_day = day(row.get("generated_at"))
        event = calendar.get((str(row.get("event_id")), generated_day.year if generated_day else 0)) or {}
        event_start = day(event.get("start_date"))
        if (generated_day and event_start and generated_day < event_start and generated_day < day(as_of)
                and row.get("market_type") == "tournament_matchups" and row.get("player_key") and row.get("opponent_key")):
            admitted_quotes.add((row.get("event_id"), row.get("player_key"), row.get("opponent_key"), row.get("book")))
    report["market_evidence"].update({"raw_quote_rows": len(quote_rows), "source_event_count": len({r.get("event_id") for r in quote_rows}),
                                      "quote_count": len(admitted_quotes), "timing_rule": "Recorded UTC calendar date strictly before the official event-start date; same-day quotes are excluded without verified tee-time timing."})
    if any(not split for split in splits.values()):
        report["promotion"]["reasons"].append("Insufficient chronological train, validation and test events.")
        return report, None, [], baseline
    attach_baseline(rows, pit, baseline)
    training, validation, test = splits["train"], splits["validation"], splits["test"]
    trials = []
    for ridge in PROTOCOL["ridge_grid"]:
        model = fit_ridge(training, ridge)
        calibration_rows, forecasts = crossfit_scores(training, ridge)
        model["pair_slope"] = fit_pair_slope(calibration_rows, forecasts)
        metrics = evaluate(validation, predict_rows(model, validation), model["pair_slope"])
        trials.append({"ridge": ridge, "validation_log_loss": metrics["pair_log_loss"], "validation_sg_rmse": metrics["sg_rmse"], "calibration_events": len(group_events(calibration_rows))})
    selected = min(trials, key=lambda r: (r["validation_log_loss"], r["validation_sg_rmse"], -r["ridge"]))
    pretest = training + validation
    model = fit_ridge(pretest, selected["ridge"])
    calibration_rows, forecasts = crossfit_scores(pretest, selected["ridge"])
    model["pair_slope"] = fit_pair_slope(calibration_rows, forecasts)
    naive_slope = fit_pair_slope(calibration_rows, np.asarray([r["naive_sg"] for r in calibration_rows]))
    model.update({"protocol_hash": canonical_hash(PROTOCOL), "tour_scope": "pga_only", "implementation_sha256": implementation_fingerprint(), "trained_through": max(r["end"] for r in pretest),
                  "test_start": min(r["start"] for r in test), "source_sha256": source["source_sha256"], "training_event_ids": sorted(group_events(pretest)),
                  "calibration_events": len(group_events(calibration_rows)), "promotion_allowed": False})
    model["hash"] = canonical_hash(model)
    score_sets = {"candidate": (predict_rows(model, test), model["pair_slope"], True),
                  "baseline": (np.asarray([r["baseline_score"] for r in test]), abs(float(baseline["strategy"]["platt_a"])), False),
                  "naive": (np.asarray([r["naive_sg"] for r in test]), naive_slope, True)}
    metrics = {key: evaluate(test, scores, slope, sg_scores=sg) for key, (scores, slope, sg) in score_sets.items()}
    series = []
    for key, event in group_events(test).items():
        indices = [i for i, r in enumerate(test) if r["event_key"] == key]
        one = {name: evaluate(event, scores[indices], slope, sg_scores=sg) for name, (scores, slope, sg) in score_sets.items()}
        series.append({"event_id": event[0]["event_id"], "year": event[0]["year"], "date": event[0]["start"], "event_name": event[0]["event_name"], "players": len(event), "pairs": one["candidate"]["pairs"],
                       **{f"{name}_{metric}": stats[metric] for name, stats in one.items() for metric in ("pair_log_loss", "brier", "pair_accuracy", "rank_correlation", "sg_rmse")},
                       "candidate_log_loss": one["candidate"]["pair_log_loss"], "baseline_log_loss": one["baseline"]["pair_log_loss"]})
    delta = {key: round(metrics["candidate"][key] - metrics["baseline"][key], 6) for key in ("pair_log_loss", "brier", "pair_accuracy", "rank_correlation")}
    rng = np.random.default_rng(20261015)
    losses = np.asarray([r["candidate_log_loss"] - r["baseline_log_loss"] for r in series])
    boot = losses[rng.integers(0, len(losses), size=(2000, len(losses)))].mean(axis=1)
    delta["log_loss_event_bootstrap_95"] = np.quantile(boot, [0.025, 0.975]).round(6).tolist()
    naive_losses = np.asarray([r["candidate_log_loss"] - r["naive_pair_log_loss"] for r in series])
    naive_boot = naive_losses[rng.integers(0, len(naive_losses), size=(2000, len(naive_losses)))].mean(axis=1)
    delta["vs_naive_log_loss"] = round(metrics["candidate"]["pair_log_loss"] - metrics["naive"]["pair_log_loss"], 6)
    delta["vs_naive_log_loss_event_bootstrap_95"] = np.quantile(naive_boot, [0.025, 0.975]).round(6).tolist()
    report.update({"state": "evaluated", "selection": {"objective": PROTOCOL["selection_objective"], "trials": trials, "selected_ridge": selected["ridge"]},
                   "comparisons": {"test": metrics, "delta": delta, "event_series": series}})
    report["candidate"].update({"hash": model["hash"], "trained_through": model["trained_through"], "calibration_events": model["calibration_events"]})
    if current_field:
        pga_rounds = [r for r in tables.get("rounds", []) if str(r.get("tour") or "").lower() == "pga"]
        report["current_rankings"] = rank_players(model, pga_rounds, current_field.get("players", []), as_of=current_field["as_of"], course_num=current_field.get("course_num"))
    predictions = [{**{k: r[k] for k in ("event_id", "year", "event_name", "start", "end", "player_key", "player_display", "finish", "target_sg", "history_rounds", "last_observed", "baseline_score")},
                    "candidate_sg": round(float(score_sets["candidate"][0][i]), 6), "naive_sg": r["naive_sg"], "split": "test", "candidate_hash": model["hash"]} for i, r in enumerate(test)]
    return report, model, predictions, baseline


def save_artifacts(output: Path, report: dict, model: dict | None, predictions: list[dict], baseline: dict, source: dict, *, forward_model=None, input_files=None) -> Path:
    """Append an immutable run; update only the latest pointer. Identical inputs reuse a run."""
    identity = canonical_hash({"source": source["source_sha256"], "protocol": report["protocol_hash"], "candidate": report["candidate"]["hash"],
                               "baseline": baseline["hash"], "as_of": report["as_of"], "current_event": report.get("current_event"),
                               "projection": report.get("current_rankings", []), "forward": report.get("forward_candidate", {}).get("hash")})
    run_id = f"{report['as_of'].replace('-', '')}-{identity[:16]}"
    destination = output / run_id
    destination.mkdir(parents=True, exist_ok=True)
    files = {"report.json": report, "model.json": model, "baseline.json": baseline, "source-manifest.json": source}
    if forward_model is not None:
        files["forward-model.json"] = forward_model
        files["protocol.json"] = report["protocol"]
    for filename, value in files.items():
        path = destination / filename
        if not path.exists():
            with path.open("x") as handle:
                json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
                handle.write("\n")
    implementation = report.get("implementation_sha256", {})
    for name, expected in implementation.items():
        content = (ROOT / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("Implementation changed during training; report publication refused")
        target = destination / "implementation" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            with target.open("xb") as handle:
                handle.write(content)
    input_hashes = {}
    for name, path in (input_files or {}).items():
        content = Path(path).read_bytes()
        input_hashes[name] = hashlib.sha256(content).hexdigest()
        target = destination / name
        if not target.exists():
            with target.open("xb") as handle:
                handle.write(content)
    reproduction = destination / "reproducibility.json"
    if not reproduction.exists():
        with reproduction.open("x") as handle:
            json.dump({"python": sys.version, "numpy": np.__version__, "implementation_sha256": implementation,
                       "input_sha256": input_hashes, "source_sha256": source["source_sha256"],
                       "baseline_sha256": baseline["hash"], "protocol_sha256": report["protocol_hash"],
                       "automatic_promotion": False}, handle, indent=2, sort_keys=True)
    path = destination / "predictions.jsonl"
    if not path.exists():
        with path.open("x") as handle:
            for row in predictions:
                handle.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
    pointer = {"schema_version": 1, "run_id": run_id, "report": f"{run_id}/report.json", "model": f"{run_id}/model.json", "candidate_hash": report["candidate"]["hash"]}
    if forward_model is not None:
        pointer.update({"forward_model": f"{run_id}/forward-model.json", "forward_hash": forward_model["hash"]})
    temp = output / "latest.json.tmp"
    temp.write_text(json.dumps(pointer, indent=2, sort_keys=True) + "\n")
    temp.replace(output / "latest.json")
    registry_path = output / "registry.jsonl"
    registered = set()
    if registry_path.is_file():
        with registry_path.open() as registry:
            registered = {json.loads(line)["run_id"] for line in registry if line.strip()}
    if run_id not in registered:
        with registry_path.open("a") as registry:
            registry.write(json.dumps({"run_id": run_id, "candidate_hash": report["candidate"]["hash"],
                                       "forward_hash": report.get("forward_candidate", {}).get("hash"),
                                       "protocol_hash": report["protocol_hash"], "source_sha256": source["source_sha256"],
                                       "as_of": report["as_of"], "state": report["state"], "promotion_allowed": False}, sort_keys=True) + "\n")
    baseline_dir = ROOT / "config" / "model-baselines"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = baseline_dir / f"original-{baseline['hash'][:16]}.json"
    if not baseline_path.exists():
        with baseline_path.open("x") as handle:
            json.dump(baseline, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
    return destination
