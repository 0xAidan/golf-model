"""
Momentum Score

Measures whether a player is trending up or down by comparing
their performance across different time windows.

Key insight from the WM Phoenix chat:
  - Sahith Theegala: 16r rank jumped from #81 to #17 (+64 trend) = BUY
  - Jordan Spieth: -41 trend = CAUTION
  - Tony Finau: hot at L4 but cold at L8/L20 = TRAP

Inputs:
  - SG:TOT (or composite SG) ranks across windows: all, 50, 36, 24, 16, 12, 8
  - Rolling averages if available (L4, L8, L20, L50)

Output: per-player momentum_score (0-100, >50 = improving, <50 = declining)
"""

from src import db


def _get_ranks_across_windows(tournament_id: int) -> dict:
    """
    For each player, get their SG:TOT rank at each available round window.
    Returns: {player_key: {window: rank}}
    """
    windows = ["all", "50", "36", "24", "20", "16", "12", "8"]
    player_windows = {}

    for w in windows:
        metrics = db.get_metrics_by_category(
            tournament_id, "strokes_gained",
            data_mode="recent_form", round_window=w,
        )
        for m in metrics:
            if m["metric_name"] == "SG:TOT" and m["metric_value"] is not None:
                pk = m["player_key"]
                if pk not in player_windows:
                    player_windows[pk] = {}
                player_windows[pk][w] = m["metric_value"]

    return player_windows


def _compute_trend(ranks: dict) -> float:
    """
    Compute a trend value from ranks at different windows.

    Positive = improving (recent ranks better than older ranks).
    Negative = declining.

    We compare the most recent window to the oldest available.
    Also check intermediate points to detect false trends.

    Returns a raw trend value (higher = more improvement).
    """
    # Order windows from oldest to newest
    window_order = ["all", "50", "36", "24", "20", "16", "12", "8"]
    available = [(w, ranks[w]) for w in window_order if w in ranks]

    if len(available) < 2:
        return 0.0  # Not enough data to compute trend

    # Primary trend: oldest available vs most recent
    oldest_rank = available[0][1]
    newest_rank = available[-1][1]
    primary_trend = oldest_rank - newest_rank  # positive = improving

    # Secondary: check if trend is consistent or just noise
    # Look at the middle point
    if len(available) >= 3:
        mid_idx = len(available) // 2
        mid_rank = available[mid_idx][1]
        # Consistent trend: all three points should show progression
        trend_first_half = oldest_rank - mid_rank
        trend_second_half = mid_rank - newest_rank
        # If both halves agree on direction, more confident
        if (trend_first_half > 0 and trend_second_half > 0):
            # Consistent improvement
            consistency_bonus = 0.2
        elif (trend_first_half < 0 and trend_second_half < 0):
            # Consistent decline
            consistency_bonus = 0.2
        else:
            # Mixed signal (like Finau: hot recently but was cold)
            consistency_bonus = -0.1
    else:
        consistency_bonus = 0.0

    return primary_trend * (1.0 + consistency_bonus)


def compute_momentum(tournament_id: int, weights: dict) -> dict:
    """
    Compute momentum score for every player.

    Returns: {player_key: {"score": float, "trend": float, "direction": str, "windows": dict}}
    """
    player_windows = _get_ranks_across_windows(tournament_id)

    if not player_windows:
        return {}

    # Compute raw trends
    trends = {}
    for pk, ranks in player_windows.items():
        trends[pk] = {
            "raw_trend": _compute_trend(ranks),
            "windows": ranks,
        }

    # Normalize trends to 0-100 scale
    all_trends = [t["raw_trend"] for t in trends.values()]
    if not all_trends:
        return {}

    max_trend = max(abs(t) for t in all_trends) or 1.0

    results = {}
    for pk, t in trends.items():
        raw = t["raw_trend"]
        # Scale: 0 trend → 50, max positive → ~90, max negative → ~10
        score = 50.0 + (raw / max_trend) * 40.0
        score = max(5.0, min(95.0, score))

        if raw > 5:
            direction = "hot"
        elif raw > 0:
            direction = "warming"
        elif raw > -5:
            direction = "cooling"
        else:
            direction = "cold"

        results[pk] = {
            "score": round(score, 2),
            "trend": round(raw, 1),
            "direction": direction,
            "windows": t["windows"],
        }

    return results
