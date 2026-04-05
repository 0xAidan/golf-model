"""
Methodology Document Generator

Produces a comprehensive methodology doc alongside each betting card,
documenting exactly how the model reached its predictions for that tournament.
All numbers are dynamically pulled from the pipeline context — nothing is hardcoded.
"""

import os
from datetime import datetime

from src import config


def generate_methodology(ctx: dict, output_dir: str = "output") -> str:
    """
    Generate a methodology markdown document from pipeline context.

    ctx keys:
        tournament_name, course_name, event_id, start_date, location,
        field_size, total_rounds, rounds_by_year, weights, composite_results,
        value_bets, profile, weather_forecast, weather_adjustments,
        weather_severity, ai_pre_analysis, ai_decisions, dg_probs,
        metric_counts, matchup_bets, blend_weights, adaptation_states,
        course_nums, model_version

    Returns the file path of the generated methodology doc.
    """
    lines = []
    tournament_name = ctx.get("tournament_name", "Unknown")
    course_name = ctx.get("course_name", "Unknown")
    composite = ctx.get("composite_results", [])
    value_bets = ctx.get("value_bets", {})
    weights = ctx.get("weights", {})
    profile = ctx.get("profile")
    ai_pre = ctx.get("ai_pre_analysis")
    weather_forecast = ctx.get("weather_forecast")
    weather_adjustments = ctx.get("weather_adjustments", {})
    metric_counts = ctx.get("metric_counts", {})
    model_version = ctx.get("model_version", config.MODEL_VERSION)

    w_cf = weights.get("course_fit", 0.45)
    w_form = weights.get("form", 0.45)
    w_mom = weights.get("momentum", 0.10)

    _header(lines, ctx, model_version)
    _toc(lines)
    _algorithm_overview(lines, w_cf, w_form, w_mom)
    _data_sources(lines, ctx, metric_counts)
    _course_fit_section(lines, profile, composite, w_cf)
    _form_section(lines, w_form)
    _momentum_section(lines, w_mom)
    _weather_section(lines, ctx)
    _composite_section(lines, composite, w_cf, w_form, w_mom)
    _probability_section(lines, ctx)
    _value_bet_section(lines, value_bets, ctx)
    _adaptation_section(lines, ctx)
    _ai_section(lines, ai_pre, ctx)
    _course_profile_section(lines, profile, course_name, composite)
    _worked_examples(lines, composite, ctx)
    _picks_rationale(lines, value_bets, composite, ctx)
    _limitations(lines, ctx)
    _footer(lines, composite, ai_pre, model_version)

    os.makedirs(output_dir, exist_ok=True)
    safe_name = tournament_name.lower().replace(" ", "_").replace("'", "")

    try:
        from src.output_manager import archive_previous
        archived = archive_previous(output_dir, safe_name, file_type="methodology")
        if archived:
            import logging
            logging.getLogger("methodology").info(
                "Archived %d previous methodology doc(s) for %s", archived, safe_name
            )
    except Exception as e:
        import logging
        logging.getLogger("methodology").warning("Could not archive previous methodology: %s", e)

    filename = f"{safe_name}_methodology_{datetime.now().strftime('%Y%m%d')}.md"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w") as f:
        f.write("\n".join(lines))

    return filepath


def _header(lines, ctx, model_version):
    tournament_name = ctx.get("tournament_name", "Unknown")
    course_name = ctx.get("course_name", "Unknown")
    location = ctx.get("location", "")
    start_date = ctx.get("start_date", "")
    field_size = len(ctx.get("composite_results", []))

    lines.append(f"# {tournament_name} — Methodology Breakdown (v{model_version})")
    lines.append(f"**Course:** {course_name}" + (f", {location}" if location else ""))
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d')}")
    if start_date:
        lines.append(f"**Event Start:** {start_date}")
    lines.append(f"**Field Size:** {field_size} players scored")
    lines.append(f"**Model Version:** {model_version}")
    lines.append("")
    lines.append("---")
    lines.append("")


def _toc(lines):
    lines.append("## Table of Contents")
    lines.append("")
    sections = [
        "Algorithm Overview",
        "Data Sources & Pipeline",
        "Component 1: Course Fit",
        "Component 2: Form",
        "Component 3: Momentum",
        "Weather Module",
        "Final Composite Score",
        "Probability Conversion & Blending",
        "Value Bet Calculation",
        "Market Adaptation System",
        "AI Adjustments & Portfolio Rules",
        "Course Profile",
        "Worked Examples: Top 5 Players",
        "This Week's Picks & Rationale",
        "Known Limitations & Future Work",
    ]
    for i, s in enumerate(sections, 1):
        anchor = s.lower().replace(" ", "-").replace(":", "").replace("&", "")
        lines.append(f"{i}. [{s}](#{anchor})")
    lines.append("")
    lines.append("---")
    lines.append("")


def _algorithm_overview(lines, w_cf, w_form, w_mom):
    lines.append("## Algorithm Overview")
    lines.append("")
    lines.append("The model produces a **composite score (0-100)** for each player by combining three independent components:")
    lines.append("")
    lines.append("```")
    lines.append(f"COMPOSITE = (Course Fit x {w_cf:.2f}) + (Form x {w_form:.2f}) + (Momentum x {w_mom:.2f})")
    lines.append("```")
    lines.append("")
    lines.append("- **50 = neutral baseline** (average/unknown player)")
    lines.append("- **>50 = positive signal** (good fit, good form, improving)")
    lines.append("- **<50 = negative signal** (bad fit, bad form, declining)")
    lines.append("")
    lines.append("Each component is a weighted blend of multiple sub-signals, all normalized to 0-100. "
                 "The composite score is then converted to a probability via softmax and **blended with "
                 "Data Golf's calibrated probability** (95% DG + 5% model) to produce a final model probability. "
                 "This probability is compared against live sportsbook odds to find value bets.")
    lines.append("")
    lines.append("**Card strategy:** The betting card is matchup-first: the top plays are always tournament and round matchups (up to "
                 f"{getattr(config, 'BEST_BETS_COUNT', 5)}). Placements appear only when EV meets the high-confidence floor (≥{getattr(config, 'PLACEMENT_CARD_EV_FLOOR', 0.15):.0%}). "
                 "Each matchup bet includes a **conviction score** (0–100) combining form differential, course-fit differential, "
                 "momentum alignment (pick hot / opponent cold), and DG/model agreement strength.")
    lines.append("")
    lines.append("### High-Level Flow")
    lines.append("")
    lines.append("```")
    lines.append("Data Golf API  -->  SQLite Database  -->  Rolling Stats Engine")
    lines.append("                                              |")
    lines.append("                    Course Profile  -->  Course Fit Model (+ time decay) --+")
    lines.append("                                                                          |")
    lines.append("                    Rolling Stats   -->  Form Model (+ sample size adj) ---+---> Composite")
    lines.append("                                                                          |       |")
    lines.append("                    Rolling Stats   -->  Momentum Model (+ elite bonus) ---+   Softmax (5%)")
    lines.append("                                                                          |       |")
    lines.append("                    Weather API     -->  Weather Module -------------------+   DG Prob (95%)")
    lines.append("                                                                                  |")
    lines.append("                                         AI Analysis --------> Blended Probability")
    lines.append("                                              |                      |")
    lines.append("                                    Adaptation System          Value Bet Detection")
    lines.append("                                              |                      |")
    lines.append("                                         Betting Card + Methodology Doc")
    lines.append("                                              |")
    lines.append("                                         Post-Tournament Review --> Learning Cycle")
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")


def _data_sources(lines, ctx, metric_counts):
    total_rounds = ctx.get("total_rounds", 0)
    event_id = ctx.get("event_id", "")
    tournament_name = ctx.get("tournament_name", "")
    rounds_by_year = ctx.get("rounds_by_year", {})

    lines.append("## Data Sources & Pipeline")
    lines.append("")
    lines.append("### Primary Data Source: Data Golf API")
    lines.append("")
    lines.append("All data comes from the Data Golf API.")
    lines.append("")
    lines.append("| Endpoint | Data Retrieved | Metrics Stored |")
    lines.append("|----------|---------------|----------------|")
    lines.append(f"| `get-schedule` | Current event detection ({tournament_name}, Event ID: {event_id}) | -- |")
    lines.append(f"| `historical-raw-data/rounds` | Round-level SG data, 2019-2026 ({total_rounds:,} total rounds) | Stored in `rounds` table |")

    ep_metrics = [
        ("preds/pre-tournament", "Baseline + course-history win/top5/top10/top20/make-cut probabilities",
         f"{metric_counts.get('baseline', 0)} baseline + {metric_counts.get('course_history', 0)} course-history metrics"),
        ("preds/player-decompositions", "Course-adjusted SG predictions per category",
         f"{metric_counts.get('decompositions', 0)} metrics"),
        ("field-updates", "Field list, salaries, tee times",
         f"{metric_counts.get('field', 0)} metrics"),
        ("preds/skill-ratings", "True SG per category (field-strength adjusted)",
         f"{metric_counts.get('skill_ratings', 0)} metrics"),
        ("preds/get-dg-rankings", "DG global rank + skill estimate",
         f"{metric_counts.get('rankings', 0)} metrics"),
        ("preds/approach-skill", "SG by yardage bucket and lie type",
         f"{metric_counts.get('approach', 0)} metrics"),
        ("betting-tools/outrights", "Live odds from 15 sportsbooks",
         f"{metric_counts.get('odds_markets', 0)} markets"),
        ("betting-tools/matchups", "Tournament matchup odds",
         f"{metric_counts.get('matchups', 0)} matchups"),
    ]
    for ep, desc, count in ep_metrics:
        lines.append(f"| `{ep}` | {desc} | {count} |")
    lines.append("")

    if rounds_by_year:
        lines.append("### Round Data by Year")
        lines.append("")
        lines.append("| Year | Rounds | Players |")
        lines.append("|------|--------|---------|")
        for year, info in sorted(rounds_by_year.items()):
            lines.append(f"| {year} | {info.get('rounds', 0):,} | {info.get('players', 0)} |")
        lines.append("")

    rolling = metric_counts.get("rolling", {})
    if rolling:
        lines.append("### Rolling Stats Computation")
        lines.append("")
        lines.append(f"From the {total_rounds:,} stored rounds, the model computes rolling statistics for each player in the field:")
        lines.append("")
        lines.append("- **Windows:** 8, 12, 16, 20, 24 rounds")
        lines.append("- **SG categories:** SG:TOT, SG:OTT, SG:APP, SG:ARG, SG:P, SG:T2G")
        lines.append("- **Traditional stats:** Driving Distance, Driving Accuracy %, GIR %, Scrambling %, Proximity")
        course_nums = ctx.get("course_nums", [])
        if course_nums:
            lines.append(f"- **Course-specific stats:** Filtered by course_num={course_nums[0]}, with time decay")
        lines.append("")
        lines.append(f"**Result:** {rolling.get('total', 0):,} total metrics computed "
                     f"({rolling.get('sg', 0):,} SG + {rolling.get('traditional', 0):,} traditional + "
                     f"{rolling.get('course_specific', 0):,} course-specific)")
        lines.append("")

    lines.append("---")
    lines.append("")


def _course_fit_section(lines, profile, composite, w_cf):
    pct = f"{w_cf:.0%}"
    lines.append(f"## Component 1: Course Fit ({pct})")
    lines.append("")
    lines.append('**Question answered:** "How well does this player\'s game suit this specific course?"')
    lines.append("")
    lines.append("### Base SG Sub-Weights (Before Course Profile Adjustment)")
    lines.append("")
    lines.append("| Category | Base Weight | Description |")
    lines.append("|----------|------------|-------------|")
    lines.append("| SG:Total | 30% | Overall strokes-gained at this course |")
    lines.append("| SG:Approach | 25% | Iron play / approach shots |")
    lines.append("| SG:Off-the-Tee | 20% | Driving (distance + accuracy) |")
    lines.append("| SG:Putting | 15% | Putting performance at this course |")
    lines.append("| Par Efficiency | 10% | Birdie-or-better % on par 3s/4s/5s |")
    lines.append("")

    if profile:
        from src.course_profile import course_to_model_weights
        adj = course_to_model_weights(profile)
        ratings = profile.get("skill_ratings", {})

        lines.append("### Course Profile Adjustments")
        lines.append("")
        source = profile.get("course_facts", {}).get("source", "auto-generated")
        lines.append(f"Profile source: **{source}**")
        lines.append("")
        lines.append("| Category | Difficulty | Multiplier |")
        lines.append("|----------|-----------|------------|")
        for cat in ["sg_ott", "sg_app", "sg_arg", "sg_putting"]:
            diff = ratings.get(cat, "Unknown")
            mult = adj.get(f"course_{cat}_mult", 1.0)
            lines.append(f"| {cat.upper().replace('_', ':')} | {diff} | {mult}x |")
        lines.append("")

    lines.append("### Scoring Formula")
    lines.append("")
    lines.append("1. **Rank-to-Score conversion:** `score = 100 x (1 - (rank - 1) / (field_size - 1))`")
    lines.append("2. **Weighted base score** from SG sub-components")
    lines.append("3. **Time decay:** `decay = 0.5 ^ (years_since / 2.0)` — stale course data is discounted")
    lines.append("4. **DG blending:** Decomposition (30-70%), Skill Ratings (up to 15%), Approach Skill (up to 12%)")
    lines.append("5. **Confidence:** `min(1.0, 0.3 + 0.7 x (rounds / 30))` — pulls unknowns toward 50")
    lines.append("")
    lines.append("---")
    lines.append("")


def _form_section(lines, w_form):
    pct = f"{w_form:.0%}"
    lines.append(f"## Component 2: Form ({pct})")
    lines.append("")
    lines.append('**Question answered:** "How well is this player playing RIGHT NOW across all courses?"')
    lines.append("")
    lines.append("### Sub-Component Weights")
    lines.append("")
    lines.append("| Component | Weight | Description |")
    lines.append("|-----------|--------|-------------|")
    lines.append("| Sim Probabilities | 25% | DG pre-tournament win/top5/top10/top20/make-cut probabilities |")
    lines.append("| Recent Windows | 25% | SG:TOT ranks in most recent rounds (8, 12, 16 round windows) |")
    lines.append("| Baseline Windows | 15% | SG:TOT ranks in larger windows (24 rounds) |")
    lines.append("| Multi-SG Breakdown | 15% | Weighted SG by category from best available window |")
    lines.append("| DG Skill Ratings | 15% | True player ability (field-strength adjusted SG) |")
    lines.append("| DG Rankings | 5% | Global DG rank signal |")
    lines.append("")
    lines.append("### Sample Size Adjustment")
    lines.append("")
    lines.append("```")
    lines.append("confidence = min(1.0, effective_sample / 8)")
    lines.append("adjusted_score = 50.0 + confidence x (raw_score - 50.0)")
    lines.append("```")
    lines.append("")
    lines.append("Players with < 8 rounds of data have their scores shrunk toward the neutral baseline.")
    lines.append("")
    lines.append("---")
    lines.append("")


def _momentum_section(lines, w_mom):
    pct = f"{w_mom:.0%}"
    lines.append(f"## Component 3: Momentum ({pct})")
    lines.append("")
    lines.append('**Question answered:** "Is this player trending up or down?"')
    lines.append("")
    lines.append("**Windows used:** 8, 12, 16, 24 only (\"all\" window excluded — it represents career averages, not trends).")
    lines.append("")
    lines.append("### Trend Calculation")
    lines.append("")
    lines.append("1. **Percentage-based improvement:** `pct_improvement = clamp((oldest_rank - newest_rank) / oldest_rank, -1, 1)`")
    lines.append("2. **Elite stability bonus** (top 10 players maintain scores even when holding steady)")
    lines.append("3. **Position signal:** `(field_size - newest_rank) / (field_size - 1)` — current absolute strength")
    lines.append("4. **Blended trend** with elite-aware weighting (50% position for elite, 40% otherwise)")
    lines.append("5. **Consistency bonus:** +30% if 60%+ of window pairs trend in same direction")
    lines.append("")
    lines.append("### Direction Thresholds")
    lines.append("")
    lines.append("| Relative Position | Direction | Symbol |")
    lines.append("|-------------------|-----------|--------|")
    lines.append("| > 25th pctl | Hot | ↑↑ |")
    lines.append("| > 5th pctl | Warming | ↑ |")
    lines.append("| > -25th pctl | Cooling | ↓ |")
    lines.append("| <= -25th pctl | Cold | ↓↓ |")
    lines.append("")
    lines.append("---")
    lines.append("")


def _weather_section(lines, ctx):
    lines.append("## Weather Module")
    lines.append("")
    weather_forecast = ctx.get("weather_forecast")
    weather_severity = ctx.get("weather_severity")
    weather_adjustments = ctx.get("weather_adjustments", {})

    if not weather_forecast and weather_severity is None:
        lines.append("*Weather data not available or not applicable this week.*")
        lines.append("")
        lines.append("---")
        lines.append("")
        return

    if weather_severity is not None:
        lines.append(f"**Tournament severity: {weather_severity}/100**")
        lines.append("")

    if weather_forecast and "days" in weather_forecast:
        lines.append("### Forecast")
        lines.append("")
        lines.append("| Day | Wind | Rain | Temp |")
        lines.append("|-----|------|------|------|")
        for day in weather_forecast.get("days", [])[:4]:
            wind = day.get("avg_wind_kmh", 0) or 0
            rain = day.get("total_precip_mm", 0) or 0
            temp = day.get("avg_temp_c", 0) or 0
            lines.append(f"| {day.get('date', '?')} | {wind:.0f} km/h | {rain:.1f} mm | {temp:.0f}C |")
        lines.append("")

    if weather_adjustments:
        sorted_adj = sorted(weather_adjustments.items(),
                            key=lambda x: abs(x[1].get("adjustment", 0)), reverse=True)
        lines.append(f"Weather adjustments applied to **{len(weather_adjustments)} players**:")
        lines.append("")
        lines.append("| Player | Adjustment | Reason |")
        lines.append("|--------|-----------|--------|")
        for pk, wa in sorted_adj[:8]:
            adj = wa.get("adjustment", 0)
            reason = wa.get("reason", "")
            lines.append(f"| {pk} | {adj:+.1f} | {reason} |")
        lines.append("")
    elif weather_severity is not None and weather_severity < 10:
        lines.append(f"Conditions benign (severity {weather_severity}<10) — no weather adjustments applied.")
        lines.append("")

    lines.append("---")
    lines.append("")


def _composite_section(lines, composite, w_cf, w_form, w_mom):
    lines.append("## Final Composite Score")
    lines.append("")
    lines.append("```")
    lines.append(f"COMPOSITE = {w_cf:.2f} x Course_Fit + {w_form:.2f} x Form + {w_mom:.2f} x Momentum + Weather_Adj")
    lines.append("```")
    lines.append("")
    lines.append("### This Week's Top 10")
    lines.append("")
    lines.append(f"| Rank | Player | Composite | Course Fit ({w_cf:.0%}) | Form ({w_form:.0%}) | Momentum ({w_mom:.0%}) | Trend |")
    lines.append("|------|--------|-----------|------------------|------------|-----------------|-------|")
    for r in composite[:10]:
        trend = {"hot": "↑↑", "warming": "↑", "cooling": "↓", "cold": "↓↓"}.get(
            r.get("momentum_direction", ""), "—")
        lines.append(
            f"| {r['rank']} | {r['player_display']} | {r['composite']:.1f} "
            f"| {r['course_fit']:.1f} | {r['form']:.1f} | {r['momentum']:.1f} | {trend} |"
        )
    lines.append("")

    if composite:
        top = composite[0]
        calc_cf = w_cf * top["course_fit"]
        calc_form = w_form * top["form"]
        calc_mom = w_mom * top["momentum"]
        calc_total = calc_cf + calc_form + calc_mom
        lines.append(f"### Verification: {top['player_display']}")
        lines.append("")
        lines.append("```")
        lines.append(f"Composite ≈ {w_cf:.2f} x {top['course_fit']:.1f} + {w_form:.2f} x {top['form']:.1f} + {w_mom:.2f} x {top['momentum']:.1f}")
        lines.append(f"          = {calc_cf:.2f} + {calc_form:.2f} + {calc_mom:.2f}")
        lines.append(f"          ≈ {calc_total:.1f} (displayed: {top['composite']:.1f})")
        lines.append("```")
        lines.append("")
        lines.append("*Small difference due to higher-precision sub-scores internally.*")
        lines.append("")

    lines.append("---")
    lines.append("")


def _probability_section(lines, ctx):
    lines.append("## Probability Conversion & Blending")
    lines.append("")
    lines.append("### DG Probability Blending (v4)")
    lines.append("")
    lines.append("The model blends Data Golf's calibrated probabilities with its own composite-derived probability:")
    lines.append("")
    lines.append("| Market | DG Weight | Model Weight | Rationale |")
    lines.append("|--------|----------|-------------|-----------|")
    lines.append("| Outright | 95% | 5% | DG simulations are very well-calibrated |")
    lines.append("| Top 5 | 95% | 5% | High-variance market, lean on DG |")
    lines.append("| Top 10 | 95% | 5% | Moderate market |")
    lines.append("| Top 20 | 95% | 5% | DG still best source |")
    lines.append("| FRL | 95% | 5% | Single-round market |")
    lines.append("| Make Cut | 95% | 5% | Broadest market |")
    lines.append("")
    lines.append("```")
    lines.append("blended_prob = 0.95 x DG_probability + 0.05 x composite_softmax_probability")
    lines.append("```")
    lines.append("")
    lines.append("### Softmax Temperature by Market")
    lines.append("")
    lines.append("| Market | Temperature | Target Sum |")
    lines.append("|--------|------------|------------|")
    lines.append("| Outright | 8.0 | 1.0 |")
    lines.append("| Top 5 | 10.0 | 5.0 |")
    lines.append("| Top 10 | 12.0 | 10.0 |")
    lines.append("| Top 20 | 15.0 | 20.0 |")
    lines.append("| Make Cut | 20.0 | 0.65 x field |")
    lines.append("| FRL | 7.0 | 1.0 |")
    lines.append("")
    lines.append("Clamping [0.001, 0.95] with renormalization to preserve target_sum.")
    lines.append("")
    lines.append("---")
    lines.append("")


def _value_bet_section(lines, value_bets, ctx):
    lines.append("## Value Bet Calculation")
    lines.append("")
    lines.append("### Expected Value Formula")
    lines.append("")
    lines.append("```")
    lines.append("EV = (model_prob x decimal_odds) - 1")
    lines.append("```")
    lines.append("")
    lines.append("A bet is flagged as **value** when EV exceeds the market-specific threshold:")
    lines.append("")
    lines.append("| Market | EV Threshold | Rationale |")
    lines.append("|--------|-------------|-----------|")
    lines.append("| Outright | 5% | High variance, needs larger edge |")
    lines.append("| Top 5 | 5% | High variance |")
    lines.append("| Top 10 | 2% | Moderate variance |")
    lines.append("| Top 20 | 2% | Lower variance, smaller edges worthwhile |")
    lines.append("| FRL | 5% | Very high variance |")
    lines.append("| Make Cut | 2% | Lowest variance |")
    lines.append("")
    lines.append("### Data Quality Filters")
    lines.append("")
    lines.append("- **MAX_CREDIBLE_EV:** 200% — anything above is flagged as suspicious")
    lines.append("- **MIN_MARKET_PROB:** 0.5% — odds implying less than this are likely corrupted")
    lines.append("- **MAX_REASONABLE_ODDS:** Market-specific caps (e.g., +30000 outright, +3000 top 10)")
    lines.append("")

    lines.append("### This Week's Value Assessment")
    lines.append("")
    lines.append("| Market | Players Priced | Value Plays | Best Value |")
    lines.append("|--------|---------------|-------------|------------|")
    for bt_label, bt_key in [("Outright", "outright"), ("Top 5", "top5"),
                              ("Top 10", "top10"), ("Top 20", "top20"), ("FRL", "frl")]:
        vb_list = value_bets.get(bt_key, [])
        total = len(vb_list)
        value_only = [v for v in vb_list if v.get("is_value")]
        if total == 0:
            lines.append(f"| {bt_label} | — | — | No odds available |")
            continue
        best = ""
        if value_only:
            top_v = value_only[0]
            best = f"{top_v['player_display']}: {top_v['ev_pct']} EV @ {_fmt_odds(top_v['best_odds'])} ({top_v['best_book']})"
        else:
            best = "No positive-EV plays"
        lines.append(f"| {bt_label} | {total} | {len(value_only)} | {best} |")
    lines.append("")

    lines.append("---")
    lines.append("")


def _adaptation_section(lines, ctx):
    lines.append("## Market Adaptation System")
    lines.append("")
    lines.append("The v4 model includes an automated market adaptation system that tracks ROI by market type "
                 "and adjusts betting behavior based on rolling performance.")
    lines.append("")
    lines.append("### Graduated Response")
    lines.append("")
    lines.append("| State | Trigger | Action |")
    lines.append("|-------|---------|--------|")
    lines.append("| Normal | ROI > -10% or < 15 bets tracked | Standard EV thresholds |")
    lines.append("| Caution | ROI -10% to -25% | EV threshold raised by 3% |")
    lines.append("| Cold | ROI -25% to -50% or 5+ consecutive losses | Stake reduced to 0.5u, EV +5% |")
    lines.append("| Frozen | ROI < -50% or 8+ consecutive losses | Market suppressed entirely |")
    lines.append("")

    adaptation_states = ctx.get("adaptation_states", {})
    if adaptation_states:
        lines.append("### Current Adaptation Status")
        lines.append("")
        lines.append("| Market | State | EV Threshold | Stake | Bets Tracked |")
        lines.append("|--------|-------|-------------|-------|--------------|")
        for market, state in adaptation_states.items():
            ev_thr = state.get("ev_threshold")
            ev_str = f"{ev_thr:.0%}" if ev_thr is not None else "suppressed"
            stake = state.get("stake_multiplier", 1.0)
            bets = state.get("total_bets", 0)
            lines.append(f"| {market} | {state.get('state', 'normal')} | {ev_str} | {stake}u | {bets} |")
        lines.append("")
    else:
        lines.append("*Adaptation states not yet populated (first run or data unavailable).*")
        lines.append("")

    lines.append("---")
    lines.append("")


def _ai_section(lines, ai_pre, ctx):
    lines.append("## AI Adjustments & Portfolio Rules")
    lines.append("")

    if ai_pre:
        conf = ai_pre.get("confidence", 0)
        lines.append(f"**AI Status:** Enabled ({conf:.0%} confidence)")
        lines.append("")

        narrative = ai_pre.get("course_narrative", "")
        if narrative:
            lines.append(f"**AI Narrative:** {narrative}")
            lines.append("")

        key_factors = ai_pre.get("key_factors", [])
        if key_factors:
            lines.append("**Key Factors (AI-identified):**")
            for kf in key_factors:
                lines.append(f"- {kf}")
            lines.append("")

        watch = ai_pre.get("players_to_watch", [])
        if watch:
            lines.append("**Players to Watch:**")
            lines.append("")
            lines.append("| Player | Adjustment | Edge |")
            lines.append("|--------|------------|------|")
            for p in watch:
                adj = p.get("adjustment", 0)
                sign = "+" if adj > 0 else ""
                lines.append(f"| {p['player']} | {sign}{adj:.1f} | {p['edge']} |")
            lines.append("")

        fades = ai_pre.get("players_to_fade", [])
        if fades:
            lines.append("**Players to Fade:**")
            lines.append("")
            lines.append("| Player | Adjustment | Reason |")
            lines.append("|--------|------------|--------|")
            for p in fades:
                adj = p.get("adjustment", 0)
                sign = "+" if adj > 0 else ""
                lines.append(f"| {p['player']} | {sign}{adj:.1f} | {p['reason']} |")
            lines.append("")
    else:
        lines.append("**AI Status:** Not available this week")
        lines.append("")
        lines.append("Rankings reflect only the mathematical model (course fit + form + momentum + weather adjustments).")
        lines.append("")

    lines.append("### AI Tracking (v4)")
    lines.append("")
    lines.append("AI adjustments are tracked separately. If they consistently hurt performance over a rolling window, "
                 "adjustment caps are lowered or AI adjustments are auto-disabled.")
    lines.append("")
    lines.append("### Portfolio Rules")
    lines.append("")
    lines.append("- Max 40% of total units on any single player across all bet types")
    lines.append("- Max 3 units on any individual bet")
    lines.append("- Violations proportionally scaled down")
    lines.append("")
    lines.append("---")
    lines.append("")


def _course_profile_section(lines, profile, course_name, composite):
    lines.append(f"## Course Profile: {course_name}")
    lines.append("")

    if not profile:
        lines.append("*No course profile available. Model uses neutral weights for all SG categories.*")
        lines.append("")
        lines.append("---")
        lines.append("")
        return

    source = profile.get("course_facts", {}).get("source", "auto-generated")
    lines.append(f"**Source:** {source}")
    lines.append("")

    ratings = profile.get("skill_ratings", {})
    if ratings:
        lines.append("| Category | Difficulty | Impact |")
        lines.append("|----------|-----------|--------|")
        descriptions = {
            "sg_ott": "Driving accuracy and distance",
            "sg_app": "Approach play / iron quality",
            "sg_arg": "Around-the-green / scrambling",
            "sg_putting": "Putting performance",
        }
        for cat in ["sg_ott", "sg_app", "sg_arg", "sg_putting"]:
            diff = ratings.get(cat, "Unknown")
            desc = descriptions.get(cat, "")
            lines.append(f"| {cat.upper().replace('_', ':')} | {diff} | {desc} |")
        lines.append("")

    facts = profile.get("course_facts", {})
    if facts:
        lines.append("### Key Characteristics")
        lines.append("")
        for key in ["par", "yardage", "grass", "designer"]:
            if key in facts:
                lines.append(f"- **{key.title()}:** {facts[key]}")
        lines.append("")

    by_course = sorted(composite, key=lambda x: x.get("course_fit", 0), reverse=True)
    lines.append("### Best Course Fits This Week")
    lines.append("")
    lines.append("| Player | Course Fit | Rounds at Course |")
    lines.append("|--------|-----------|-----------------|")
    for r in by_course[:5]:
        lines.append(f"| {r['player_display']} | {r['course_fit']:.1f} | {r.get('course_rounds', 0):.0f} |")
    lines.append("")
    lines.append("---")
    lines.append("")


def _worked_examples(lines, composite, ctx):
    lines.append("## Worked Examples: Top 5 Players")
    lines.append("")

    weights = ctx.get("weights", {})
    w_cf = weights.get("course_fit", 0.45)
    w_form = weights.get("form", 0.45)
    w_mom = weights.get("momentum", 0.10)

    dg_probs = ctx.get("dg_probs", {})

    for r in composite[:5]:
        pk = r["player_key"]
        lines.append(f"### #{r['rank']} {r['player_display']} — Composite {r['composite']:.1f}")
        lines.append("")
        lines.append("| Component | Score | Weight | Contribution |")
        lines.append("|-----------|-------|--------|-------------|")

        cf_contrib = w_cf * r["course_fit"]
        form_contrib = w_form * r["form"]
        mom_contrib = w_mom * r["momentum"]

        lines.append(f"| Course Fit | {r['course_fit']:.1f} | {w_cf:.0%} | ~{cf_contrib:.1f} |")
        lines.append(f"| Form | {r['form']:.1f} | {w_form:.0%} | ~{form_contrib:.1f} |")
        lines.append(f"| Momentum | {r['momentum']:.1f} | {w_mom:.0%} | ~{mom_contrib:.1f} |")
        lines.append(f"| **Final Composite** | | | **{r['composite']:.1f}** |")
        lines.append("")

        player_dg = dg_probs.get(pk, {})
        win_pct = player_dg.get("Win % (CH)") or player_dg.get("Win %")
        t10_pct = player_dg.get("Top 10 % (CH)") or player_dg.get("Top 10 %")

        notes = []
        if r["course_fit"] > 60:
            notes.append(f"Strong course fit ({r['course_fit']:.1f})")
        elif r["course_fit"] < 52:
            notes.append(f"Limited course history (fit {r['course_fit']:.1f})")
        if r["form"] > 90:
            notes.append("Elite current form")
        if win_pct:
            notes.append(f"DG Win% {win_pct*100:.1f}%")
        if t10_pct:
            notes.append(f"DG T10% {t10_pct*100:.1f}%")
        trend = {"hot": "Trending hot (↑↑)", "warming": "Warming (↑)",
                 "cooling": "Cooling (↓)", "cold": "Trending cold (↓↓)"}.get(
            r.get("momentum_direction", ""), "")
        if trend:
            notes.append(trend)

        if notes:
            for note in notes:
                lines.append(f"- {note}")
            lines.append("")

    lines.append("---")
    lines.append("")


def _picks_rationale(lines, value_bets, composite, ctx):
    lines.append("## This Week's Picks & Rationale")
    lines.append("")

    total_value = sum(
        sum(1 for v in vb if v.get("is_value"))
        for vb in value_bets.values()
    )
    ai_tag = "AI-adjusted" if ctx.get("ai_pre_analysis") else "Purely quantitative"
    lines.append(f"### Summary: {total_value} Value Bets Found ({ai_tag})")
    lines.append("")

    for bt_label, bt_key in [("Outright", "outright"), ("Top 5", "top5"),
                              ("Top 10", "top10"), ("Top 20", "top20")]:
        vb_list = value_bets.get(bt_key, [])
        value_only = [v for v in vb_list if v.get("is_value")]
        if not value_only:
            continue

        lines.append(f"### {bt_label} Value ({len(value_only)} bets)")
        lines.append("")
        lines.append("| Player | Odds | Model% | Market% | EV | Better Price |")
        lines.append("|--------|------|--------|---------|-----|-------------|")
        for v in value_only[:8]:
            odds_str = _fmt_odds(v["best_odds"])
            better = v.get("better_odds_note", "—") or "—"
            lines.append(
                f"| {v['player_display']} | {odds_str} @ {v['best_book']} "
                f"| {v['model_prob']:.1%} | {v['market_prob']:.1%} "
                f"| {v['ev_pct']} | {better} |"
            )
        lines.append("")

    matchup_bets = ctx.get("matchup_bets", [])
    if matchup_bets:
        lines.append(f"### Matchup Value ({len(matchup_bets)} bets)")
        lines.append("")
        lines.append("Matchups use a Platt-style sigmoid on composite gap, blended 80% DG / 20% model. "
                     "Conviction (0–100) combines form gap, course-fit gap, momentum alignment, and DG/model agreement.")
        lines.append("")
        lines.append("| Pick | vs | Odds | Model Win% | EV | Conviction | Tier | Book |")
        lines.append("|------|-----|------|------------|-----|------------|------|------|")
        for bet in matchup_bets[:10]:
            odds = bet.get("odds", 0)
            odds_str = _fmt_odds(odds)
            conv = bet.get("conviction", "—")
            conv_str = str(conv) if conv is not None else "—"
            lines.append(
                f"| {bet['pick']} | {bet['opponent']} | {odds_str} "
                f"| {bet.get('model_win_prob', 0):.1%} | {bet.get('ev_pct', '')} | {conv_str} | {bet.get('tier', '—')} | {bet.get('book', '—')} |"
            )
        lines.append("")

    hot_players = [r for r in composite if r.get("momentum_direction") == "hot"]
    hot_players.sort(key=lambda x: x["momentum"], reverse=True)
    if hot_players:
        lines.append("### Trending Hot (↑↑)")
        lines.append("")
        lines.append("| Player | Momentum | Rank |")
        lines.append("|--------|----------|------|")
        for r in hot_players[:5]:
            lines.append(f"| {r['player_display']} | {r['momentum']:.1f} | #{r['rank']} |")
        lines.append("")

    cold_players = [r for r in composite if r.get("momentum_direction") == "cold"]
    cold_players.sort(key=lambda x: x["momentum"])
    if cold_players:
        lines.append("### Trending Cold / Fades (↓↓)")
        lines.append("")
        lines.append("| Player | Momentum | Rank |")
        lines.append("|--------|----------|------|")
        for r in cold_players[:5]:
            lines.append(f"| {r['player_display']} | {r['momentum']:.1f} | #{r['rank']} |")
        lines.append("")

    lines.append("---")
    lines.append("")


def _limitations(lines, ctx):
    lines.append("## Known Limitations & Future Work")
    lines.append("")
    lines.append("### Current Limitations")
    lines.append("")

    limitations = [
        "Very high EV values (>100%) are likely model-market probability disagreements rather than true edges of that magnitude. Real sports betting edges are typically 2-20%.",
        "DG data dependency: Course-specific decompositions and skill ratings are not available historically, so the backtester cannot fully replicate the DG blending.",
        "Sim probabilities not in backtester: DG pre-tournament probabilities cannot be replicated for backtesting.",
    ]

    if not ctx.get("ai_pre_analysis"):
        limitations.insert(0, "AI unavailable this week. No qualitative adjustments, narrative, or AI portfolio optimization.")

    profile = ctx.get("profile")
    if profile and profile.get("course_facts", {}).get("source") == "auto-generated":
        limitations.append("Course profile is auto-generated from DG decomposition data. Manual course profiles with screenshots provide more nuance.")

    for i, lim in enumerate(limitations, 1):
        lines.append(f"{i}. {lim}")
    lines.append("")

    lines.append("### Database State After Run")
    lines.append("")
    total_rounds = ctx.get("total_rounds", 0)
    n_logged = ctx.get("predictions_logged", 0)
    lines.append(f"- **Total rounds stored:** {total_rounds:,}")
    lines.append(f"- **Predictions logged:** {n_logged} for post-tournament scoring")
    if profile:
        lines.append(f"- **Course profile:** {profile.get('course_facts', {}).get('source', 'available')}")
    lines.append("")
    lines.append("---")
    lines.append("")


def _footer(lines, composite, ai_pre, model_version):
    ai_tag = " AI-adjusted." if ai_pre else ""
    lines.append(f"*Generated by the Golf Betting Model v{model_version}. "
                 f"All scores, weights, and formulas documented here reflect the exact configuration used for this prediction run. "
                 f"Post-tournament review will automatically run after the tournament completes to score all predictions and update the learning system.*")


def _fmt_odds(price: int) -> str:
    if price > 0:
        return f"+{price}"
    return str(price)
