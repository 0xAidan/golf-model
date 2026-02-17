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

    # Pull DG approach skill data (detailed by yardage/lie bucket)
    dg_approach_metrics = db.get_metrics_by_category(tournament_id, "dg_approach")
    player_dg_approach = {}
    for m in dg_approach_metrics:
        pk = m["player_key"]
        if pk not in player_dg_approach:
            player_dg_approach[pk] = {}
        player_dg_approach[pk][m["metric_name"]] = m["metric_value"]

    # Pull DG skill ratings (true SG per category)
    dg_skill_metrics = db.get_metrics_by_category(tournament_id, "dg_skill")
    player_dg_skill = {}
    for m in dg_skill_metrics:
        pk = m["player_key"]
        if pk not in player_dg_skill:
            player_dg_skill[pk] = {}
        player_dg_skill[pk][m["metric_name"]] = m["metric_value"]

    if not course_metrics and not dg_decomp and not player_dg_skill:
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

    # Merge: include players that only appear in DG decomp, skill, or approach
    for pk in player_dg_decomp:
        if pk not in player_data:
            player_data[pk] = {}
    for pk in player_dg_skill:
        if pk not in player_data:
            player_data[pk] = {}
    for pk in player_dg_approach:
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

        # ── Blend with DG data sources ──
        # Track total external blend weight to prevent over-dilution.
        # Cap total external blending at 60% — course-specific signal
        # should always retain at least 40% of the final score.
        MAX_EXTERNAL_BLEND = 0.60
        total_blend_used = 0.0

        # DG decomposition blend
        dg_data = player_dg_decomp.get(pk)
        if dg_data:
            dg_sg_total = dg_data.get("dg_sg_total")
            if dg_sg_total is not None:
                all_dg_totals = [
                    d.get("dg_sg_total", 0) for d in player_dg_decomp.values()
                    if d.get("dg_sg_total") is not None
                ]
                if all_dg_totals:
                    below = sum(1 for v in all_dg_totals if v < dg_sg_total)
                    dg_score = 100.0 * below / max(len(all_dg_totals) - 1, 1)
                    components["dg_decomp"] = round(dg_score, 2)

                    if confidence >= 0.5:
                        dg_weight = 0.30
                    else:
                        dg_weight = 0.70
                    dg_weight = min(dg_weight, MAX_EXTERNAL_BLEND - total_blend_used)
                    score = (1 - dg_weight) * score + dg_weight * dg_score
                    total_blend_used += dg_weight

        # DG skill ratings blend
        dg_sk = player_dg_skill.get(pk)
        if dg_sk and total_blend_used < MAX_EXTERNAL_BLEND:
            sk_app = dg_sk.get("dg_sg_app")
            sk_ott = dg_sk.get("dg_sg_ott")
            sk_arg = dg_sk.get("dg_sg_arg")
            sk_putt = dg_sk.get("dg_sg_putt")

            def _percentile_score(val, all_vals):
                if val is None or not all_vals:
                    return None
                below = sum(1 for v in all_vals if v < val)
                return 100.0 * below / max(len(all_vals) - 1, 1)

            all_apps = [d.get("dg_sg_app") for d in player_dg_skill.values() if d.get("dg_sg_app") is not None]
            all_otts = [d.get("dg_sg_ott") for d in player_dg_skill.values() if d.get("dg_sg_ott") is not None]
            all_putts = [d.get("dg_sg_putt") for d in player_dg_skill.values() if d.get("dg_sg_putt") is not None]

            skill_components = {}
            weighted_sum = 0.0
            weight_total = 0.0

            for cat_name, val, all_vals, weight in [
                ("skill_app", sk_app, all_apps, w_sg_app),
                ("skill_ott", sk_ott, all_otts, w_sg_ott),
                ("skill_putt", sk_putt, all_putts, w_sg_putt),
            ]:
                pctile = _percentile_score(val, all_vals)
                if pctile is not None:
                    skill_components[cat_name] = round(pctile, 2)
                    weighted_sum += weight * pctile
                    weight_total += weight

            if weight_total > 0:
                dg_skill_fit = weighted_sum / weight_total
                components["dg_skill_fit"] = round(dg_skill_fit, 2)

                skill_blend = min(0.15, MAX_EXTERNAL_BLEND - total_blend_used)
                if skill_blend > 0:
                    score = (1 - skill_blend) * score + skill_blend * dg_skill_fit
                    total_blend_used += skill_blend

        # DG approach skill blend
        dg_app = player_dg_approach.get(pk)
        if dg_app and total_blend_used < MAX_EXTERNAL_BLEND:
            approach_composite = dg_app.get("approach_sg_composite")
            if approach_composite is not None:
                all_composites = [
                    d.get("approach_sg_composite") for d in player_dg_approach.values()
                    if d.get("approach_sg_composite") is not None
                ]
                if all_composites:
                    below = sum(1 for v in all_composites if v < approach_composite)
                    app_score = 100.0 * below / max(len(all_composites) - 1, 1)
                    components["dg_approach"] = round(app_score, 2)

                    app_blend = min(0.12, w_sg_app * 0.4, MAX_EXTERNAL_BLEND - total_blend_used)
                    if app_blend > 0:
                        score = (1 - app_blend) * score + app_blend * app_score
                        total_blend_used += app_blend

        elif not course_metrics and not dg_data and not dg_sk:
            pass

        # Apply confidence modifier AFTER all blends (prevents double-penalizing
        # low-confidence players who also get heavy DG blending)
        score = 50.0 + confidence * (score - 50.0)

        results[pk] = {
            "score": round(score, 2),
            "components": {k: round(v, 2) for k, v in components.items()},
            "confidence": round(confidence, 2),
            "rounds": rounds,
        }

    return results
