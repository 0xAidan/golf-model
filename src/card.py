"""
Betting Card Generator

Produces a short, digestible markdown betting card.
Bet types: Outright, Top 5, Top 10, Top 20, Matchups, 72-hole groups.
No DFS.
"""

import os
from datetime import datetime


def _fmt_odds(price: int) -> str:
    if price > 0:
        return f"+{price}"
    return str(price)


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
                  output_dir: str = "output") -> str:
    """
    Generate a markdown betting card.

    composite_results: from composite.compute_composite()
    value_bets: dict keyed by bet_type ('outright', 'top5', etc.)
                each value is a list from value.find_value_bets()

    Returns the file path of the generated card.
    """
    if value_bets is None:
        value_bets = {}

    lines = []
    lines.append(f"# {tournament_name} — Betting Card")
    lines.append(f"**Course:** {course_name}")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # ── Quick Reference: Top 15 Composite Rankings ──────────────
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

    # ── Outright ────────────────────────────────────────────────
    lines.append("## Outright Winner")
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

    # ── Top 5 ──────────────────────────────────────────────────
    lines.append("## Top 5 Finish")
    lines.append("")
    top5_vb = value_bets.get("top5", [])
    if top5_vb:
        _write_value_section(lines, top5_vb, top_n=5)
    else:
        lines.append("*Top 5 picks by model:*")
        lines.append("")
        for r in composite_results[:8]:
            lines.append(f"- **{r['player_display']}** — {_reason(r)}")
        lines.append("")

    # ── Top 10 ─────────────────────────────────────────────────
    lines.append("## Top 10 Finish")
    lines.append("")
    top10_vb = value_bets.get("top10", [])
    if top10_vb:
        _write_value_section(lines, top10_vb, top_n=6)
    else:
        lines.append("*Top 10 picks by model:*")
        lines.append("")
        for r in composite_results[:12]:
            lines.append(f"- **{r['player_display']}** — {_reason(r)}")
        lines.append("")

    # ── Top 20 ─────────────────────────────────────────────────
    lines.append("## Top 20 Finish")
    lines.append("")
    top20_vb = value_bets.get("top20", [])
    if top20_vb:
        _write_value_section(lines, top20_vb, top_n=8)
    else:
        lines.append("*Top 20 picks by model:*")
        lines.append("")
        for r in composite_results[:20]:
            lines.append(f"- **{r['player_display']}** — {_reason(r)}")
        lines.append("")

    # ── Matchup Edges ──────────────────────────────────────────
    lines.append("## Matchup Edges")
    lines.append("")
    lines.append("Best head-to-head edges based on composite score gap:")
    lines.append("")
    matchups = _suggest_matchups(composite_results)
    for m in matchups[:8]:
        lines.append(
            f"- **{m['pick']}** over {m['opponent']} — "
            f"edge: {m['edge']:.1f} pts ({m['reason']})"
        )
    lines.append("")

    # ── Fades ──────────────────────────────────────────────────
    lines.append("## Fades (Avoid)")
    lines.append("")
    lines.append("Players likely overpriced or in poor form:")
    lines.append("")
    for r in composite_results[-10:]:
        if r.get("momentum_direction") == "cold" or r["composite"] < 40:
            lines.append(f"- **{r['player_display']}** — composite {r['composite']:.1f}, {_reason(r)}")
    lines.append("")

    # ── Model Info ─────────────────────────────────────────────
    lines.append("---")
    lines.append(f"*Model: {len(composite_results)} players scored. "
                 f"Course data: {'Yes' if any(r.get('course_rounds', 0) > 0 for r in composite_results) else 'No'}.*")

    # Write to file
    os.makedirs(output_dir, exist_ok=True)
    safe_name = tournament_name.lower().replace(" ", "_").replace("'", "")
    filename = f"{safe_name}_{datetime.now().strftime('%Y%m%d')}.md"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w") as f:
        f.write("\n".join(lines))

    return filepath


def _write_value_section(lines: list, value_bets: list, top_n: int = 5):
    """Write a value bet section with odds and EV."""
    shown = 0
    for vb in value_bets:
        if shown >= top_n:
            break
        tag = "**VALUE** " if vb.get("is_value") else ""
        lines.append(
            f"- {tag}**{vb['player_display']}** "
            f"(#{vb['rank']}) — "
            f"odds {_fmt_odds(vb['best_odds'])} ({vb['best_book']}), "
            f"model {vb['model_prob']:.1%} vs market {vb['market_prob']:.1%}, "
            f"EV {vb['ev_pct']}"
        )
        shown += 1
    lines.append("")


def _suggest_matchups(composite_results: list[dict], min_gap: float = 3.0) -> list[dict]:
    """
    Find the best matchup edges by pairing players with large
    composite score differences who are similarly priced.
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
    return deduped
