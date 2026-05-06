"""Lab-only data integrity diagnostics (v5 research lane).

Non-blocking by default: callers attach warnings to run results.
"""

from __future__ import annotations

from typing import Any

from src import config
from src import db


def evaluate_lab_data_integrity(tournament_id: int) -> dict[str, Any]:
    """
    Run lightweight checks before trusting model outputs for experiments.

    Does not abort pipeline — surfaces warnings for dashboards / logs.
    """
    warnings: list[str] = []
    conn = db.get_conn()
    try:
        mcount = conn.execute(
            "SELECT COUNT(*) AS c FROM metrics WHERE tournament_id = ?",
            (tournament_id,),
        ).fetchone()["c"]
        sg_recent = conn.execute(
            """
            SELECT COUNT(*) AS c FROM metrics
            WHERE tournament_id = ?
              AND data_mode = 'recent_form'
              AND metric_category = 'strokes_gained'
            """,
            (tournament_id,),
        ).fetchone()["c"]
        dg_skill = conn.execute(
            """
            SELECT COUNT(*) AS c FROM metrics
            WHERE tournament_id = ?
              AND metric_category = 'dg_skill'
            """,
            (tournament_id,),
        ).fetchone()["c"]
    finally:
        conn.close()

    if mcount < 50:
        warnings.append(f"Low metric row count ({mcount}) for tournament {tournament_id}.")
    if sg_recent < 10:
        warnings.append(f"Thin recent_form strokes_gained coverage ({sg_recent} rows).")
    if dg_skill < 10:
        warnings.append(f"Thin dg_skill coverage ({dg_skill} rows).")

    ok = not warnings
    status = "ok" if ok else "warn"
    return {
        "status": status,
        "tournament_id": tournament_id,
        "metric_rows": int(mcount),
        "recent_sg_rows": int(sg_recent),
        "dg_skill_rows": int(dg_skill),
        "field_size_bounds": {
            "min": config.FIELD_SIZE_MIN,
            "max": config.FIELD_SIZE_MAX,
        },
        "warnings": warnings,
        "summary": "Lab data integrity checks passed."
        if ok
        else "Lab data integrity checks reported warnings — review before trusting experiments.",
    }
