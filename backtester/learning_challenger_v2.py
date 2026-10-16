"""Pinned multi-season shadow experiments. Exposed audit and forward refit are separate."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from backtester import learning_challenger as v1
from src.models.learning_challenger import FEATURE_NAMES_V2, day, player_features_v2, rank_players

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "config/learning-protocols/recovered-rounds-v2-identity-repair.json"


def protocol():
    result = json.loads(PROTOCOL_PATH.read_text())
    result["feature_names"] = list(FEATURE_NAMES_V2)
    return result


def fingerprint():
    paths = ("backtester/learning_challenger_v2.py", "backtester/learning_challenger.py",
             "backtester/learning_corpus.py", "src/models/learning_challenger.py",
             "backtester/sealed_holdout.py", "docs/research/sealed_holdout_events.json", "src/event_format.py",
             "scripts/train_learning_challenger.py", "scripts/weekly_learning_refresh.py",
             "src/learning_run_history.py",
             str(PROTOCOL_PATH.relative_to(ROOT)))
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}


def clean_history(tables, as_of):
    """Apply calendar, completion, team and sealed guards before any feature can read a round."""
    from backtester.sealed_holdout import sealed_event_keys
    from src.event_format import EVENT_FORMAT_TEAM, classify_event_format

    calendar = {(str(r.get("tour") or "").lower(), str(r.get("event_id")), int(r.get("year") or 0)): r
                for r in tables.get("historical_event_info", [])}
    events = defaultdict(list)
    exclusions = Counter()
    for row in tables.get("rounds", []):
        key = (str(row.get("tour") or "").lower(), str(row.get("event_id")), int(row.get("year") or 0))
        events[key].append(row)
    safe = []
    sealed = sealed_event_keys()
    for key, rows in events.items():
        info = calendar.get(key, {})
        start = day(info.get("start_date"))
        completed = {day(row.get("event_completed")) for row in rows}
        reason = None
        if key[0] != "pga":
            reason = "outside_pga"
        elif (key[1], key[2]) in sealed:
            reason = "sealed_event_never_admitted"
        elif not start or None in completed or len(completed) != 1:
            reason = "missing_or_ambiguous_calendar"
        elif not start <= next(iter(completed)) <= start + timedelta(days=7):
            reason = "completion_calendar_mismatch"
        elif next(iter(completed)) >= day(as_of):
            reason = "not_completed_before_as_of"
        elif classify_event_format(str(info.get("event_name") or ""), key[1]) == EVENT_FORMAT_TEAM:
            reason = "team_event"
        if reason:
            exclusions[reason] += len(rows)
        else:
            safe.extend(rows)
    return {**tables, "rounds": safe}, dict(exclusions)


def split_rows(rows, config):
    train_start, validation, test = (config[k] for k in ("train_start", "validation_start", "test_start"))
    return {"train": [r for r in rows if train_start <= r["start"] < validation and r["end"] < validation],
            "validation": [r for r in rows if validation <= r["start"] < test and r["end"] < test],
            "test": [r for r in rows if r["start"] >= test]}


def event_weights(rows):
    counts = Counter(row["event_key"] for row in rows)
    weights = np.asarray([1 / counts[row["event_key"]] for row in rows])
    return weights / weights.sum()


def fit(rows, specification, config):
    kind = specification["kind"]
    common = {"feature_names": list(FEATURE_NAMES_V2), "minimum_history_rounds": 8,
              "kind": kind, "specification": specification, "pair_slope": 1.0}
    if kind == "sg50_shrink":
        return {**common, "prior_rounds": specification["prior_rounds"]}
    if kind in {"ridge", "spline_ridge"}:
        knots = []
        training = rows
        if kind == "spline_ridge":
            knots = [[FEATURE_NAMES_V2.index(name), knot] for name in ("sg_total_50", "ewm_total_48") for knot in (-0.5, 0.5, 1.5)]
            training = [{**r, "features": r["features"] + [max(0, r["features"][i] - knot) for i, knot in knots]} for r in rows]
        result = v1.fit_ridge(training, specification["ridge"])
        return {**result, **common, "basis_knots": knots}
    x = np.asarray([row["features"] for row in rows])
    y = np.asarray([row["target_sg"] for row in rows])
    weights = event_weights(rows)
    intercept = float(weights @ y)
    prediction = np.full(len(rows), intercept)
    prepared = []
    for feature in range(x.shape[1]):
        order = np.argsort(x[:, feature], kind="stable")
        ordered = x[order, feature]
        thresholds = np.unique(np.quantile(ordered, config["stump_quantiles"]))
        positions = np.searchsorted(ordered, thresholds, side="right") - 1
        cumulative = np.cumsum(weights[order])
        valid = (positions >= 0) & (positions < len(rows) - 1)
        positions, thresholds = positions[valid], thresholds[valid]
        mass = cumulative[positions]
        valid = (mass >= config["stump_min_leaf_event_weight"]) & (mass <= 1 - config["stump_min_leaf_event_weight"])
        prepared.append((order, positions[valid], thresholds[valid], mass[valid]))
    trees = []
    shrink = specification["learning_rate"]
    penalty = config["stump_leaf_l2"]
    for _ in range(specification["iterations"]):
        residual = weights * (y - prediction)
        total = residual.sum()
        best = None
        for feature, (order, positions, thresholds, mass) in enumerate(prepared):
            if not len(positions):
                continue
            left_sum = np.cumsum(residual[order])[positions]
            right_sum = total - left_sum
            gain = left_sum ** 2 / (mass + penalty) + right_sum ** 2 / (1 - mass + penalty)
            index = int(gain.argmax())
            candidate = (float(gain[index]), feature, float(thresholds[index]),
                         float(shrink * left_sum[index] / (mass[index] + penalty)),
                         float(shrink * right_sum[index] / (1 - mass[index] + penalty)))
            if best is None or candidate[0] > best[0]:
                best = candidate
        if best is None:
            break
        gain, feature, threshold, left, right = best
        trees.append({"feature": feature, "threshold": threshold, "left": left, "right": right, "gain": gain})
        prediction += np.where(x[:, feature] <= threshold, left, right)
    return {**common, "intercept": intercept, "trees": trees}


def crossfit(rows, specification, config):
    dates = sorted({r["start"] for r in rows})
    first = max(8, len(dates) // 3)
    step = max(1, (len(dates) - first + 3) // 4)
    held_rows, scores, folds = [], [], []
    for index in range(first, len(dates), step):
        held_dates = set(dates[index:index + step])
        earlier = [r for r in rows if r["end"] < dates[index]]
        held = [r for r in rows if r["start"] in held_dates]
        if not earlier or not held:
            continue
        model = fit(earlier, specification, config)
        held_rows.extend(held)
        scores.extend(v1.predict_rows(model, held))
        folds.append({"fit_through": max(r["end"] for r in earlier), "forecast_start": min(r["start"] for r in held),
                      "forecast_end": max(r["end"] for r in held), "forecast_events": len(v1.group_events(held))})
    return held_rows, np.asarray(scores), folds


def stamp(model, rows, source, config, role):
    model.update({"schema_version": 2, "protocol_hash": v1.canonical_hash(config),
                  "implementation_sha256": fingerprint(), "source_sha256": source["source_sha256"],
                  "trained_through": max(r["end"] for r in rows), "training_event_ids": sorted(v1.group_events(rows)),
                  "tour_scope": "pga_only", "role": role, "promotion_allowed": False})
    model["hash"] = v1.canonical_hash(model)
    return model


def train(tables, source, *, as_of, current_field=None, progress=print):
    config = protocol()
    started = time.monotonic()
    baseline = v1.preserve_baseline(tables, source)
    safe, history_exclusions = clean_history(tables, as_of)
    progress(json.dumps({"phase": "build_temporal_dataset", "admitted_rounds": len(safe["rounds"])}), flush=True)
    rows, exclusions, pit = v1.build_dataset(safe, as_of, feature_builder=player_features_v2, calendar_course_only=True)
    splits = split_rows(rows, config)
    if any(not value for value in splits.values()):
        raise ValueError("Expanded protocol requires nonempty pre2025 train,2025 validation and2026 audit")
    progress(json.dumps({"phase": "baseline", "splits": {k: {field: value for field, value in v1._split_summary(v).items() if field != "event_ids"} for k, v in splits.items()}}), flush=True)
    v1.attach_baseline(rows, pit, baseline)
    training, validation, test = (splits[k] for k in ("train", "validation", "test"))
    trials = []
    validation_by_id = {}
    for specification in config["candidates"]:
        model = fit(training, specification, config)
        held, predictions, folds = crossfit(training, specification, config)
        model["pair_slope"] = v1.fit_pair_slope(held, predictions)
        metrics = v1.evaluate(validation, v1.predict_rows(model, validation), model["pair_slope"])
        trials.append({**specification, "validation_log_loss": metrics["pair_log_loss"],
                       "validation_sg_rmse": metrics["sg_rmse"], "validation_brier": metrics["brier"],
                       "calibration_events": len(v1.group_events(held)), "calibration_folds": folds})
        validation_by_id[specification["id"]] = (model, metrics)
        progress(json.dumps({"phase": "validation_trial", "id": specification["id"],
                             "validation_log_loss": metrics["pair_log_loss"], "validation_sg_rmse": metrics["sg_rmse"],
                             "elapsed": round(time.monotonic() - started)}), flush=True)
    selected = min(trials, key=lambda trial: (trial["validation_log_loss"], trial["validation_sg_rmse"], trial["id"]))
    specification = next(s for s in config["candidates"] if s["id"] == selected["id"])
    pretest = training + validation
    evaluation_model = fit(pretest, specification, config)
    held, forecasts, calibration_folds = crossfit(pretest, specification, config)
    evaluation_model["pair_slope"] = v1.fit_pair_slope(held, forecasts)
    stamp(evaluation_model, pretest, source, config, "pre2026_evaluation")
    naive_slope = v1.fit_pair_slope(held, np.asarray([r["naive_sg"] for r in held]))
    calibrated_baseline_slope = v1.fit_pair_slope(pretest, np.asarray([r["baseline_score"] for r in pretest]))
    score_sets = {"candidate": (v1.predict_rows(evaluation_model, test), evaluation_model["pair_slope"], True),
                  "naive": (np.asarray([r["naive_sg"] for r in test]), naive_slope, True),
                  "baseline": (np.asarray([r["baseline_score"] for r in test]), abs(float(baseline["strategy"]["platt_a"])), False),
                  "baseline_calibrated": (np.asarray([r["baseline_score"] for r in test]), calibrated_baseline_slope, False)}
    metrics = {k: v1.evaluate(test, scores, slope, sg_scores=sg) for k, (scores, slope, sg) in score_sets.items()}
    series = []
    for key, event in v1.group_events(test).items():
        indices = [i for i, row in enumerate(test) if row["event_key"] == key]
        one = {name: v1.evaluate(event, scores[indices], slope, sg_scores=sg) for name, (scores, slope, sg) in score_sets.items()}
        series.append({"event_id": event[0]["event_id"], "year": event[0]["year"], "date": event[0]["start"],
                       "event_name": event[0]["event_name"], "players": len(event), "pairs": one["candidate"]["pairs"],
                       **{f"{name}_{metric}": value for name, stats in one.items() for metric, value in stats.items()
                          if metric in {"pair_log_loss", "brier", "pair_accuracy", "rank_correlation", "sg_rmse"}},
                       "candidate_log_loss": one["candidate"]["pair_log_loss"], "baseline_log_loss": one["baseline"]["pair_log_loss"]})
    rng = np.random.default_rng(config["bootstrap"]["seed"])
    delta = {}
    for comparator in ("baseline", "naive", "baseline_calibrated"):
        losses = np.asarray([r["candidate_log_loss"] - r[f"{comparator}_pair_log_loss"] for r in series])
        boot = losses[rng.integers(0, len(losses), size=(2000, len(losses)))].mean(axis=1)
        prefix = "" if comparator == "baseline" else f"vs_{comparator}_"
        delta[prefix + "log_loss_event_bootstrap_95"] = np.quantile(boot, [0.025, 0.975]).round(6).tolist()
        delta[prefix + "log_loss"] = round(float(losses.mean()), 6)
    for key in ("pair_log_loss", "brier", "pair_accuracy", "rank_correlation"):
        delta[key] = round(metrics["candidate"][key] - metrics["baseline"][key], 6)
    # An explicitly separate forward-only model may learn from now-exposed2026 outcomes.
    progress(json.dumps({"phase": "forward_refit", "selected": specification["id"]}), flush=True)
    all_training = [row for row in rows if row["start"] >= config["train_start"]]
    forward_model = fit(all_training, specification, config)
    forward_held, forward_predictions, forward_folds = crossfit(all_training, specification, config)
    forward_model["pair_slope"] = v1.fit_pair_slope(forward_held, forward_predictions)
    stamp(forward_model, all_training, source, config, "forward_shadow_only_not_used_in_audit")
    projection_diagnostics = {}
    current_rankings = rank_players(forward_model, safe["rounds"], current_field.get("players", []),
                                   as_of=current_field["as_of"], course_num=current_field.get("course_num"),
                                   tour=current_field.get("tour", "pga"), identity_rounds=tables.get("rounds", []),
                                   diagnostics=projection_diagnostics) if current_field else []
    generated = datetime.now(timezone.utc).isoformat()
    report = {"schema_version": 2, "generated_at": generated, "as_of": as_of, "state": "evaluated",
              "protocol": config, "protocol_hash": v1.canonical_hash(config), "implementation_sha256": fingerprint(),
              "candidate": {"id": config["id"], "label": "Multi-season learning challenger", "hash": evaluation_model["hash"],
                            "method": specification["kind"], "selected_specification": specification,
                            "feature_names": list(FEATURE_NAMES_V2), "ranking_unit": "expected_sg_per_round",
                            "trained_through": evaluation_model["trained_through"], "calibration_events": len(v1.group_events(held))},
              "forward_candidate": {"hash": forward_model["hash"], "trained_through": forward_model["trained_through"],
                                    "role": forward_model["role"], "evaluated_hash": evaluation_model["hash"]},
              "baseline": {k: baseline[k] for k in ("id", "label", "hash", "source_commit", "preserved", "comparison_kind", "comparison_limit")},
              "data": {"rounds": len(safe["rounds"]), "player_events": len(rows), "events": len(v1.group_events(rows)),
                       "first_event": min(r["start"] for r in rows), "last_event": max(r["end"] for r in rows),
                       "source_sha256": source["source_sha256"], "exclusions": {**history_exclusions, **exclusions},
                       "deduplication": source.get("deduplication"), "source_count": len(source.get("origins", [])),
                       "player_identity": source.get("player_identity"),
                       "training_snapshot": {k: v for k, v in source.get("training_snapshot", {}).items() if k != "path"},
                       "forensic_sql_admitted": False},
              "splits": {k: v1._split_summary(value) for k, value in splits.items()},
              "selection": {"objective": config["selection_objective"], "trials": trials, "trial_count": len(trials),
                            "selected_id": specification["id"], "selected_ridge": specification.get("ridge"),
                            "prior_protocol_trials": 5, "test_status": config["test_status"]},
              "comparisons": {"test": metrics, "delta": delta, "event_series": series,
                              "validation_selected": validation_by_id[specification["id"]][1]},
              "diagnostics": {"calibration_folds": calibration_folds, "forward_calibration_folds": forward_folds,
                              "quarterly_exposed_audit": {}, "validation_quarters": {}},
              "market_evidence": {"state": "not_evaluated", "quote_count": 0, "clv_count": 0,
                                  "roi_pct": None, "avg_clv_pct": None,
                                  "reason": "Round-skill research only; no executable odds or qualified closes evaluated."},
              "promotion": {"eligible": False, "decision": "shadow_only", "reasons": [
                  "2026 outcomes were previously exposed; this is retrospective development evidence.",
                  "Prospective calibrated pricing, settlement and independently recorded quotes remain required."]},
              "learning": {"last_trained": generated, "next_rule": "Append weekly reports and a separately hashed forward refit; never replace the incumbent automatically."},
              "current_event": current_field and {k: current_field.get(k) for k in ("event_id", "event_name", "as_of", "tour", "year", "calendar_start", "snapshot_generated_at", "identity_basis", "state", "reason")},
              "current_projection": projection_diagnostics,
              "current_rankings": current_rankings, "current_rankings_model_hash": forward_model["hash"],
              "limitations": ["All archives were acquired retrospectively; revision/publication provenance is not established.",
                  "2026 is an exposed retrospective audit, not an untouched holdout. Model selection uses2025 only.",
                  "Sealed events, team events, withdrawals, conflicting identities and calendar mismatches are excluded.",
                  "Mean SG averages rounds actually played; missed cuts have fewer rounds and no invented weekend scores.",
                  "Probabilities condition on decisive finish order; ties, withdrawals and sportsbook rules are not priced.",
                  "Player pairs are dependent; intervals resample paired events and may still understate cross-event dependence.",
                  "The frozen PIT comparator omits live DG/simulation inputs; it is not an exact live replay.",
                  "Forward refit uses2026 development outcomes and has no retrospective performance attributed to it."],
              "elapsed_seconds": round(time.monotonic() - started, 2)}
    for label, subset, model in (("validation_quarters", validation, validation_by_id[specification["id"]][0]),
                                  ("quarterly_exposed_audit", test, evaluation_model)):
        quarters = defaultdict(list)
        for row in subset:
            quarters[f"{row['start'][:4]}-Q{(int(row['start'][5:7]) - 1) // 3 + 1}"].append(row)
        report["diagnostics"][label] = {quarter: v1.evaluate(group, v1.predict_rows(model, group), model["pair_slope"]) for quarter, group in quarters.items()}
    predictions = [{**{k: r[k] for k in ("event_id", "year", "event_name", "start", "end", "player_key", "finish", "target_sg", "history_rounds", "last_observed")},
                    **{k: r.get(k) for k in ("provider_player_key", "dg_id", "player_aliases", "tour")},
                    "candidate_sg": float(score_sets["candidate"][0][index]), "candidate_hash": evaluation_model["hash"],
                    "naive_sg": r["naive_sg"], "baseline_score": r["baseline_score"], "split": "exposed_2026_audit"} for index, r in enumerate(test)]
    return report, evaluation_model, predictions, baseline, forward_model
