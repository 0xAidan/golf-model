"""
Unified entry for dashboard / API autoresearch cycles.

Primary evaluation: weighted walk-forward + replay_event (see research_cycle).
Checkpoint / pilot contract evaluation is a separate holdout path (CLI scripts).
"""

from __future__ import annotations

from typing import Any

from backtester.research_cycle import run_research_cycle


def run_cycle(
    *,
    max_candidates: int = 5,
    years: list[int] | None = None,
    source: str = "manual",
    scope: str = "global",
    output_dir: str | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """Run one bounded research cycle; adds evaluation metadata for operators."""
    result = run_research_cycle(
        max_candidates=max_candidates,
        years=years,
        source=source,
        scope=scope,
        output_dir=output_dir,
        seed=seed,
    )
    result["evaluation_mode"] = "weighted_walk_forward"
    result["holdout_eval_note"] = (
        "Pilot checkpoint / immutable eval: scripts/run_autoresearch_eval.py "
        "(see docs/autoresearch/pilot_contract.json). Not merged into this cycle score."
    )
    return result
