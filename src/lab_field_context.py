"""Field strength context for lab / v5 experiments (research-backed normalization).

Produces a compact summary used by form + uncertainty. Does not alter baseline path.
"""

from __future__ import annotations

from typing import Any

from src import db


def compute_field_strength_context(tournament_id: int) -> dict[str, Any]:
    """
    Summarize current-event field strength from DG skill metrics.

    Returns:
      index: ~0 weak .. ~1 strong (heuristic from mean SG:Total)
      field_size: player count with dg_sg_total
      mean_sg: average SG:Total in field (if available)
    """
    metrics = db.get_metrics_by_category(tournament_id, "dg_skill")
    totals: list[float] = []
    for m in metrics:
        if m.get("metric_name") != "dg_sg_total":
            continue
        if m.get("metric_value") is None:
            continue
        try:
            totals.append(float(m["metric_value"]))
        except (TypeError, ValueError):
            continue
    if not totals:
        return {"index": 0.5, "field_size": 0, "mean_sg": None}

    n = len(totals)
    mean_sg = sum(totals) / n
    # Map typical SG total roughly [-2, +3] into [0, 1]
    idx = (mean_sg + 2.0) / 5.0
    idx = max(0.0, min(1.0, idx))
    return {"index": idx, "field_size": n, "mean_sg": round(mean_sg, 4)}
