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
from src import config

ELITE_THRESHOLD = 10  # rank <= 10 in newest window counts as "elite"


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

    IMPORTANT: Excludes the "all" window from momentum calculations.
    The "all" window represents a career-level average (hundreds of rounds)
    and is NOT comparable to rolling windows (8, 12, 24 rounds). Comparing
    "all" rank vs "8-round" rank produces misleading momentum signals --
    e.g., Morikawa winning Pebble Beach but showing "cold" because his
    8-round rank (#14) is worse than his career rank (#5).

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
    # Exclude "all" window -- it's a career baseline, not a trend indicator
    windows = [w for w in windows if w != "all"]
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


def _compute_trend(ranks: dict, field_size: int = 150) -> float:
    """
    Compute a trend value from ranks at different windows.

    Positive = improving (recent ranks better than older ranks).
    Negative = declining.

    Uses all available windows, sorted from oldest to newest.

    Key fix: uses PERCENTAGE improvement relative to position rather than
    raw rank change. This prevents penalizing elite players who have
    less room to improve in rank. A player going from #5 → #1 is a 
    significant improvement just like #80 → #40.
    """
    # Sort windows from oldest (largest) to newest (smallest)
    sorted_windows = sorted(ranks.keys(), key=_window_sort_key, reverse=True)
    available = [(w, ranks[w]) for w in sorted_windows]

    if len(available) < 2:
        return 0.0

    # Primary trend: oldest available vs most recent
    oldest_rank = available[0][1]
    newest_rank = available[-1][1]

    # Use percentage-based improvement to avoid penalizing elite players.
    # Going from rank 5→1 is an 80% improvement, same as 50→10.
    # This fixes the problem where a top player who wins still shows "cold"
    # because their raw rank change is small.
    # Clamped to [-1, 1] to prevent asymmetric extremes (e.g., rank 3→15
    # would be -400% unclamped, but we cap decline at -100%).
    if oldest_rank > 0:
        pct_improvement = max(-1.0, min(1.0, (oldest_rank - newest_rank) / oldest_rank))
    else:
        pct_improvement = 0.0

    # Also factor in absolute position: being ranked highly in the
    # most recent window is itself a positive signal.
    # A player ranked #3 in the newest window gets a small positive boost.
    if field_size > 1:
        position_signal = (field_size - newest_rank) / (field_size - 1)
    else:
        position_signal = 0.5

    # Combine: directional trend + current position strength
    # For elite players (top 10), increase position weight since
    # sustained excellence is a stronger signal than small rank changes.
    is_elite = newest_rank <= ELITE_THRESHOLD
    pos_weight = 0.50 if is_elite else 0.40
    trend_weight = 1.0 - pos_weight

    # The position_signal is centered at 0.5 for a mid-field player,
    # so we shift it to be centered at 0 for blending.
    return (trend_weight * pct_improvement * 100.0
            + pos_weight * (position_signal - 0.5) * 100.0)


def compute_momentum(tournament_id: int, weights: dict, elite_players: set = None) -> dict:
    """
    Compute momentum score for every player.
    When config.MOMENTUM_ENABLED is False (kill switch), returns neutral 50 for all.

    Returns: {player_key: {"score": float, "trend": float, "direction": str,
                           "windows": dict, "windows_count": int}}
    """
    if not config.MOMENTUM_ENABLED:
        return {}

    player_windows = _get_ranks_across_windows(tournament_id)

    if not player_windows:
        return {}

    # Determine field size for percentage-based calculations
    field_size = len(player_windows)

    # Compute raw trends
    trends = {}
    for pk, ranks in player_windows.items():
        trends[pk] = {
            "raw_trend": _compute_trend(ranks, field_size=field_size),
            "windows": ranks,
            "windows_count": len(ranks),
        }

    # Normalize trends to 0-100 scale
    all_trends = [t["raw_trend"] for t in trends.values()]
    if not all_trends:
        return {}

    max_trend = max(abs(t) for t in all_trends) if all_trends else 1.0
    if max_trend == 0:
        max_trend = 1.0

    results = {}
    for pk, t in trends.items():
        raw = t["raw_trend"]
        # Scale: 0 trend -> 50, max positive -> ~70, max negative -> ~30
        score = 50.0 + (raw / max_trend) * 20.0
        score = max(30.0, min(70.0, score))

        # More confidence if we have more windows
        confidence = min(1.0, t["windows_count"] / 4.0)
        # Pull toward 50 if low confidence
        score = 50.0 + confidence * (score - 50.0)

        # Elite floor: top DG-skill players shouldn't crater on momentum
        if elite_players and pk in elite_players:
            score = max(35.0, score)

        # Direction uses relative thresholds based on field trends
        # This prevents labeling moderate trends as "cold" in a field
        # with extreme outliers
        relative = raw / max_trend if max_trend > 0 else 0
        if relative > 0.25:
            direction = "hot"
        elif relative > 0.05:
            direction = "warming"
        elif relative > -0.25:
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
