"""Tier 1 autonomous loop: mutate -> fast-tier evaluate -> keep/discard -> confirm.

Per docs/research/PROGRAM.md:
- Mutations stay strictly within the artifact's declared ranges (schema v2).
- One primary score decides everything: matchup-weighted walk-forward performance
  vs the current champion-candidate, under strict guardrails, on the frozen
  SEARCH window (13 events).
- Survivors must re-pass on the rolling CONFIRMATION window (3 most recent
  completed events) before being staged as PROMOTION-READY. Nothing is ever
  promoted automatically.
- Every trial appends to output/research/ledger.jsonl; nothing is deleted.
- Multiplicity armor: each candidate lineage records trials_run so dossiers can
  state deflation context honestly.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict
from pathlib import Path
from typing import Any

from backtester.fast_tier import (
    FastTierWindow,
    compute_precomputed_baseline_results,
    select_research_windows,
)
from backtester.research_lab.canonical import (
    EVAL_CONTRACT_VERSION_WALK_FORWARD,
    evaluation_from_walk_forward_dict,
)
from backtester.research_lab.fingerprint import evaluator_identity
from backtester.research_lab.ledger import append_ledger_row, _git_head
from backtester.sealed_holdout import filter_sealed_events
from backtester.strategy import StrategyConfig
from backtester.strategy_config_artifact import (
    ConfigArtifactError,
    STRATEGY_CONFIG_ARTIFACT_PATH,
    artifact_hash,
    diff_artifacts,
    load_strategy_artifact,
)
from backtester.weighted_walkforward import (
    compute_blended_score,
    evaluate_guardrails,
    evaluate_weighted_walkforward,
)

DOSSIER_DIR = Path("output") / "research" / "promotion_ready"

# Minimum picks in a confirmation-window verdict for it to count (tiny windows
# are reported but never decisive).
MIN_CONFIRMATION_BETS = 10


def load_champion_candidate(path: Path | None = None) -> dict[str, Any]:
    """Load the current champion-candidate artifact (the thing Tier 1 mutates)."""
    return load_strategy_artifact(path or STRATEGY_CONFIG_ARTIFACT_PATH)


def propose_mutation(
    artifact: dict[str, Any],
    *,
    rng: random.Random,
    magnitude: float = 0.25,
) -> tuple[dict[str, Any], str]:
    """
    Propose one within-range mutation of the artifact.

    Picks a random ranged field and moves its override value toward a random
    point between current value and a range bound. Returns (new_artifact, description).
    """
    ranges = artifact.get("ranges") or {}
    if not ranges:
        raise ConfigArtifactError("No mutation ranges declared in strategy_config.json")
    field = rng.choice(sorted(ranges))
    bounds = ranges[field]
    lo, hi = float(bounds["min"]), float(bounds["max"])
    overrides = dict(artifact.get("overrides") or {})
    if field not in overrides:
        # Seed from midpoint when the field has no explicit value yet.
        baseline = StrategyConfig()
        current = float(getattr(baseline, field))
    else:
        current = float(overrides[field])
    target = rng.uniform(lo, hi) if rng.random() < 0.5 else (
        lo + (hi - lo) * (1 - magnitude) + current * magnitude
    )
    step = (hi - lo) * magnitude
    new_value = min(hi, max(lo, current + rng.uniform(-step, step)))
    new_value = round(new_value, 4)
    if new_value == current:
        return artifact, ""
    new_artifact = json.loads(json.dumps(artifact))  # deep copy
    new_artifact.setdefault("overrides", {})[field] = new_value
    description = f"{field}: {current} -> {new_value}"
    return new_artifact, description


def evaluate_on_events(
    strategy: StrategyConfig,
    baseline_strategy: StrategyConfig,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Fast-tier walk-forward over an explicit event set (frozen evaluator)."""
    splits_test_count = max(0, len(events) - 2)
    if splits_test_count <= 0:
        # Too few events for expanding splits; replay directly as one summary.
        from backtester.weighted_walkforward import _default_replay_runner

        rows = [{**e, **_default_replay_runner(e, strategy)} for e in events]
        base_rows = [{**e, **_default_replay_runner(e, baseline_strategy)} for e in events]
        from backtester.weighted_walkforward import compute_weighted_metrics

        raw = {
            "summary_metrics": compute_weighted_metrics(rows),
            "baseline_summary_metrics": compute_weighted_metrics(base_rows),
            "guardrail_results": {},
            "segmented_metrics": None,
            "baseline_segmented_metrics": None,
            "splits": [],
            "event_results": rows,
            "baseline_event_results": base_rows,
        }
        result = evaluation_from_walk_forward_dict(raw)
        result.metadata = {"fast_tier": True, "direct_window": True}
        return result

    with FastTierWindow(events):
        baseline_payload_rows = compute_precomputed_baseline_results(baseline_strategy, events)
        raw = evaluate_weighted_walkforward(
            strategy=strategy,
            baseline_strategy=baseline_strategy,
            events=events,
            precomputed_baseline=baseline_payload_rows,
        )
    result = evaluation_from_walk_forward_dict(raw)
    result.metadata = {"fast_tier": True}
    return result


def run_tier1_cycle(
    *,
    budget=None,
    max_trials: int | None = None,
    seed: int = 42,
    artifact_path: Path | None = None,
    alert_fn=None,
) -> dict[str, Any]:
    """
    One full Tier 1 cycle. Returns a summary payload; every trial is ledgered.

    Verdicts: keep / discard / confirm_pass (staged promotion-ready) /
    confirm_fail / report_only (n below floor).
    """
    from src.db import ensure_initialized

    ensure_initialized()
    rng = random.Random(seed)
    artifact = load_champion_candidate(artifact_path)
    parent_hash = artifact_hash(artifact)

    baseline_strategy = StrategyConfig(name="champion_candidate")
    windows = select_research_windows()
    search_events = windows["search"]
    confirmation_events = windows["confirmation"]

    summary: dict[str, Any] = {
        "kind": "tier1_cycle",
        "parent_hash": parent_hash,
        "search_events": len(search_events),
        "confirmation_events": len(confirmation_events),
        "trials": [],
        "keeps": 0,
        "discards": 0,
        "staged_promotions": 0,
    }

    if not search_events:
        summary["verdict"] = "no_data"
        return summary

    max_trials = max_trials if max_trials is not None else (budget.max_trials if budget else 30)
    best_keep = None

    for trial_index in range(max_trials):
        if budget and budget.exhausted():
            break
        if budget:
            budget.start_trial()

        candidate_artifact, description = propose_mutation(artifact, rng=rng)
        if not description:
            continue
        candidate_hash = artifact_hash(candidate_artifact)
        candidate = build_candidate_strategy(candidate_artifact, baseline_strategy)

        result = evaluate_on_events(candidate, baseline_strategy, search_events)
        guardrails = evaluate_guardrails(
            result.summary_metrics, result.baseline_summary_metrics
        )
        score = result.summary_metrics.get("weighted_roi_pct", 0.0)
        n_bets = int(result.summary_metrics.get("total_bets", 0) or 0)

        # Primary floor: report-only below the sample floor.
        report_only = n_bets < 300
        keep = (not report_only) and guardrails.get("passed", False)

        row: dict[str, Any] = {
            "source": "agent",
            "kind": "trial",
            "tier": "fast",
            "window": "search_13",
            "git_commit": _git_head(),
            "eval_contract_version": EVAL_CONTRACT_VERSION_WALK_FORWARD,
            "config_hash": candidate_hash,
            "parent_hash": parent_hash,
            "mutation": description,
            "params": candidate_artifact.get("overrides"),
            "metrics": {
                "weighted_roi_pct": score,
                "total_bets": n_bets,
                "weighted_clv_avg": result.summary_metrics.get("weighted_clv_avg"),
                "weighted_calibration_error": result.summary_metrics.get("weighted_calibration_error"),
                "blended_score": compute_blended_score(result.summary_metrics, guardrails),
            },
            "guardrails_passed": bool(guardrails.get("passed")),
            "report_only": report_only,
            "decision": ("keep" if keep else "discard") if not report_only else "report_only",
            "duration_hint_ms": 0,
            **evaluator_identity(),
        }
        append_ledger_row(row)
        summary["trials"].append({"hash": candidate_hash, "decision": row["decision"]})

        if keep:
            summary["keeps"] += 1
            confirmation = evaluate_on_events(candidate, baseline_strategy, confirmation_events)
            conf_guardrails = evaluate_guardrails(
                confirmation.summary_metrics, confirmation.baseline_summary_metrics
            )
            conf_n = int(confirmation.summary_metrics.get("total_bets", 0) or 0)
            confirmed = bool(conf_guardrails.get("passed")) and conf_n >= MIN_CONFIRMATION_BETS

            append_ledger_row({
                "source": "agent",
                "kind": "confirmation",
                "window": "confirmation_3",
                "git_commit": _git_head(),
                "config_hash": candidate_hash,
                "parent_hash": parent_hash,
                "mutation": description,
                "metrics": {
                    "weighted_roi_pct": confirmation.summary_metrics.get("weighted_roi_pct"),
                    "total_bets": conf_n,
                },
                "guardrails_passed": bool(conf_guardrails.get("passed")),
                "decision": "confirm_pass" if confirmed else "confirm_fail",
                **evaluator_identity(),
            })

            if confirmed:
                summary["staged_promotions"] += 1
                if best_keep is None or score > best_keep[0]:
                    best_keep = (score, candidate_artifact, description, candidate_hash)

                dossier_path = stage_promotion_ready_dossier(
                    candidate_artifact=candidate_artifact,
                    parent_artifact=artifact,
                    candidate_hash=candidate_hash,
                    search_summary=result.summary_metrics,
                    confirmation_summary=confirmation.summary_metrics,
                    trials_run=trial_index + 1,
                )
                append_ledger_row({
                    "source": "agent",
                    "kind": "promotion_ready",
                    "config_hash": candidate_hash,
                    "dossier_path": str(dossier_path),
                    **evaluator_identity(),
                })
                if alert_fn:
                    alert_fn(
                        "Autoresearch: PROMOTION-READY candidate found.\n"
                        f"Mutation: {description}\n"
                        f"Search ROI {score:.2f}% on {n_bets} bets; "
                        f"confirmation passed ({conf_n} bets).\n"
                        f"Dossier: {dossier_path}\n"
                        "Review and promote from the dashboard when ready."
                    )
        else:
            summary["discards"] += 1

    summary["verdict"] = (
        "staged_for_review" if summary["staged_promotions"] else "no_promotable_candidate"
    )
    return summary


def build_candidate_strategy(artifact: dict[str, Any], baseline: StrategyConfig) -> StrategyConfig:
    from backtester.strategy_config_artifact import build_strategy_from_artifact

    return build_strategy_from_artifact(artifact, baseline)


def stage_promotion_ready_dossier(
    *,
    candidate_artifact: dict[str, Any],
    parent_artifact: dict[str, Any],
    candidate_hash: str,
    search_summary: dict[str, Any],
    confirmation_summary: dict[str, Any],
    trials_run: int,
) -> Path:
    """Write the human-readable promotion-ready dossier; returns its path."""
    DOSSIER_DIR.mkdir(parents=True, exist_ok=True)
    changes = diff_artifacts(parent_artifact, candidate_artifact)
    payload = {
        "status": "PROMOTION_READY (human action required)",
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "config_hash": candidate_hash,
        "changes_vs_champion": changes,
        "search_window": {"events": 13, "summary": _compact(search_summary)},
        "confirmation_window": {"events": 3, "summary": _compact(confirmation_summary)},
        "multiplicity_context": {
            "trials_run_this_lineage": trials_run,
            "caveat": (
                "Best-seen scores inflate with trial counts; this candidate survived "
                "a fresh confirmation window, but treat the edge as provisional until "
                "the sealed holdout is opened."
            ),
        },
        "next_action": "Open the Autoresearch tab -> review diff -> click Promote to Lab.",
        **evaluator_identity(),
    }
    path = DOSSIER_DIR / f"promotion_ready_{candidate_hash}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return path


def _compact(summary: dict[str, Any]) -> dict[str, Any]:
    keys = ("weighted_roi_pct", "unweighted_roi_pct", "total_bets",
            "weighted_clv_avg", "weighted_calibration_error", "max_drawdown_pct")
    return {k: summary.get(k) for k in keys}
