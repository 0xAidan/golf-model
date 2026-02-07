"""
Form Score

Uses recent form data (all courses) across multiple timeframes
to score how well each player is playing right now.

Inputs (from metrics where data_mode = 'recent_form'):
  - Strokes gained ranks across timeframes (all rounds, 12r, 16r, 24r)
  - 12-month form data
  - Betsperts sim probabilities (win %, top 5/10/20 %)
  - Rolling averages (L4, L8, L20, L50)

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
    # Sim percentages are already 0-1 range typically
    # Scale so that top values get high scores
    # A 18% win rate (like Scheffler) should be ~95+
    # A 1% win rate should be ~50-60
    return min(100.0, 50.0 + pct * 300)


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
    """Get all recent form metrics organized by player."""
    all_metrics = db.get_metrics_by_category(
        tournament_id, "strokes_gained", data_mode="recent_form"
    )
    # Also get other form categories
    for cat in ["ott", "approach", "putting", "scoring",
                "par3_efficiency", "par4_efficiency", "par5_efficiency"]:
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


def compute_form(tournament_id: int, weights: dict) -> dict:
    """
    Compute form score for every player.

    Returns: {player_key: {"score": float, "components": dict}}
    """
    # Get SG ranks across available windows
    windows_to_check = ["all", "8", "12", "16", "24", "36", "50"]
    sg_by_window = {}
    for w in windows_to_check:
        ranks = _get_sg_ranks_for_window(tournament_id, w)
        if ranks:
            sg_by_window[w] = ranks

    # Get sim data
    sim_data = _get_sim_data(tournament_id)

    # Get all form data
    all_form = _get_all_form_metrics(tournament_id)

    # Collect all players
    all_players = set()
    for ranks in sg_by_window.values():
        all_players.update(ranks.keys())
    all_players.update(sim_data.keys())
    all_players.update(all_form.keys())

    if not all_players:
        return {}

    # Weight config
    w_16r = weights.get("form_16r", 0.35)
    w_12month = weights.get("form_12month", 0.25)
    w_sim = weights.get("form_sim", 0.25)
    w_rolling = weights.get("form_rolling", 0.15)

    # SG sub-weights
    w_sg_tot = weights.get("form_sg_tot", 0.40)
    w_sg_app = weights.get("form_sg_app", 0.25)
    w_sg_ott = weights.get("form_sg_ott", 0.15)
    w_sg_putt = weights.get("form_sg_putt", 0.10)
    w_sg_arg = weights.get("form_sg_arg", 0.10)

    # Determine field sizes per window
    field_sizes = {w: len(r) for w, r in sg_by_window.items()}

    results = {}
    for pk in all_players:
        components = {}

        # ── Recent window score (16r or closest available) ────
        recent_score = 50.0
        for w in ["16", "12", "8"]:
            if w in sg_by_window and pk in sg_by_window[w]:
                recent_score = _rank_to_score(sg_by_window[w][pk], field_sizes[w])
                break
        components["recent"] = recent_score

        # ── Baseline score (all rounds or 12-month) ────
        baseline_score = 50.0
        for w in ["all", "50", "36", "24"]:
            if w in sg_by_window and pk in sg_by_window[w]:
                baseline_score = _rank_to_score(sg_by_window[w][pk], field_sizes[w])
                break
        components["baseline"] = baseline_score

        # ── Sim probability score ────
        sim_score = 50.0
        if pk in sim_data:
            sd = sim_data[pk]
            # Weight: win% matters most, then top10, top20
            win_pct = sd.get("Win %", 0) or 0
            top10_pct = sd.get("Top 10 %", 0) or 0
            top20_pct = sd.get("Top 20 %", 0) or 0
            make_cut = sd.get("Make Cut", 0) or 0

            # Normalize: a 10% win rate is elite, 0.1% is low
            sim_score = (
                0.30 * _pct_to_score(win_pct)
                + 0.30 * min(100, top10_pct * 120)
                + 0.25 * min(100, top20_pct * 100)
                + 0.15 * min(100, make_cut * 90)
            )
        components["sim"] = sim_score

        # ── Multi-SG score (from best available window) ────
        form_data = all_form.get(pk, {})
        best_window = "16"
        for w in ["16", "12", "all", "24"]:
            if f"{w}_strokes_gained_SG:TOT" in form_data:
                best_window = w
                break

        fs = field_sizes.get(best_window, 120)
        sg_scores = {
            "tot": _rank_to_score(form_data.get(f"{best_window}_strokes_gained_SG:TOT"), fs),
            "app": _rank_to_score(form_data.get(f"{best_window}_strokes_gained_SG:APP")
                                  or form_data.get(f"{best_window}_approach_SG:APP"), fs),
            "ott": _rank_to_score(form_data.get(f"{best_window}_strokes_gained_SG:OTT")
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
        components["multi_sg"] = multi_sg

        # ── Weighted total ────
        score = (
            w_16r * recent_score
            + w_12month * baseline_score
            + w_sim * sim_score
            + w_rolling * multi_sg
        )

        results[pk] = {
            "score": round(score, 2),
            "components": {k: round(v, 2) for k, v in components.items()},
        }

    return results
