"""
Betting Card Generator

Produces a short, digestible markdown betting card.
Bet types: Outright, Top 5, Top 10, Top 20, Matchups, 72-hole groups.
No DFS.
"""

import logging
import os
from datetime import datetime

from src import config, db
from src.feature_flags import is_enabled
from src.kelly import units_for_bet
from src.odds_utils import american_to_decimal as _american_to_decimal

logger = logging.getLogger("card")


def _fmt_odds(price: int) -> str:
    if price > 0:
        return f"+{price}"
    return str(price)


def _fmt_prob(prob: float) -> str:
    """Format probability for display, using more decimals for small values."""
    if prob >= 0.01:
        return f"{prob:.1%}"
    elif prob >= 0.001:
        return f"{prob:.2%}"
    else:
        return f"{prob:.3%}"


def _top_bets_for_summary(value_bets: dict, matchup_bets: list[dict] | None) -> list[dict]:
    """Collect top N matchup plays: tournament matchups first, then round matchups. No placements."""
    max_bets = getattr(config, "BEST_BETS_COUNT", 5)

    tournament_candidates = []
    round_candidates = []

    if matchup_bets:
        for b in matchup_bets:
            ev = b.get("ev", 0) or 0
            ev_pct = b.get("ev_pct", "")
            if isinstance(ev_pct, (int, float)):
                ev_pct = f"{ev_pct:.1f}%"
            odds_val = b.get("odds", 0) or 0
            odds_str = f"+{odds_val}" if odds_val > 0 else str(odds_val)
            pick = f"{b.get('pick', '')} vs {b.get('opponent', '')}"
            market_type = b.get("market_type", "")
            mtype_label = "72-hole" if market_type == "tournament_matchups" else "round"

            entry = {
                "ev": ev, "pick": pick, "market": "matchup",
                "odds": odds_str, "ev_pct": ev_pct, "tier": b.get("tier", "LEAN"),
                "stake": None, "market_type_label": mtype_label,
                "conviction": b.get("conviction", None),
            }

            if market_type == "tournament_matchups":
                tournament_candidates.append(entry)
            else:
                round_candidates.append(entry)

    tournament_candidates.sort(key=lambda x: x["ev"], reverse=True)
    round_candidates.sort(key=lambda x: x["ev"], reverse=True)

    top = list(tournament_candidates[:max_bets])
    remaining = max_bets - len(top)
    if remaining > 0:
        top.extend(round_candidates[:remaining])

    return top[:max_bets]


def _reason(r: dict) -> str:
    """Build a brief reason string from a player's scores."""
    parts = []
    if r.get("course_fit", 50) > 65:
        parts.append(f"course fit {r['course_fit']:.0f}")
    if r.get("form", 50) > 65:
        parts.append(f"form {r['form']:.0f}")
    md = r.get("momentum_direction", "")
    if md == "hot":
        parts.append(f"trending hot (+{r.get('momentum_trend', 0):.0f})")
    elif md == "cold":
        parts.append(f"trending cold ({r.get('momentum_trend', 0):.0f})")
    if r.get("ev", 0) > 0.05:
        parts.append(f"EV {r.get('ev_pct', '')}")
    if r.get("course_rounds", 0) >= 20:
        parts.append(f"{int(r['course_rounds'])} rds at course")
    return "; ".join(parts) if parts else "composite edge"


def generate_card(tournament_name: str,
                  course_name: str,
                  composite_results: list[dict],
                  value_bets: dict = None,
                  output_dir: str = "output",
                  ai_pre_analysis: dict = None,
                  ai_decisions: dict = None,
                  matchup_bets: list[dict] = None,
                  strategy_meta: dict | None = None,
                  mode: str = "full") -> str:
    """
    Generate a markdown betting card.

    composite_results: from composite.compute_composite()
    value_bets: dict keyed by bet_type ('outright', 'top5', etc.)
                each value is a list from value.find_value_bets()
    ai_pre_analysis: AI pre-tournament analysis (optional)
    ai_decisions: AI betting decisions (optional)
    matchup_bets: list of matchup value bets from matchup_value module (optional)

    Returns the file path of the generated card.
    """
    if value_bets is None:
        value_bets = {}

    show_placements = mode in ("full", "placements-only")
    show_matchups = mode in ("full", "matchups-only", "round-matchups")
    show_3ball = mode in ("full", "matchups-only")

    if mode == "round-matchups" and matchup_bets:
        matchup_bets = [b for b in matchup_bets if b.get("market_type") == "round_matchups"]

    lines = []
    lines.append(f"# {tournament_name} — Betting Card")
    lines.append(f"**Course:** {course_name}")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    if strategy_meta:
        src = strategy_meta.get("strategy_source", "default")
        name = strategy_meta.get("strategy_name", "default")
        rid = strategy_meta.get("strategy_record_id")
        id_suffix = f" (id {rid})" if rid else ""
        lines.append(f"**Baseline Strategy:** {name}{id_suffix} via `{src}`")
    if ai_pre_analysis:
        conf = ai_pre_analysis.get('confidence', 0)
        lines.append(f"**AI Analysis:** Enabled ({conf:.0%} confidence)")
        factors = ai_pre_analysis.get('confidence_factors', {})
        explanation = ai_pre_analysis.get('confidence_explanation', '')
        if factors:
            factor_strs = [f"{k.replace('_', ' ').title()}: {v:.0%}" for k, v in factors.items()]
            lines.append(f"*Confidence breakdown: {', '.join(factor_strs)}*")
        if explanation:
            lines.append(f"*{explanation}*")
    lines.append("")

    try:
        conn = db.get_conn()
        matchup_preds = conn.execute(
            "SELECT actual_outcome, profit FROM prediction_log WHERE bet_type = 'matchup' AND actual_outcome IS NOT NULL"
        ).fetchall()
        conn.close()
        if matchup_preds:
            wins = sum(1 for p in matchup_preds if (p["actual_outcome"] or 0) == 1)
            losses = sum(1 for p in matchup_preds if (p["actual_outcome"] or 0) == 0)
            total_profit = sum(p["profit"] or 0 for p in matchup_preds)
            total_risked = len(matchup_preds)
            roi = (total_profit / total_risked * 100) if total_risked else 0
            lines.append(f"**Season Matchup Record:** {wins}-{losses} ({total_profit:+.1f}U, {roi:+.1f}% ROI)")
            lines.append("")
    except Exception:
        pass

    # ── Section 1: Exec Summary (always visible) ─────────────────
    lines.append(f"## Top {getattr(config, 'BEST_BETS_COUNT', 5)} Matchup Plays")
    lines.append("")

    if strategy_meta:
        lines.append("## Baseline Provenance")
        lines.append("")
        runtime = strategy_meta.get("runtime_settings", {})
        blend = runtime.get("blend_weights", {})
        lines.append(
            f"- Strategy source: `{strategy_meta.get('strategy_source', 'default')}`"
        )
        lines.append(
            f"- Blend: course {blend.get('course_fit', 0):.0%}, "
            f"form {blend.get('form', 0):.0%}, "
            f"momentum {blend.get('momentum', 0):.0%}"
        )
        if runtime.get("ev_threshold") is not None:
            lines.append(f"- EV threshold: {runtime['ev_threshold']:.0%}")
        lines.append("")
    best_plays = _top_bets_for_summary(value_bets, matchup_bets)
    if best_plays:
        show_stake = is_enabled("kelly_sizing") or is_enabled("kelly_stakes")
        header = "| Pick | Type | Odds | EV% | Tier |"
        if show_stake:
            header += " Stake |"
        lines.append(header)
        sep = "|------|------|------|-----|------|"
        if show_stake:
            sep += "--------|"
        lines.append(sep)
        for row in best_plays:
            stake_str = ""
            if show_stake:
                s = row.get("stake")
                stake_str = f" {s:.2f}u |" if s is not None else " — |"
            mtype = row.get("market_type_label", "matchup")
            lines.append(
                f"| **{row['pick']}** | {mtype} | {row['odds']} | {row['ev_pct']} | {row.get('tier', '—')} |" + stake_str
            )
    else:
        lines.append("*No matchup value bets above threshold this week.*")
    lines.append("")

    # ── Sections 2+ (collapsible) ─────────────────────────────
    lines.append("<details>")
    lines.append("<summary>Weekly Strategy & Adaptation</summary>")
    lines.append("")
    _write_weekly_strategy(lines, value_bets)
    _write_adaptation_status(lines)
    lines.append("</details>")
    lines.append("")

    lines.append("<details>")
    lines.append("<summary>Model Rankings (Top 20)</summary>")
    lines.append("")
    lines.append("## Model Rankings (Top 20)")
    lines.append("")
    lines.append("| Rank | Player | Composite | Course Fit | Form | Momentum | Trend |")
    lines.append("|------|--------|-----------|------------|------|----------|-------|")
    for r in composite_results[:20]:
        trend_symbol = {"hot": "↑↑", "warming": "↑", "cooling": "↓", "cold": "↓↓"}.get(
            r.get("momentum_direction", ""), "—"
        )
        lines.append(
            f"| {r['rank']} | {r['player_display']} | {r['composite']:.1f} "
            f"| {r['course_fit']:.1f} | {r['form']:.1f} | {r['momentum']:.1f} | {trend_symbol} |"
        )
    lines.append("")
    lines.append("</details>")
    lines.append("")

    if show_matchups:
        lines.append("<details>")
        lines.append("<summary>Matchup Value Bets (Primary)</summary>")
        lines.append("")
        _write_matchup_value_bets(lines, matchup_bets)
        lines.append("</details>")
        lines.append("")

    if show_3ball:
        lines.append("<details>")
        lines.append("<summary>3-Ball Markets</summary>")
        lines.append("")
        lines.append("## 3-Ball")
        lines.append("")
        three_ball = value_bets.get("3ball", [])
        three_ball_value = [b for b in three_ball if b.get("is_value")]
        if three_ball_value:
            _write_value_section(lines, three_ball_value, top_n=10)
        else:
            lines.append("*No 3-ball value plays this week.*")
            lines.append("")
        lines.append("</details>")
        lines.append("")

    if not show_placements:
        lines.append("*Placement markets omitted (mode: " + mode + ")*")
        lines.append("")

    if show_placements:
        lines.append("<details>")
        lines.append("<summary>Value Picks: Placement Markets (Secondary)</summary>")
        lines.append("")
        lines.append("## Value Picks: Placement Markets")
        lines.append("")

        top15_vb = value_bets.get("top15", [])
        top10_vb = value_bets.get("top10", [])
        top20_vb = value_bets.get("top20", [])
        top5_vb = value_bets.get("top5", [])
        ev_floor = getattr(config, "PLACEMENT_CARD_EV_FLOOR", 0.15)
        placement_max = getattr(config, "PLACEMENT_CARD_MAX", 3)

        lines.append("### Top 20 Finish")
        lines.append("")
        if top20_vb:
            qualified = [b for b in top20_vb if b.get("is_value") and not b.get("suspicious") and not b.get("ev_capped") and (b.get("ev", 0) or 0) >= ev_floor]
            _write_value_section(lines, qualified, top_n=placement_max)
        else:
            lines.append("*No odds data available for Top 20.*")
            lines.append("")

        lines.append("### Top 15 Finish")
        lines.append("")
        if top15_vb:
            qualified = [b for b in top15_vb if b.get("is_value") and not b.get("suspicious") and not b.get("ev_capped") and (b.get("ev", 0) or 0) >= ev_floor]
            _write_value_section(lines, qualified, top_n=placement_max)
        else:
            lines.append("*No odds data available for Top 15.*")
            lines.append("")

        lines.append("### Top 10 Finish")
        lines.append("")
        if top10_vb:
            qualified = [b for b in top10_vb if b.get("is_value") and not b.get("suspicious") and not b.get("ev_capped") and (b.get("ev", 0) or 0) >= ev_floor]
            _write_value_section(lines, qualified, top_n=placement_max)
        else:
            lines.append("*No odds data available for Top 10.*")
            lines.append("")

        lines.append("### Top 5 Finish")
        lines.append("")
        if top5_vb:
            qualified = [b for b in top5_vb if b.get("is_value") and not b.get("suspicious") and not b.get("ev_capped") and (b.get("ev", 0) or 0) >= ev_floor]
            _write_value_section(lines, qualified, top_n=placement_max)
        else:
            lines.append("*No odds data available for Top 5.*")
        lines.append("")
        lines.append("</details>")
        lines.append("")

        outright_vb = value_bets.get("outright", [])
        outright_value = [b for b in outright_vb if b.get("is_value") and not b.get("suspicious") and not b.get("ev_capped") and (b.get("ev", 0) or 0) >= ev_floor]
        if outright_value:
            lines.append("<details>")
            lines.append("<summary>Outright Value (High-Confidence Only)</summary>")
            lines.append("")
            lines.append("## Outright Value")
            lines.append("")
            lines.append(f"*Only showing outrights with EV >= {ev_floor:.0%}.*")
            lines.append("")
            _write_value_section(lines, outright_value, top_n=placement_max)
            lines.append("</details>")
            lines.append("")

    if ai_pre_analysis:
        lines.append("<details>")
        lines.append("<summary>AI Course Analysis</summary>")
        lines.append("")
        lines.append("## AI Course Analysis")
        lines.append("")

        narrative = ai_pre_analysis.get("course_narrative", "")
        if narrative:
            lines.append(f"**Course Narrative:** {narrative}")
            lines.append("")

        key_factors = ai_pre_analysis.get("key_factors", [])
        if key_factors:
            lines.append("**Key Factors:**")
            for kf in key_factors:
                lines.append(f"- {kf}")
            lines.append("")

        watch = ai_pre_analysis.get("players_to_watch", [])
        if watch:
            lines.append("**Players to Watch (AI sees edge):**")
            lines.append("")
            lines.append("| Player | Adjustment | Edge |")
            lines.append("|--------|------------|------|")
            for p in watch:
                adj = p.get("adjustment", 0)
                sign = "+" if adj > 0 else ""
                lines.append(f"| {p['player']} | {sign}{adj:.1f} | {p['edge']} |")
            lines.append("")

        fades = ai_pre_analysis.get("players_to_fade", [])
        if fades:
            lines.append("**Players to Fade (AI sees risk):**")
            lines.append("")
            lines.append("| Player | Adjustment | Reason |")
            lines.append("|--------|------------|--------|")
            for p in fades:
                adj = p.get("adjustment", 0)
                sign = "+" if adj > 0 else ""
                lines.append(f"| {p['player']} | {sign}{adj:.1f} | {p['reason']} |")
            lines.append("")
        lines.append("</details>")
        lines.append("")

    lines.append("<details>")
    lines.append("<summary>Fades (Avoid)</summary>")
    lines.append("")
    lines.append("## Fades (Avoid)")
    lines.append("")
    lines.append("Players likely overpriced or in poor form:")
    lines.append("")
    for r in composite_results[-10:]:
        if r.get("momentum_direction") == "cold" or r["composite"] < 40:
            lines.append(f"- **{r['player_display']}** — composite {r['composite']:.1f}, {_reason(r)}")
    lines.append("")
    lines.append("</details>")
    lines.append("")

    lines.append("<details>")
    lines.append("<summary>Data Quality & Methodology</summary>")
    lines.append("")
    _write_data_quality(lines, value_bets, composite_results)
    lines.append("</details>")
    lines.append("")

    # ── Footer ────────────────────────────────────────────────
    lines.append("---")
    ai_tag = " AI-adjusted." if ai_pre_analysis else ""
    runtime = (strategy_meta or {}).get("runtime_settings", {})
    blend = runtime.get("blend_weights", {})
    lines.append(
        f"*Model v{config.MODEL_VERSION}: {len(composite_results)} players scored. "
        f"Course data: {'Yes' if any(r.get('course_rounds', 0) > 0 for r in composite_results) else 'No'}."
        f"{ai_tag} Weights: {blend.get('course_fit', 0.45):.0%} course fit / "
        f"{blend.get('form', 0.45):.0%} form / {blend.get('momentum', 0.10):.0%} momentum."
        f" DG blend: 95% DG / 5% model.*"
    )

    os.makedirs(output_dir, exist_ok=True)
    safe_name = tournament_name.lower().replace(" ", "_").replace("'", "")

    try:
        from src.output_manager import archive_previous
        archived = archive_previous(output_dir, safe_name, file_type="card")
        if archived:
            logger.info("Archived %d previous card(s) for %s", archived, safe_name)
    except Exception as e:
        logger.warning("Could not archive previous cards: %s", e)

    filename = f"{safe_name}_{datetime.now().strftime('%Y%m%d')}.md"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w") as f:
        f.write("\n".join(lines))

    return filepath


def _write_weekly_strategy(lines: list, value_bets: dict):
    """Summarize where the model sees its edge this week."""
    lines.append("## Weekly Strategy")
    lines.append("")

    core_value = 0
    spec_value = 0
    for market, bets in value_bets.items():
        count = sum(1 for b in bets if b.get("is_value") and not b.get("suspicious") and not b.get("ev_capped"))
        if market in ("top10", "top20", "make_cut"):
            core_value += count
        elif market in ("outright", "top5", "frl"):
            spec_value += count

    parts = []
    parts.append("Matchups are always the primary focus (strongest historical signal).")
    if core_value > 0:
        parts.append(f"{core_value} placement value bet(s) found in Top 10/20 markets.")
    else:
        parts.append("No placement value bets this week — market is efficiently priced.")
    if spec_value > 0:
        parts.append(f"{spec_value} speculative value bet(s) in outright/top 5 (high variance).")
    else:
        parts.append("No speculative value found in outright/top 5 markets.")

    for p in parts:
        lines.append(f"- {p}")
    lines.append("")


def _write_data_quality(lines: list, value_bets: dict, composite_results: list):
    """Add a data quality section if there are any concerns."""
    warnings = []

    # Check if we have odds data at all
    total_odds_entries = sum(len(vb) for vb in value_bets.values())
    if total_odds_entries == 0:
        warnings.append("No odds data available — value bets based on model only")

    # Check for suspicious/capped entries
    for bet_type, vbs in value_bets.items():
        capped = sum(1 for vb in vbs if vb.get("ev_capped"))
        suspicious = sum(1 for vb in vbs if vb.get("suspicious"))
        if capped > 0:
            warnings.append(f"{capped} {bet_type} entries had unrealistic EV (capped/filtered)")
        if suspicious > 0:
            warnings.append(f"{suspicious} {bet_type} entries had large model-vs-market discrepancy (flagged)")

    # Check if top players have reasonable scores
    if composite_results:
        top_player = composite_results[0]
        if top_player["composite"] < 60:
            warnings.append("Top composite score is unusually low — check data freshness")

    if warnings:
        lines.append("## Data Quality Flags")
        lines.append("")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")


def _write_value_section(lines: list, value_bets: list, top_n: int = 8):
    """Write a value bet section with odds and EV.

    Separates positive-EV bets (true value) from negative-EV bets
    (closest to value). When no positive-EV bets exist, shows the
    closest-to-value options with a clear label.
    """
    positive_ev = [vb for vb in value_bets if vb.get("is_value")]
    negative_ev = [vb for vb in value_bets if not vb.get("is_value")]

    if positive_ev:
        for vb in positive_ev[:top_n]:
            # Skip suspicious entries (model/market prob wildly different)
            if vb.get("suspicious") or vb.get("ev_capped"):
                continue
            better = ""
            if vb.get("better_odds_note"):
                better = f" *(better: {vb['better_odds_note']})*"
            # Use more decimal places for small probabilities
            model_fmt = _fmt_prob(vb['model_prob'])
            market_fmt = _fmt_prob(vb['market_prob'])
            lines.append(
                f"- **VALUE** **{vb['player_display']}** "
                f"(#{vb['rank']}) — "
                f"{_fmt_odds(vb['best_odds'])} @ {vb['best_book']}, "
                f"model {model_fmt} vs market {market_fmt}, "
                f"EV {vb['ev_pct']}{better}"
            )
        lines.append("")
    else:
        book = value_bets[0].get("best_book", "market") if value_bets else "market"
        lines.append(f"*No positive-EV bets found at {book}. Closest to value:*")
        lines.append("")

    # Show negative-EV bets (closest to value) if we have room
    remaining = top_n - len(positive_ev)
    if remaining > 0 and negative_ev:
        for vb in negative_ev[:remaining]:
            if vb.get("suspicious") or vb.get("ev_capped"):
                continue
            better = ""
            if vb.get("better_odds_note"):
                better = f" *(better: {vb['better_odds_note']})*"
            model_fmt = _fmt_prob(vb['model_prob'])
            market_fmt = _fmt_prob(vb['market_prob'])
            lines.append(
                f"- **{vb['player_display']}** "
                f"(#{vb['rank']}) — "
                f"{_fmt_odds(vb['best_odds'])} @ {vb['best_book']}, "
                f"model {model_fmt} vs market {market_fmt}, "
                f"EV {vb['ev_pct']}{better}"
            )
        lines.append("")


def _write_adaptation_status(lines: list):
    """Add market adaptation state table to the card."""
    try:
        from src.adaptation import get_adaptation_state

        markets = ["outright", "top5", "top10", "top20", "matchup"]
        rows = []
        for market in markets:
            state = get_adaptation_state(market)
            ev_thr = state.get("ev_threshold")
            ev_str = f"{ev_thr:.0%}" if ev_thr is not None else "suppressed"
            stake = state.get("stake_multiplier", 1.0)
            bets = state.get("total_bets", 0)
            rows.append(
                f"| {market} | {state['state']} | {ev_str} | {stake}u | {bets} |"
            )

        lines.append("## Market Adaptation Status")
        lines.append("")
        lines.append("| Market | State | EV Threshold | Stake | Bets Tracked |")
        lines.append("|--------|-------|-------------|-------|--------------|")
        for row in rows:
            lines.append(row)
        lines.append("")
    except Exception as e:
        logger.warning("Adaptation status unavailable: %s", e)


def _write_matchup_value_bets(lines: list, matchup_bets: list[dict] | None):
    """Add matchup value bets section, split by tournament vs round matchups."""
    if not matchup_bets:
        lines.append("## Matchup Value Bets (Real Odds)")
        lines.append("")
        lines.append("*No matchup value bets available this week.*")
        lines.append("")
        return

    tournament_matchups = [b for b in matchup_bets if b.get("market_type") == "tournament_matchups"]
    round_matchups = [b for b in matchup_bets if b.get("market_type") == "round_matchups"]
    other_matchups = [b for b in matchup_bets if b.get("market_type") not in ("tournament_matchups", "round_matchups")]

    def _write_matchup_table(bets: list[dict]):
        lines.append("| Pick | vs | Odds | Model Win% | EV | Conviction | Tier | Book | Why |")
        lines.append("|------|-----|------|------------|-----|------------|------|------|-----|")
        for bet in bets:
            odds = bet.get("odds", 0)
            odds_str = f"+{odds}" if odds > 0 else str(odds)
            model_pct = f"{bet.get('model_win_prob', 0):.1%}"
            ev_pct = bet.get("ev_pct", "")
            conviction = bet.get("conviction", "—")
            conviction_str = str(conviction) if conviction is not None else "—"
            tier = bet.get("tier", "LEAN")
            book = bet.get("book", "—")
            reason = bet.get("reason", "composite edge")
            if bet.get("momentum_aligned"):
                pick_mom = bet.get("pick_momentum", 50)
                opp_mom = bet.get("opp_momentum", 50)
                reason += f"; momentum ↑{pick_mom:.0f}/↓{opp_mom:.0f}"
            lines.append(
                f"| **{bet['pick']}** | {bet['opponent']} "
                f"| {odds_str} | {model_pct} | {ev_pct} | {conviction_str} | {tier} | {book} | {reason} |"
            )
        lines.append("")

    if tournament_matchups:
        lines.append("## Tournament Matchups (72-hole)")
        lines.append("")
        _write_matchup_table(tournament_matchups)

    if round_matchups:
        lines.append("## Round Matchups (per-round)")
        lines.append("")
        lines.append("*Shorter variance window — settle after each round.*")
        lines.append("")
        _write_matchup_table(round_matchups)

    if other_matchups:
        lines.append("## Other Matchups")
        lines.append("")
        _write_matchup_table(other_matchups)

    if not tournament_matchups and not round_matchups and not other_matchups:
        lines.append("## Matchup Value Bets")
        lines.append("")
        lines.append("*No matchup value bets available this week.*")
        lines.append("")
