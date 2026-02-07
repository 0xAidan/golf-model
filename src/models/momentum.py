"""
Momentum Score

Measures whether a player is trending up or down by comparing
their performance across different time windows.

AUTO-DISCOVERS available windows from whatever data was uploaded.

Key insight from the WM Phoenix chat:
  - Sahith Theegala: 16r rank jumped from #81 to #17 (+64 trend) = BUY
  - Jordan Spieth: -41 trend = CAUTION
  - Tony Finau: hot at L4 but cold at L8/L20 = TRAP

Output: per-player momentum_score (0-100, >50 = improving, <50 = declining)
"""

from src import db


def _window_sort_key(w: str) -> int:
    """Sort windows numerically. 'all' = largest."""
    if w == "all":
        return 9999
    try:
        return int(w)
    except ValueError:
        return 5000


def _get_ranks_across_windows(tournament_id: int) -> dict:
    """
    For each player, get their SG:TOT rank at each available round window.
    AUTO-DISCOVERS windows from the database.
    Returns: {player_key: {window: rank}}
    """
    # Discover all windows with SG data
    conn = db.get_conn()
    window_rows = conn.execute(
        """SELECT DISTINCT round_window FROM metrics
           WHERE tournament_id = ? AND data_mode = 'recent_form'
             AND metric_category = 'strokes_gained'
             AND metric_name = 'SG:TOT'
             AND metric_value IS NOT NULL
             AND round_window IS NOT NULL""",
        (tournament_id,),
    ).fetchall()
    conn.close()

    windows = [r["round_window"] for r in window_rows]
    if not windows:
        return {}

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

    Uses all available windows, sorted from oldest to newest.
    """
    # Sort windows from oldest (largest) to newest (smallest)
    sorted_windows = sorted(ranks.keys(), key=_window_sort_key, reverse=True)
    available = [(w, ranks[w]) for w in sorted_windows]

    if len(available) < 2:
        return 0.0

    # Primary trend: oldest available vs most recent
    oldest_rank = available[0][1]
    newest_rank = available[-1][1]
    primary_trend = oldest_rank - newest_rank  # positive = improving

    # Check consistency across all intermediate points
    if len(available) >= 3:
        # Count how many consecutive pairs show improvement
        improving_pairs = 0
        declining_pairs = 0
        for i in range(len(available) - 1):
            if available[i][1] > available[i + 1][1]:
                improving_pairs += 1
            elif available[i][1] < available[i + 1][1]:
                declining_pairs += 1

        total_pairs = improving_pairs + declining_pairs
        if total_pairs > 0:
            consistency = abs(improving_pairs - declining_pairs) / total_pairs
        else:
            consistency = 0.0

        # Consistent direction gets bonus, mixed gets penalty
        if consistency > 0.6:
            consistency_bonus = 0.3 * consistency
        else:
            consistency_bonus = -0.15
    else:
        consistency_bonus = 0.0

    return primary_trend * (1.0 + consistency_bonus)


def compute_momentum(tournament_id: int, weights: dict) -> dict:
    """
    Compute momentum score for every player.

    Returns: {player_key: {"score": float, "trend": float, "direction": str,
                           "windows": dict, "windows_count": int}}
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
            "windows_count": len(ranks),
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

        # More confidence if we have more windows
        confidence = min(1.0, t["windows_count"] / 4.0)
        # Pull toward 50 if low confidence
        score = 50.0 + confidence * (score - 50.0)

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
            "windows_count": t["windows_count"],
        }

    return results
