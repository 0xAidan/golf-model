"""
Betting Card Generator

Produces a short, digestible markdown betting card.
Bet types: Outright, Top 5, Top 10, Top 20, Matchups, 72-hole groups.
No DFS.
"""

import logging
import os
from datetime import datetime

from src import config
from src.feature_flags import is_enabled

logger = logging.getLogger("card")


def _american_to_decimal(american: int) -> float:
    """Convert American odds to decimal for stake calculation."""
    if not american:
        return 1.0
    if american > 0:
        return 1.0 + american / 100.0
    return 1.0 + 100.0 / abs(american)


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
    """Collect top 3 bets by EV across placement and matchups for exec summary."""
    candidates = []
    for bet_type, bets in (value_bets or {}).items():
        for b in bets:
            if not b.get("is_value") or b.get("suspicious") or b.get("ev_capped"):
                continue
            ev = b.get("ev", 0) or 0
            ev_pct = b.get("ev_pct", "0%")
            if isinstance(ev_pct, (int, float)):
                ev_pct = f"{ev_pct:.1f}%"
            odds_str = _fmt_odds(b.get("best_odds", 0))
            stake = None
            if is_enabled("kelly_sizing") or is_enabled("kelly_stakes"):
                try:
                    from src.kelly import units_for_bet
                    dec = _american_to_decimal(b.get("best_odds", 0))
                    stake = units_for_bet(b.get("model_prob", 0.5), dec)
                except Exception:
                    pass
            candidates.append({
                "ev": ev, "pick": b.get("player_display", ""), "market": bet_type,
                "odds": odds_str, "ev_pct": ev_pct, "tier": "—", "stake": stake,
            })
    if matchup_bets:
        for b in matchup_bets:
            ev = b.get("ev", 0) or 0
            ev_pct = b.get("ev_pct", "")
            if isinstance(ev_pct, (int, float)):
                ev_pct = f"{ev_pct:.1f}%"
            odds_str = f"+{b.get('odds', 0)}" if (b.get("odds") or 0) > 0 else str(b.get("odds", 0))
            stake = None
            candidates.append({
                "ev": ev, "pick": b.get("pick", ""), "market": "matchup",
                "odds": odds_str, "ev_pct": ev_pct, "tier": b.get("tier", "LEAN"), "stake": stake,
            })
    candidates.sort(key=lambda x: x["ev"], reverse=True)
    return candidates[:3]


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
                  matchup_bets: list[dict] = None) -> str:
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

    lines = []
    lines.append(f"# {tournament_name} — Betting Card")
    lines.append(f"**Course:** {course_name}")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
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

    # ── Section 1: Exec Summary (always visible) ─────────────────
    lines.append("## 3 Best Bets")
    lines.append("")
    best_three = _top_bets_for_summary(value_bets, matchup_bets)
    if best_three:
        show_stake = is_enabled("kelly_sizing") or is_enabled("kelly_stakes")
        header = "| Pick | Market | Odds | EV% | Tier |"
        if show_stake:
            header += " Stake |"
        lines.append(header)
        lines.append("|------|--------|------|-----|------|" + ("--------|" if show_stake else ""))
        for row in best_three:
            stake_str = ""
            if show_stake:
                s = row.get("stake")
                stake_str = f" {s:.2f}u |" if s is not None else " — |"
            lines.append(
                f"| **{row['pick']}** | {row['market']} | {row['odds']} | {row['ev_pct']} | {row.get('tier', '—')} |" + stake_str
            )
    else:
        lines.append("*No value bets above threshold this week.*")
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

    lines.append("<details>")
    lines.append("<summary>Matchup Value Bets</summary>")
    lines.append("")
    _write_matchup_value_bets(lines, matchup_bets)
    lines.append("</details>")
    lines.append("")

    lines.append("<details>")
    lines.append("<summary>Value Picks: Placement Markets</summary>")
    lines.append("")
    lines.append("## Value Picks: Placement Markets")
    lines.append("")

    top10_vb = value_bets.get("top10", [])
    top20_vb = value_bets.get("top20", [])

    lines.append("### Top 10 Finish")
    lines.append("")
    if top10_vb:
        _write_value_section(lines, top10_vb, top_n=6)
    else:
        lines.append("*No odds data available for Top 10.*")
        lines.append("")

    lines.append("### Top 20 Finish")
    lines.append("")
    if top20_vb:
        _write_value_section(lines, top20_vb, top_n=8)
    else:
        lines.append("*No odds data available for Top 20.*")
    lines.append("")
    lines.append("</details>")
    lines.append("")

    lines.append("<details>")
    lines.append("<summary>Speculative: Outright / Top 5</summary>")
    lines.append("")
    lines.append("## Speculative Picks: Outright / Top 5")
    lines.append("")
    lines.append("*High variance markets. Positive EV threshold raised to 5% to filter noise.*")
    lines.append("")

    lines.append("### Outright Winner")
    lines.append("")
    outright_vb = value_bets.get("outright", [])
    if outright_vb:
        _write_value_section(lines, outright_vb, top_n=5)
    else:
        lines.append("*No odds data available. Top 5 by model:*")
        lines.append("")
        for r in composite_results[:5]:
            lines.append(f"- **{r['player_display']}** — {_reason(r)}")
        lines.append("")

    lines.append("### Top 5 Finish")
    lines.append("")
    top5_vb = value_bets.get("top5", [])
    if top5_vb:
        _write_value_section(lines, top5_vb, top_n=5)
    else:
        lines.append("*No odds data available for Top 5.*")
    lines.append("")
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

    lines.append("<details>")
    lines.append("<summary>3-Ball Markets</summary>")
    lines.append("")
    lines.append("## 3-Ball")
    lines.append("")
    three_ball = value_bets.get("3ball", [])
    if three_ball and any(b.get("is_value") for b in three_ball):
        _write_value_section(lines, three_ball, top_n=10)
    else:
        lines.append("*No 3-ball odds this week. When available: softmax over 3 players, blend 70/30 with DG.*")
    lines.append("")
    lines.append("</details>")
    lines.append("")

    # ── Footer ────────────────────────────────────────────────
    lines.append("---")
    ai_tag = " AI-adjusted." if ai_pre_analysis else ""
    lines.append(f"*Model v{config.MODEL_VERSION}: {len(composite_results)} players scored. "
                 f"Course data: {'Yes' if any(r.get('course_rounds', 0) > 0 for r in composite_results) else 'No'}."
                 f"{ai_tag} Weights: 45% course fit / 45% form / 10% momentum."
                 f" DG blend: market-specific (80-90% DG).*")

    # Write to file
    os.makedirs(output_dir, exist_ok=True)
    safe_name = tournament_name.lower().replace(" ", "_").replace("'", "")
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
    """Add matchup value bets section (real sportsbook odds)."""
    if not matchup_bets:
        return

    lines.append("## Matchup Value Bets (Real Odds)")
    lines.append("")
    lines.append("*Only matchups with actual sportsbook odds shown.*")
    lines.append("")
    lines.append("| Pick | vs | Odds | Model Win% | EV | Tier | Book | State |")
    lines.append("|------|-----|------|------------|-----|------|------|-------|")

    for bet in matchup_bets:
        odds = bet.get("odds", 0)
        odds_str = f"+{odds}" if odds > 0 else str(odds)
        model_pct = f"{bet.get('model_win_prob', 0):.1%}"
        ev_pct = bet.get("ev_pct", "")
        tier = bet.get("tier", "LEAN")
        book = bet.get("book", "—")
        state = bet.get("adaptation_state", "normal")
        lines.append(
            f"| **{bet['pick']}** | {bet['opponent']} | {odds_str} "
            f"| {model_pct} | {ev_pct} | {tier} | {book} | {state} |"
        )
    lines.append("")
