"""
Fit per-player SG volatility from the `rounds` table (offline / shadow use only).

Used by shadow Monte Carlo v2 to scale idiosyncratic noise per player.
"""

from __future__ import annotations

import math
from typing import Any

from src import db as db_mod


def fit_player_round_sg(
    player_keys: list[str],
    *,
    lookback_rounds: int = 40,
    min_rounds_for_sd: int = 2,
    default_sd: float = 2.5,
    min_sd: float = 0.6,
) -> dict[str, dict[str, Any]]:
    """
    For each normalized player_key, return recent-round SG stats from `rounds`.

    Returns:
      { pk: {"n": int, "mean_sg": float|None, "sd_sg": float, "source": "rounds"|"default"} }
    """
    keys = [str(k).strip().lower() for k in player_keys if str(k).strip()]
    if not keys:
        return {}

    conn = db_mod.get_conn()
    placeholders = ",".join("?" * len(keys))
    rows = conn.execute(
        f"""SELECT player_key, sg_total, event_completed, round_num
            FROM rounds
            WHERE player_key IN ({placeholders}) AND sg_total IS NOT NULL
            ORDER BY player_key, event_completed DESC, round_num DESC""",
        keys,
    ).fetchall()
    conn.close()

    by_pk: dict[str, list[float]] = {k: [] for k in keys}
    for r in rows:
        pk = str(r["player_key"] or "").strip().lower()
        if pk not in by_pk:
            continue
        if len(by_pk[pk]) >= lookback_rounds:
            continue
        try:
            by_pk[pk].append(float(r["sg_total"]))
        except (TypeError, ValueError):
            continue

    out: dict[str, dict[str, Any]] = {}
    for pk in keys:
        vals = by_pk.get(pk) or []
        n = len(vals)
        if n >= min_rounds_for_sd:
            mean_sg = sum(vals) / n
            var = sum((x - mean_sg) ** 2 for x in vals) / (n - 1)
            sd = max(min_sd, math.sqrt(max(var, 1e-12)))
            out[pk] = {"n": n, "mean_sg": round(mean_sg, 4), "sd_sg": round(sd, 4), "source": "rounds"}
        else:
            out[pk] = {"n": n, "mean_sg": None, "sd_sg": default_sd, "source": "default"}
    return out
