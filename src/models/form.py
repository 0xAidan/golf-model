"""
Form Score

Uses recent form data (all courses) across multiple timeframes
to score how well each player is playing right now.

AUTO-DISCOVERS available round windows and metric categories from
whatever data you uploaded — no hardcoded windows.

Inputs (from metrics where data_mode = 'recent_form'):
  - Strokes gained ranks across ANY timeframes uploaded
  - Any metric category uploaded (ott, approach, putting, etc.)
  - Betsperts sim probabilities (win %, top 5/10/20 %)

Output: per-player form_score (0-100, higher = better form)
"""

from src import db


def _rank_to_score(rank: float, field_size: int) -> float:
    if rank is None or field_size <= 1:
        return 50.0
    rank = max(1, min(rank, field_size))
    return 100.0 * (1.0 - (rank - 1) / (field_size - 1))


def _pct_to_score(pct: float) -> float:
    """Convert a probability percentage to a 0-100 score."""
    if pct is None:
        return 50.0
    return min(100.0, 50.0 + pct * 300)


def _window_sort_key(w: str) -> int:
    """Sort round windows from largest (oldest) to smallest (most recent)."""
    if w == "all":
        return 9999
    try:
        return int(w)
    except ValueError:
        return 5000


def _discover_available_windows(tournament_id: int) -> list[str]:
    """Find all round windows that have recent_form strokes_gained data."""
    conn = db.get_conn()
    rows = conn.execute(
        """SELECT DISTINCT round_window FROM metrics
           WHERE tournament_id = ? AND data_mode = 'recent_form'
             AND metric_category = 'strokes_gained'
             AND round_window IS NOT NULL""",
        (tournament_id,),
    ).fetchall()
    conn.close()
    windows = [r["round_window"] for r in rows]
    # Sort: largest/oldest first, smallest/newest last
    windows.sort(key=_window_sort_key, reverse=True)
    return windows


def _discover_available_categories(tournament_id: int) -> list[str]:
    """Find all metric categories with recent_form data."""
    conn = db.get_conn()
    rows = conn.execute(
        """SELECT DISTINCT metric_category FROM metrics
           WHERE tournament_id = ? AND data_mode = 'recent_form'
             AND metric_category NOT IN ('meta', 'sim', 'recent_form', 'cheat_sheet')""",
        (tournament_id,),
    ).fetchall()
    conn.close()
    return [r["metric_category"] for r in rows]


def _get_sg_ranks_for_window(tournament_id: int, round_window: str) -> dict:
    """Get SG:TOT ranks for a given round window."""
    metrics = db.get_metrics_by_category(
        tournament_id, "strokes_gained",
        data_mode="recent_form", round_window=round_window,
    )
    player_ranks = {}
    for m in metrics:
        if m["metric_name"] == "SG:TOT" and m["metric_value"] is not None:
            player_ranks[m["player_key"]] = m["metric_value"]
    return player_ranks


def _get_sim_data(tournament_id: int) -> dict:
    """Get simulation probabilities."""
    metrics = db.get_metrics_by_category(tournament_id, "sim")
    player_sim = {}
    for m in metrics:
        pk = m["player_key"]
        if pk not in player_sim:
            player_sim[pk] = {}
        player_sim[pk][m["metric_name"]] = m["metric_value"]
    return player_sim


def _get_all_form_metrics(tournament_id: int) -> dict:
    """Get ALL recent form metrics organized by player, auto-discovering categories."""
    categories = _discover_available_categories(tournament_id)

    all_metrics = []
    for cat in categories:
        all_metrics.extend(
            db.get_metrics_by_category(tournament_id, cat, data_mode="recent_form")
        )

    player_data = {}
    for m in all_metrics:
        pk = m["player_key"]
        if pk not in player_data:
            player_data[pk] = {}
        key = f"{m['round_window']}_{m['metric_category']}_{m['metric_name']}"
        player_data[pk][key] = m["metric_value"]
    return player_data


def _get_dg_skill_data(tournament_id: int) -> dict:
    """Get DG true skill ratings (sg_total, sg_ott, sg_app, sg_arg, sg_putt)."""
    metrics = db.get_metrics_by_category(tournament_id, "dg_skill")
    player_skills = {}
    for m in metrics:
        pk = m["player_key"]
        if pk not in player_skills:
            player_skills[pk] = {}
        player_skills[pk][m["metric_name"]] = m["metric_value"]
    return player_skills


def _get_dg_ranking_data(tournament_id: int) -> dict:
    """Get DG ranking data (global rank, OWGR rank, skill estimate)."""
    metrics = db.get_metrics_by_category(tournament_id, "dg_ranking")
    player_ranks = {}
    for m in metrics:
        pk = m["player_key"]
        if pk not in player_ranks:
            player_ranks[pk] = {}
        player_ranks[pk][m["metric_name"]] = m["metric_value"]
    return player_ranks


def compute_form(tournament_id: int, weights: dict) -> dict:
    """
    Compute form score for every player.

    Auto-discovers whatever round windows and categories you uploaded.
    Also incorporates DG skill ratings (true ability) and DG rankings
    when available — these are the most accurate baseline signals.

    Returns: {player_key: {"score": float, "components": dict, "windows_used": list}}
    """
    # Auto-discover available windows
    available_windows = _discover_available_windows(tournament_id)

    # Get SG ranks for each available window
    sg_by_window = {}
    for w in available_windows:
        ranks = _get_sg_ranks_for_window(tournament_id, w)
        if ranks:
            sg_by_window[w] = ranks

    # Get sim data
    sim_data = _get_sim_data(tournament_id)

    # Get all form data (auto-discovers categories)
    all_form = _get_all_form_metrics(tournament_id)

    # Get DG skill ratings (true player ability — field-strength adjusted)
    dg_skill_data = _get_dg_skill_data(tournament_id)

    # Get DG rankings
    dg_ranking_data = _get_dg_ranking_data(tournament_id)

    # Collect all players
    all_players = set()
    for ranks in sg_by_window.values():
        all_players.update(ranks.keys())
    all_players.update(sim_data.keys())
    all_players.update(all_form.keys())
    all_players.update(dg_skill_data.keys())
    all_players.update(dg_ranking_data.keys())

    if not all_players:
        return {}

    # Weight config
    w_sim = weights.get("form_sim", 0.25)

    # SG sub-weights
    w_sg_tot = weights.get("form_sg_tot", 0.40)
    w_sg_app = weights.get("form_sg_app", 0.25)
    w_sg_ott = weights.get("form_sg_ott", 0.15)
    w_sg_putt = weights.get("form_sg_putt", 0.10)
    w_sg_arg = weights.get("form_sg_arg", 0.10)

    # Determine field sizes per window
    field_sizes = {w: len(r) for w, r in sg_by_window.items()}

    # Classify windows into "recent" (<=16 rounds) vs "baseline" (>16 rounds)
    recent_windows = []
    baseline_windows = []
    for w in available_windows:
        if w == "all":
            baseline_windows.append(w)
        else:
            try:
                n = int(w)
                if n <= 20:
                    recent_windows.append(w)
                else:
                    baseline_windows.append(w)
            except ValueError:
                baseline_windows.append(w)

    # Sort recent: smallest (most recent) first for priority
    recent_windows.sort(key=lambda x: _window_sort_key(x))
    # Sort baseline: largest (most data) first for priority
    baseline_windows.sort(key=lambda x: _window_sort_key(x), reverse=True)

    # Dynamic weighting: more windows available = each gets less weight
    # But recent windows get more weight than baseline
    n_windows = len(sg_by_window)
    if n_windows == 0:
        recent_weight = 0.0
        baseline_weight = 0.0
    elif n_windows == 1:
        recent_weight = 0.75 * (1.0 - w_sim)
        baseline_weight = 0.0
    else:
        recent_weight = 0.45 * (1.0 - w_sim)
        baseline_weight = 0.30 * (1.0 - w_sim)

    results = {}
    for pk in all_players:
        components = {}
        windows_used = []

        # ── Recent window scores (use all available, weighted by recency) ──
        recent_scores = []
        for w in recent_windows:
            if w in sg_by_window and pk in sg_by_window[w]:
                score = _rank_to_score(sg_by_window[w][pk], field_sizes[w])
                recent_scores.append((w, score))
                windows_used.append(f"recent:{w}")
        if recent_scores:
            # Weight more recent windows higher
            # First (most recent) gets weight n, second gets n-1, etc.
            n = len(recent_scores)
            total_w = sum(range(1, n + 1))
            recent_score = sum(
                score * (n - i) / total_w for i, (_, score) in enumerate(recent_scores)
            )
        else:
            recent_score = 50.0
        components["recent"] = recent_score

        # ── Baseline window scores ──
        baseline_scores = []
        for w in baseline_windows:
            if w in sg_by_window and pk in sg_by_window[w]:
                score = _rank_to_score(sg_by_window[w][pk], field_sizes[w])
                baseline_scores.append((w, score))
                windows_used.append(f"baseline:{w}")
        if baseline_scores:
            baseline_score = sum(s for _, s in baseline_scores) / len(baseline_scores)
        else:
            baseline_score = 50.0
        components["baseline"] = baseline_score

        # ── Sim probability score ──
        sim_score = 50.0
        if pk in sim_data:
            sd = sim_data[pk]
            win_pct = sd.get("Win %", 0) or 0
            top10_pct = sd.get("Top 10 %", 0) or 0
            top20_pct = sd.get("Top 20 %", 0) or 0
            make_cut = sd.get("Make Cut", 0) or 0
            sim_score = (
                0.30 * _pct_to_score(win_pct)
                + 0.30 * min(100, top10_pct * 120)
                + 0.25 * min(100, top20_pct * 100)
                + 0.15 * min(100, make_cut * 90)
            )
            windows_used.append("sim")
        components["sim"] = sim_score

        # ── Multi-SG score (from best available recent window) ──
        form_data = all_form.get(pk, {})
        # Find the best (most recent) window that has SG:TOT data
        best_window = None
        for w in recent_windows + baseline_windows:
            if f"{w}_strokes_gained_SG:TOT" in form_data:
                best_window = w
                break
        if best_window is None:
            # Try any available window
            for key in form_data:
                if "strokes_gained_SG:TOT" in key:
                    best_window = key.split("_")[0]
                    break

        if best_window:
            fs = field_sizes.get(best_window, 120)
            sg_scores = {
                "tot": _rank_to_score(form_data.get(f"{best_window}_strokes_gained_SG:TOT"), fs),
                "app": _rank_to_score(
                    form_data.get(f"{best_window}_strokes_gained_SG:APP")
                    or form_data.get(f"{best_window}_approach_SG:APP"), fs),
                "ott": _rank_to_score(
                    form_data.get(f"{best_window}_strokes_gained_SG:OTT")
                    or form_data.get(f"{best_window}_ott_SG:OTT"), fs),
                "putt": _rank_to_score(form_data.get(f"{best_window}_strokes_gained_SG:P"), fs),
                "arg": _rank_to_score(form_data.get(f"{best_window}_strokes_gained_SG:ARG"), fs),
            }
            multi_sg = (
                w_sg_tot * sg_scores["tot"]
                + w_sg_app * sg_scores["app"]
                + w_sg_ott * sg_scores["ott"]
                + w_sg_putt * sg_scores["putt"]
                + w_sg_arg * sg_scores["arg"]
            )
            windows_used.append(f"sg_detail:{best_window}")
        else:
            multi_sg = 50.0
        components["multi_sg"] = multi_sg

        # ── DG Skill Rating score (true player ability) ──
        dg_skill_score = 50.0
        has_dg_skill = False
        if pk in dg_skill_data:
            dg_sk = dg_skill_data[pk]
            dg_sg_total = dg_sk.get("dg_sg_total")
            if dg_sg_total is not None:
                # Rank this player's DG SG:Total among all players who have it
                all_dg_totals = [
                    d.get("dg_sg_total", 0) for d in dg_skill_data.values()
                    if d.get("dg_sg_total") is not None
                ]
                if all_dg_totals:
                    below = sum(1 for v in all_dg_totals if v < dg_sg_total)
                    dg_skill_score = 100.0 * below / max(len(all_dg_totals) - 1, 1)
                    has_dg_skill = True
                    windows_used.append("dg_skill")
        components["dg_skill"] = dg_skill_score

        # ── DG Ranking score (global rank signal) ──
        dg_rank_score = 50.0
        has_dg_rank = False
        if pk in dg_ranking_data:
            dg_rk = dg_ranking_data[pk]
            dg_rank = dg_rk.get("dg_rank")
            if dg_rank is not None:
                # Invert: rank 1 = 100, rank 500 = 0
                dg_rank_score = max(0.0, 100.0 * (1.0 - (dg_rank - 1) / 499))
                has_dg_rank = True
                windows_used.append("dg_ranking")
        components["dg_ranking"] = dg_rank_score

        # ── Weighted total ──
        # DG skill ratings are the most accurate available signal,
        # so they get significant weight when available.
        remaining = 1.0 - w_sim
        multi_sg_weight = remaining * 0.20

        # DG skill weight: 15% of total when available
        dg_skill_weight = 0.15 if has_dg_skill else 0.0
        # DG rank weight: 5% of total when available
        dg_rank_weight = 0.05 if has_dg_rank else 0.0
        # Reduce other weights proportionally to make room
        dg_total_weight = dg_skill_weight + dg_rank_weight

        # Adjust if we have fewer window types
        if not recent_scores and not baseline_scores:
            # Only sim + multi_sg + DG signals
            non_dg = 1.0 - dg_total_weight
            score = (non_dg * 0.5) * sim_score + (non_dg * 0.5) * multi_sg
            score += dg_skill_weight * dg_skill_score + dg_rank_weight * dg_rank_score
        elif not recent_scores:
            adj_factor = 1.0 - dg_total_weight
            score = (adj_factor * baseline_weight * 2 * baseline_score
                     + adj_factor * w_sim * sim_score
                     + adj_factor * multi_sg_weight * multi_sg
                     + dg_skill_weight * dg_skill_score
                     + dg_rank_weight * dg_rank_score)
        else:
            adj_factor = 1.0 - dg_total_weight
            score = (
                adj_factor * recent_weight * recent_score
                + adj_factor * baseline_weight * baseline_score
                + adj_factor * w_sim * sim_score
                + adj_factor * multi_sg_weight * multi_sg
                + dg_skill_weight * dg_skill_score
                + dg_rank_weight * dg_rank_score
            )

        results[pk] = {
            "score": round(score, 2),
            "components": {k: round(v, 2) for k, v in components.items()},
            "windows_used": windows_used,
        }

    return results
