"""
Course Fit Score

Uses ONLY course-specific data (e.g. TPC Scottsdale 8-year history)
to score how well each player fits this particular course.

Inputs (from metrics table where data_mode = 'course_specific'):
  - SG:TOT rank (or value)
  - SG:OTT rank
  - SG:APP rank
  - SG:ARG rank
  - SG:P (putting) rank
  - Par 3/4/5 efficiency ranks
  - Finish position history
  - Rounds played (more rounds = more signal)

Output: per-player course_fit_score (0-100, higher = better fit)
"""

from src import db
from src.course_profile import load_course_profile, course_to_model_weights


def _rank_to_score(rank: float, field_size: int) -> float:
    """
    Convert a rank (1 = best) to a 0-100 score.
    Rank 1 → 100, last place → 0.
    """
    if rank is None or field_size <= 1:
        return 50.0  # neutral if no data
    # Clamp
    rank = max(1, min(rank, field_size))
    return 100.0 * (1.0 - (rank - 1) / (field_size - 1))


def _rounds_confidence(rounds_played: float, max_rounds: float = 30.0) -> float:
    """
    How much to trust this player's course history.
    More rounds at the course = more confidence in the signal.
    Returns 0.3 (min, very few rounds) to 1.0 (many rounds).
    """
    if rounds_played is None or rounds_played <= 0:
        return 0.3
    return min(1.0, 0.3 + 0.7 * (rounds_played / max_rounds))


def compute_course_fit(tournament_id: int, weights: dict,
                       course_name: str = None) -> dict:
    """
    Compute course fit score for every player in the tournament.

    If a course profile exists (from screenshots), uses its skill difficulty
    ratings to adjust which SG categories matter more at this course.

    Returns: {player_key: {"score": float, "components": dict, "confidence": float}}
    """
    # Pull all course-specific metrics
    course_metrics = db.get_metrics_by_category(
        tournament_id, "strokes_gained", data_mode="course_specific"
    )
    # Also pull course-specific OTT, approach, etc.
    for cat in ["ott", "approach", "putting", "around_green",
                "par3_efficiency", "par4_efficiency", "par5_efficiency",
                "scoring", "finish"]:
        course_metrics.extend(
            db.get_metrics_by_category(tournament_id, cat, data_mode="course_specific")
        )

    # Also pull DG decomposition data (course-adjusted SG predictions)
    dg_decomp = db.get_metrics_by_category(
        tournament_id, "dg_decomposition", data_mode="course_specific"
    )

    if not course_metrics and not dg_decomp:
        # No course-specific data at all; return empty
        return {}

    # Organize by player
    player_data = {}
    for m in course_metrics:
        pk = m["player_key"]
        if pk not in player_data:
            player_data[pk] = {}
        key = f"{m['metric_category']}_{m['metric_name']}"
        player_data[pk][key] = m["metric_value"]

    # Add DG decomposition data
    player_dg_decomp = {}
    for m in dg_decomp:
        pk = m["player_key"]
        if pk not in player_dg_decomp:
            player_dg_decomp[pk] = {}
        player_dg_decomp[pk][m["metric_name"]] = m["metric_value"]

    # Also get rounds played (meta)
    meta_metrics = db.get_metrics_by_category(
        tournament_id, "meta", data_mode="course_specific"
    )
    for m in meta_metrics:
        pk = m["player_key"]
        if pk not in player_data:
            player_data[pk] = {}
        player_data[pk][f"meta_{m['metric_name']}"] = m["metric_value"]

    # Merge: include players that only appear in DG decomp
    for pk in player_dg_decomp:
        if pk not in player_data:
            player_data[pk] = {}

    field_size = len(player_data)
    if field_size == 0:
        return {}

    # Get base weight values
    w_sg_tot = weights.get("course_sg_tot", 0.30)
    w_sg_app = weights.get("course_sg_app", 0.25)
    w_sg_ott = weights.get("course_sg_ott", 0.20)
    w_sg_putt = weights.get("course_sg_putt", 0.15)
    w_par_eff = weights.get("course_par_eff", 0.10)

    # Apply course profile adjustments if available
    if course_name:
        profile = load_course_profile(course_name)
        if profile:
            adj = course_to_model_weights(profile)
            w_sg_ott *= adj.get("course_sg_ott_mult", 1.0)
            w_sg_app *= adj.get("course_sg_app_mult", 1.0)
            w_sg_putt *= adj.get("course_sg_putt_mult", 1.0)
            # Re-normalize so weights still sum to ~1.0
            total = w_sg_tot + w_sg_app + w_sg_ott + w_sg_putt + w_par_eff
            w_sg_tot /= total
            w_sg_app /= total
            w_sg_ott /= total
            w_sg_putt /= total
            w_par_eff /= total

    results = {}
    for pk, data in player_data.items():
        # Extract ranks (Betsperts rank columns)
        sg_tot_rank = data.get("strokes_gained_SG:TOT")
        sg_ott_rank = data.get("strokes_gained_SG:OTT") or data.get("ott_SG:OTT")
        sg_app_rank = data.get("strokes_gained_SG:APP") or data.get("approach_SG:APP")
        sg_putt_rank = data.get("strokes_gained_SG:P")
        sg_arg_rank = data.get("strokes_gained_SG:ARG")

        # Par efficiency (use ranks if available)
        par5_rank = data.get("par5_efficiency_Par 5 BoB %")
        par4_rank = data.get("par4_efficiency_Par 4 BoB %")
        par3_rank = data.get("par3_efficiency_Par 3 BoB %")

        # Rounds played at this course
        rounds = data.get("meta_rounds_played", 0)
        confidence = _rounds_confidence(rounds)

        # Compute sub-scores
        components = {}
        components["sg_tot"] = _rank_to_score(sg_tot_rank, field_size)
        components["sg_app"] = _rank_to_score(sg_app_rank, field_size)
        components["sg_ott"] = _rank_to_score(sg_ott_rank, field_size)
        components["sg_putt"] = _rank_to_score(sg_putt_rank, field_size)

        # Par efficiency: average of available par efficiency ranks
        par_scores = []
        for pr in [par3_rank, par4_rank, par5_rank]:
            if pr is not None:
                par_scores.append(_rank_to_score(pr, field_size))
        components["par_eff"] = (
            sum(par_scores) / len(par_scores) if par_scores else 50.0
        )

        # Weighted composite
        score = (
            w_sg_tot * components["sg_tot"]
            + w_sg_app * components["sg_app"]
            + w_sg_ott * components["sg_ott"]
            + w_sg_putt * components["sg_putt"]
            + w_par_eff * components["par_eff"]
        )

        # Apply confidence modifier (scales toward 50 if few rounds)
        score = 50.0 + confidence * (score - 50.0)

        # ── Blend with DG decomposition if available ──
        dg_data = player_dg_decomp.get(pk)
        if dg_data:
            # Convert DG decomposition SG values to a 0-100 score
            # by ranking within the field of DG decomposition players
            dg_sg_total = dg_data.get("dg_sg_total")
            if dg_sg_total is not None:
                # Collect all DG totals for ranking
                all_dg_totals = [
                    d.get("dg_sg_total", 0) for d in player_dg_decomp.values()
                    if d.get("dg_sg_total") is not None
                ]
                if all_dg_totals:
                    # Percentile-based score
                    below = sum(1 for v in all_dg_totals if v < dg_sg_total)
                    dg_score = 100.0 * below / max(len(all_dg_totals) - 1, 1)
                    components["dg_decomp"] = round(dg_score, 2)

                    # Blend: if we have course history, DG gets ~30% weight
                    # If no course history (confidence low), DG gets ~70%
                    if confidence >= 0.5:
                        dg_weight = 0.30
                    else:
                        dg_weight = 0.70
                    score = (1 - dg_weight) * score + dg_weight * dg_score
        elif not course_metrics:
            # No course history metrics at all, only DG decomp for this player
            # Use DG decomposition as primary signal (already handled above
            # for players in player_dg_decomp but not player_data)
            pass

        results[pk] = {
            "score": round(score, 2),
            "components": {k: round(v, 2) for k, v in components.items()},
            "confidence": round(confidence, 2),
            "rounds": rounds,
        }

    return results
