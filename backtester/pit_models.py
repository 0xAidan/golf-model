"""
PIT-Compatible Sub-Model Scoring

Mirrors the live model's course_fit, form, and momentum sub-models
but reads exclusively from PIT (point-in-time) tables. This ensures
the backtester validates the SAME model structure that runs live,
using only data that would have been available before each event.

Key differences from live models:
- No DG decomposition, DG skill, or sim probabilities (external data)
- Ranks computed from PIT SG values within each event's field
- Course-specific data from pit_course_stats table
"""

import logging
from src import db

logger = logging.getLogger("pit_models")

# Windows aligned with live model discovery
WINDOWS = [8, 12, 16, 20, 24, 50]


# ═══════════════════════════════════════════════════════════════════
#  Shared Helpers
# ═══════════════════════════════════════════════════════════════════

def _rank_to_score(rank: float | None, field_size: int) -> float:
    """Convert a rank (1 = best) to a 0-100 score. Rank 1 -> 100, last -> 0."""
    if rank is None or field_size <= 1:
        return 50.0
    rank = max(1, min(rank, field_size))
    return 100.0 * (1.0 - (rank - 1) / (field_size - 1))


def _rounds_confidence(rounds_played: int, max_rounds: float = 30.0) -> float:
    """
    Trust factor for course history.
    More rounds at the course = higher confidence.
    Returns 0.3 (min) to 1.0 (max at 30+ rounds).
    """
    if rounds_played is None or rounds_played <= 0:
        return 0.3
    return min(1.0, 0.3 + 0.7 * (rounds_played / max_rounds))


def _sample_size_confidence(rounds_used: int, threshold: int = 8) -> float:
    """
    Bayesian-style shrinkage factor based on available sample.
    At threshold rounds or more, full confidence (1.0).
    Below threshold, proportionally shrink toward neutral.
    """
    if rounds_used is None or rounds_used <= 0:
        return 0.0
    return min(1.0, rounds_used / threshold)


# ═══════════════════════════════════════════════════════════════════
#  PIT Form Score
# ═══════════════════════════════════════════════════════════════════

def compute_pit_form(event_id: str, year: int) -> dict:
    """
    Compute form scores for all players in the event using PIT stats.

    Mirrors the live form model logic:
    - Recent windows (<=20 rounds): weighted by recency
    - Baseline windows (>20 rounds): simple average
    - Multi-SG component: weighted blend of SG categories
    - Sample size adjustment: shrink scores toward 50 for small samples

    Returns: {player_key: {"score": float, "components": dict}}
    """
    conn = db.get_conn()

    # Load all PIT stats for this event across all windows
    rows = conn.execute("""
        SELECT player_key, window, sg_total, sg_ott, sg_app, sg_arg,
               sg_putt, sg_t2g, rounds_used, sg_total_rank
        FROM pit_rolling_stats
        WHERE event_id = ? AND year = ?
          AND sg_total IS NOT NULL
        ORDER BY window ASC
    """, (str(event_id), year)).fetchall()

    if not rows:
        return {}

    # Organize by window -> {player_key: {stats}}
    by_window = {}
    all_players = set()
    for r in rows:
        pkey, window, sg_tot, sg_ott, sg_app, sg_arg, sg_putt, sg_t2g, rounds_used, rank = r
        all_players.add(pkey)
        if window not in by_window:
            by_window[window] = {}
        by_window[window][pkey] = {
            "sg_total": sg_tot, "sg_ott": sg_ott, "sg_app": sg_app,
            "sg_arg": sg_arg, "sg_putt": sg_putt, "sg_t2g": sg_t2g,
            "rounds_used": rounds_used, "sg_total_rank": rank,
        }

    # Classify windows
    recent_windows = sorted([w for w in by_window if w <= 20])
    baseline_windows = sorted([w for w in by_window if w > 20], reverse=True)

    # Field sizes per window
    field_sizes = {w: len(players) for w, players in by_window.items()}

    # Weights (matching live model defaults, minus sim/DG which aren't available)
    # Live model: recent=0.45, baseline=0.30, sim=0.25 (of non-sim portion)
    # Without sim, redistribute: recent=0.55, baseline=0.35, multi_sg=0.10
    w_recent = 0.55
    w_baseline = 0.35
    w_multi_sg = 0.10

    results = {}
    for pk in all_players:
        components = {}

        # -- Recent window scores (weighted by recency) --
        recent_scores = []
        for w in recent_windows:
            if w in by_window and pk in by_window[w]:
                stats = by_window[w][pk]
                rank = stats["sg_total_rank"]
                fs = field_sizes[w]
                raw_score = _rank_to_score(rank, fs)
                # Sample size adjustment
                conf = _sample_size_confidence(stats["rounds_used"])
                adjusted = 50.0 + conf * (raw_score - 50.0)
                recent_scores.append((w, adjusted))

        if recent_scores:
            n = len(recent_scores)
            total_w = sum(range(1, n + 1))
            recent_score = sum(
                score * (n - i) / total_w
                for i, (_, score) in enumerate(recent_scores)
            )
        else:
            recent_score = 50.0
        components["recent"] = round(recent_score, 2)

        # -- Baseline window scores --
        baseline_scores = []
        for w in baseline_windows:
            if w in by_window and pk in by_window[w]:
                stats = by_window[w][pk]
                rank = stats["sg_total_rank"]
                fs = field_sizes[w]
                raw_score = _rank_to_score(rank, fs)
                conf = _sample_size_confidence(stats["rounds_used"])
                adjusted = 50.0 + conf * (raw_score - 50.0)
                baseline_scores.append((w, adjusted))

        if baseline_scores:
            baseline_score = sum(s for _, s in baseline_scores) / len(baseline_scores)
        else:
            baseline_score = 50.0
        components["baseline"] = round(baseline_score, 2)

        # -- Multi-SG component (from best recent window) --
        # Weighted: SG:TOT 40%, SG:APP 25%, SG:OTT 15%, SG:Putt 10%, SG:ARG 10%
        best_stats = None
        for w in recent_windows + baseline_windows:
            if w in by_window and pk in by_window[w]:
                best_stats = by_window[w][pk]
                best_fs = field_sizes[w]
                break

        if best_stats:
            # Rank each SG category within the field for this window
            # Use raw values since we only have sg_total_rank pre-computed
            # For multi-SG, compute inline ranks for each category
            best_w = recent_windows[0] if recent_windows else baseline_windows[0]
            if best_w in by_window and pk in by_window[best_w]:
                sg_scores = _compute_multi_sg_scores(by_window[best_w], pk, field_sizes[best_w])
                multi_sg = (
                    0.40 * sg_scores["tot"]
                    + 0.25 * sg_scores["app"]
                    + 0.15 * sg_scores["ott"]
                    + 0.10 * sg_scores["putt"]
                    + 0.10 * sg_scores["arg"]
                )
            else:
                multi_sg = 50.0
        else:
            multi_sg = 50.0
        components["multi_sg"] = round(multi_sg, 2)

        # -- Final form score --
        form_score = (
            w_recent * components["recent"]
            + w_baseline * components["baseline"]
            + w_multi_sg * components["multi_sg"]
        )
        form_score = max(0.0, min(100.0, form_score))

        results[pk] = {
            "score": round(form_score, 2),
            "components": components,
        }

    return results


def _compute_multi_sg_scores(window_data: dict, player_key: str,
                             field_size: int) -> dict:
    """
    Compute per-category SG scores by ranking players within the field
    for a specific window.
    """
    categories = ["sg_total", "sg_ott", "sg_app", "sg_arg", "sg_putt"]
    cat_labels = {"sg_total": "tot", "sg_ott": "ott", "sg_app": "app",
                  "sg_arg": "arg", "sg_putt": "putt"}
    result = {v: 50.0 for v in cat_labels.values()}

    for cat, label in cat_labels.items():
        # Collect all players' values for this category
        vals = []
        for pk, stats in window_data.items():
            v = stats.get(cat)
            if v is not None:
                vals.append((pk, v))

        if not vals:
            continue

        # Sort descending (best first) and find rank
        vals.sort(key=lambda x: x[1], reverse=True)
        fs = len(vals)
        for rank, (pk, _) in enumerate(vals, start=1):
            if pk == player_key:
                result[label] = _rank_to_score(rank, fs)
                break

    return result


# ═══════════════════════════════════════════════════════════════════
#  PIT Course Fit Score
# ═══════════════════════════════════════════════════════════════════

def compute_pit_course_fit(event_id: str, year: int) -> dict:
    """
    Compute course fit scores for all players in the event using PIT data.

    Mirrors the live course_fit model logic:
    - Course-specific SG averages ranked within the field
    - Confidence scaling based on rounds played at the course
    - Finish position history as a bonus signal

    Returns: {player_key: {"score": float, "confidence": float, "rounds": int, "components": dict}}
    """
    conn = db.get_conn()

    # Load course-specific PIT stats
    rows = conn.execute("""
        SELECT player_key, sg_total, sg_ott, sg_app, sg_arg, sg_putt,
               rounds_played, avg_finish, best_finish
        FROM pit_course_stats
        WHERE event_id = ? AND year = ?
    """, (str(event_id), year)).fetchall()

    if not rows:
        return {}

    # Build lookup
    player_data = {}
    for r in rows:
        pk = r[0]
        player_data[pk] = {
            "sg_total": r[1], "sg_ott": r[2], "sg_app": r[3],
            "sg_arg": r[4], "sg_putt": r[5],
            "rounds_played": r[6] or 0,
            "avg_finish": r[7], "best_finish": r[8],
        }

    field_size = len(player_data)
    if field_size == 0:
        return {}

    # Compute ranks for each SG category within the field
    cat_ranks = {}
    for cat in ["sg_total", "sg_ott", "sg_app", "sg_arg", "sg_putt"]:
        vals = [(pk, d[cat]) for pk, d in player_data.items() if d[cat] is not None]
        vals.sort(key=lambda x: x[1], reverse=True)
        cat_ranks[cat] = {pk: rank for rank, (pk, _) in enumerate(vals, start=1)}

    # Finish position ranking (lower avg_finish = better)
    finish_vals = [(pk, d["avg_finish"]) for pk, d in player_data.items()
                   if d["avg_finish"] is not None]
    finish_vals.sort(key=lambda x: x[1])  # lower is better
    finish_ranks = {pk: rank for rank, (pk, _) in enumerate(finish_vals, start=1)}

    # Weights: SG:TOT 35%, SG:APP 20%, SG:OTT 15%, SG:Putt 10%, SG:ARG 5%, Finish 15%
    w_sg_tot = 0.35
    w_sg_app = 0.20
    w_sg_ott = 0.15
    w_sg_putt = 0.10
    w_sg_arg = 0.05
    w_finish = 0.15

    results = {}
    for pk, data in player_data.items():
        components = {}

        # SG rank scores
        for cat, weight_name in [("sg_total", "sg_tot"), ("sg_app", "sg_app"),
                                  ("sg_ott", "sg_ott"), ("sg_putt", "sg_putt"),
                                  ("sg_arg", "sg_arg")]:
            rank = cat_ranks.get(cat, {}).get(pk)
            fs = len(cat_ranks.get(cat, {}))
            components[weight_name] = _rank_to_score(rank, fs) if rank else 50.0

        # Finish position score
        finish_rank = finish_ranks.get(pk)
        finish_fs = len(finish_ranks)
        components["finish"] = _rank_to_score(finish_rank, finish_fs) if finish_rank else 50.0

        # Weighted composite
        score = (
            w_sg_tot * components["sg_tot"]
            + w_sg_app * components["sg_app"]
            + w_sg_ott * components["sg_ott"]
            + w_sg_putt * components["sg_putt"]
            + w_sg_arg * components["sg_arg"]
            + w_finish * components["finish"]
        )

        # Apply confidence scaling (shrink toward 50 for few course rounds)
        rounds_played = data["rounds_played"]
        confidence = _rounds_confidence(rounds_played)
        score = 50.0 + confidence * (score - 50.0)

        results[pk] = {
            "score": round(score, 2),
            "confidence": round(confidence, 2),
            "rounds": rounds_played,
            "components": {k: round(v, 2) for k, v in components.items()},
        }

    return results


# ═══════════════════════════════════════════════════════════════════
#  PIT Momentum Score
# ═══════════════════════════════════════════════════════════════════

def compute_pit_momentum(event_id: str, year: int) -> dict:
    """
    Compute momentum scores for all players in the event using PIT data.

    Mirrors the live momentum model logic:
    - Compares ranks across windows (oldest vs newest)
    - Uses percentage-based improvement to avoid penalizing elite players
    - Elite stability bonus for players maintaining top rank
    - Position signal for absolute strength

    Returns: {player_key: {"score": float, "direction": str, "trend": float}}
    """
    conn = db.get_conn()

    # Load all PIT stats with ranks for this event
    rows = conn.execute("""
        SELECT player_key, window, sg_total_rank, rounds_used
        FROM pit_rolling_stats
        WHERE event_id = ? AND year = ?
          AND sg_total_rank IS NOT NULL
        ORDER BY window ASC
    """, (str(event_id), year)).fetchall()

    if not rows:
        return {}

    # Organize: {player_key: {window: rank}}
    player_windows = {}
    all_players = set()
    for r in rows:
        pk, window, rank, rounds_used = r
        all_players.add(pk)
        if pk not in player_windows:
            player_windows[pk] = {}
        player_windows[pk][window] = rank

    # Get field sizes per window for normalization
    field_sizes = {}
    for r in rows:
        w = r[1]
        if w not in field_sizes:
            field_sizes[w] = 0
        field_sizes[w] = max(field_sizes[w], r[2])  # max rank = field size

    # More accurate field size: count distinct players per window
    for w in field_sizes:
        count = sum(1 for pk in player_windows if w in player_windows[pk])
        field_sizes[w] = count

    results = {}
    raw_trends = {}

    for pk in all_players:
        ranks = player_windows.get(pk, {})
        if len(ranks) < 2:
            results[pk] = {"score": 50.0, "direction": "unknown", "trend": 0.0}
            raw_trends[pk] = 0.0
            continue

        # Sort from oldest (largest window) to newest (smallest window)
        sorted_windows = sorted(ranks.keys(), reverse=True)
        available = [(w, ranks[w]) for w in sorted_windows]

        oldest_rank = available[0][1]
        newest_rank = available[-1][1]
        field_size = field_sizes.get(available[-1][0], 150)

        # Percentage-based improvement (matching live model)
        if oldest_rank > 0:
            pct_improvement = max(-1.0, min(1.0, (oldest_rank - newest_rank) / oldest_rank))
        else:
            pct_improvement = 0.0

        # Elite stability bonus (matching the improvement we're adding to live model)
        ELITE_THRESHOLD = 10
        if newest_rank <= ELITE_THRESHOLD and oldest_rank <= ELITE_THRESHOLD:
            stability_bonus = 0.3 * (1.0 - (newest_rank - 1) / ELITE_THRESHOLD)
            pct_improvement = max(pct_improvement, stability_bonus)

        # Position signal
        if field_size > 1:
            position_signal = (field_size - newest_rank) / (field_size - 1)
        else:
            position_signal = 0.5

        # Blend: 60% directional, 40% current position (50% for elite)
        is_elite = newest_rank <= ELITE_THRESHOLD
        pos_weight = 0.50 if is_elite else 0.40
        trend_weight = 1.0 - pos_weight

        raw = (trend_weight * pct_improvement * 100.0
               + pos_weight * (position_signal - 0.5) * 100.0)

        # Consistency bonus/penalty across intermediate windows
        if len(available) >= 3:
            improving_pairs = 0
            declining_pairs = 0
            for i in range(len(available) - 1):
                if available[i][1] > available[i + 1][1]:
                    improving_pairs += 1
                elif available[i][1] < available[i + 1][1]:
                    declining_pairs += 1

            total_pairs = improving_pairs + declining_pairs
            if total_pairs > 0:
                consistency = (improving_pairs - declining_pairs) / total_pairs
                raw += consistency * 10.0

        raw_trends[pk] = raw

    # Normalize to 0-100 scale
    if raw_trends:
        all_raw = list(raw_trends.values())
        max_abs = max(abs(v) for v in all_raw) if all_raw else 1.0
        if max_abs == 0:
            max_abs = 1.0

        for pk in all_players:
            raw = raw_trends.get(pk, 0.0)
            normalized = 50.0 + 50.0 * (raw / max_abs)
            normalized = max(0.0, min(100.0, normalized))

            # Direction classification
            relative = raw / max_abs if max_abs > 0 else 0
            if relative > 0.25:
                direction = "hot"
            elif relative > 0.05:
                direction = "warming"
            elif relative > -0.25:
                direction = "cooling"
            else:
                direction = "cold"

            results[pk] = {
                "score": round(normalized, 2),
                "direction": direction,
                "trend": round(raw, 2),
            }

    return results


# ═══════════════════════════════════════════════════════════════════
#  PIT Composite Score
# ═══════════════════════════════════════════════════════════════════

def compute_pit_composite(event_id: str, year: int,
                          w_course_fit: float = 0.40,
                          w_form: float = 0.40,
                          w_momentum: float = 0.20) -> dict:
    """
    Compute composite scores using PIT sub-models, mirroring the live
    composite model's structure (course_fit + form + momentum).

    Returns: {player_key: {"composite": float, "course_fit": float,
                           "form": float, "momentum": float, ...}}
    """
    form_scores = compute_pit_form(event_id, year)
    course_scores = compute_pit_course_fit(event_id, year)
    momentum_scores = compute_pit_momentum(event_id, year)

    # Collect all players
    all_players = set()
    all_players.update(form_scores.keys())
    all_players.update(course_scores.keys())
    all_players.update(momentum_scores.keys())

    if not all_players:
        return {}

    # If no course data, redistribute weight
    has_course_data = bool(course_scores)
    if not has_course_data:
        w_form_adj = w_form + w_course_fit * 0.7
        w_momentum_adj = w_momentum + w_course_fit * 0.3
        w_course_adj = 0.0
    else:
        w_course_adj = w_course_fit
        w_form_adj = w_form
        w_momentum_adj = w_momentum

    results = {}
    for pk in all_players:
        cs = course_scores.get(pk, {})
        fs = form_scores.get(pk, {})
        ms = momentum_scores.get(pk, {})

        course_score = cs.get("score", 50.0)
        form_score = fs.get("score", 50.0)
        momentum_score = ms.get("score", 50.0)

        composite = (
            w_course_adj * course_score
            + w_form_adj * form_score
            + w_momentum_adj * momentum_score
        )
        composite = max(0.0, min(100.0, composite))

        results[pk] = {
            "composite": round(composite, 2),
            "course_fit": round(course_score, 2),
            "form": round(form_score, 2),
            "momentum": round(momentum_score, 2),
            "momentum_direction": ms.get("direction", "unknown"),
            "course_confidence": cs.get("confidence", 0),
            "course_rounds": cs.get("rounds", 0),
        }

    return results
