"""
Betting Card Generator

Produces a short, digestible markdown betting card.
Bet types: Outright, Top 5, Top 10, Top 20, Matchups, 72-hole groups.
No DFS.
"""

import os
from datetime import datetime

from src.matchups import find_best_matchups, group_by_confidence


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
                  ai_decisions: dict = None) -> str:
    """
    Generate a markdown betting card.

    composite_results: from composite.compute_composite()
    value_bets: dict keyed by bet_type ('outright', 'top5', etc.)
                each value is a list from value.find_value_bets()
    ai_pre_analysis: AI pre-tournament analysis (optional)
    ai_decisions: AI betting decisions (optional)

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

    # ── Weekly Strategy Summary ────────────────────────────────
    _write_weekly_strategy(lines, value_bets)

    # ── 1. Model Rankings (Top 20) ─────────────────────────────
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

    # ── 2. CORE: Matchup Edges (strongest signal) ──────────────
    lines.append("## Core Picks: Matchup Edges")
    lines.append("")
    lines.append("*Matchups are the model's strongest signal (12-3-1, +8.01u over last 2 events).*")
    lines.append("")

    matchup_course_profile = None
    matchups = find_best_matchups(composite_results, course_profile=matchup_course_profile)
    grouped = group_by_confidence(matchups)

    for tier_name, tier_label in [("strong", "STRONG"), ("moderate", "MODERATE"), ("lean", "LEAN")]:
        tier_matchups = grouped.get(tier_name, [])
        if tier_matchups:
            lines.append(f"**{tier_label} Confidence:**")
            lines.append("")
            for m in tier_matchups:
                lines.append(
                    f"- **{m['pick']}** over {m['opponent']} — "
                    f"edge: {m['edge_score']:.2f} ({m['reason']})"
                )
            lines.append("")

    if not matchups:
        lines.append("*No matchups above minimum edge threshold.*")
        lines.append("")

    # ── 3. VALUE: Top 10 / Top 20 Placements ──────────────────
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

    # ── 4. SPECULATIVE: Outright / Top 5 / FRL ────────────────
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

    # ── 5. AI Analysis (narrative only) ───────────────────────
    if ai_pre_analysis:
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

    # ── 6. Fades ──────────────────────────────────────────────
    lines.append("## Fades (Avoid)")
    lines.append("")
    lines.append("Players likely overpriced or in poor form:")
    lines.append("")
    for r in composite_results[-10:]:
        if r.get("momentum_direction") == "cold" or r["composite"] < 40:
            lines.append(f"- **{r['player_display']}** — composite {r['composite']:.1f}, {_reason(r)}")
    lines.append("")

    # ── 7. Data Quality & Methodology ─────────────────────────
    _write_data_quality(lines, value_bets, composite_results)

    # ── Footer ────────────────────────────────────────────────
    lines.append("---")
    ai_tag = " AI-adjusted." if ai_pre_analysis else ""
    lines.append(f"*Model v3.0: {len(composite_results)} players scored. "
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


def _suggest_matchups(composite_results: list[dict], min_gap: float = 3.0) -> list[dict]:
    """
    DEPRECATED: Use src.matchups.find_best_matchups() instead.

    Simple matchup finder using only composite gap. Kept as fallback.
    """
    matchups = []
    n = len(composite_results)

    for i in range(n):
        for j in range(i + 1, min(i + 30, n)):
            a = composite_results[i]
            b = composite_results[j]
            gap = a["composite"] - b["composite"]
            if gap < min_gap:
                continue

            # Build a reason for the edge
            reasons = []
            if a["course_fit"] - b["course_fit"] > 5:
                reasons.append(f"course fit +{a['course_fit'] - b['course_fit']:.0f}")
            if a["form"] - b["form"] > 5:
                reasons.append(f"form +{a['form'] - b['form']:.0f}")
            if a.get("momentum_direction") == "hot" and b.get("momentum_direction") in ("cold", "cooling"):
                reasons.append("momentum advantage")

            matchups.append({
                "pick": a["player_display"],
                "pick_key": a["player_key"],
                "opponent": b["player_display"],
                "opponent_key": b["player_key"],
                "edge": gap,
                "reason": "; ".join(reasons) if reasons else f"composite +{gap:.0f}",
            })

    # Sort by edge, take best
    matchups.sort(key=lambda x: x["edge"], reverse=True)

    # Deduplicate: each player only appears once as "pick"
    seen = set()
    deduped = []
    for m in matchups:
        if m["pick_key"] not in seen and m["opponent_key"] not in seen:
            deduped.append(m)
            seen.add(m["pick_key"])
            seen.add(m["opponent_key"])
    return deduped
