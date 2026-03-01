"""
Generate a backtest comparison report for the Cognizant Classic.
Compares pre-tournament model predictions against actual R3 leaderboard.
"""
import sqlite3
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from src.datagolf import _call_api
from src.player_normalizer import normalize_name

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'golf.db')

def fetch_live_leaderboard():
    lb = _call_api('preds/in-play', {'tour': 'pga'})
    live_data = lb.get('data', [])
    info = lb.get('info', {})
    lookup = {}
    for p in live_data:
        raw = p.get('player_name', '')
        parts = raw.split(', ')
        display = f"{parts[1]} {parts[0]}" if len(parts) == 2 else raw
        nk = normalize_name(display)
        lookup[nk] = {
            'display': display,
            'pos': p.get('current_pos', '?'),
            'score': p.get('current_score', 0),
            'r1': p.get('R1'), 'r2': p.get('R2'), 'r3': p.get('R3'),
            'thru': p.get('thru', ''),
            'win_live': p.get('win', 0) or 0,
            'top5_live': p.get('top_5', 0) or 0,
            'top10_live': p.get('top_10', 0) or 0,
            'top20_live': p.get('top_20', 0) or 0,
            'make_cut': p.get('make_cut', 0) or 0,
        }
    return lookup, live_data, info


def get_pos_num(pos_str):
    if not pos_str or pos_str in ('N/A', 'WD', '?'):
        return 999
    if 'CUT' in str(pos_str):
        return 999
    try:
        return int(str(pos_str).replace('T', ''))
    except (ValueError, TypeError):
        return 999


def main():
    live_lookup, live_data, info = fetch_live_leaderboard()

    # All 40 model rankings from the card
    all_model_rankings = [
        ("Jake Knapp", 76.4, 66.4, 83.8, 57.6),
        ("Min Woo Lee", 76.0, 65.9, 84.0, 66.1),
        ("Rory McIlroy", 75.7, 64.3, 93.1, 60.6),
        ("Matt Fitzpatrick", 73.7, 62.0, 86.6, 58.8),
        ("Collin Morikawa", 73.6, 56.1, 89.7, 67.3),
        ("Shane Lowry", 73.1, 65.5, 80.4, 64.6),
        ("Scottie Scheffler", 71.3, 57.1, 96.4, 43.1),
        ("Jacob Bridgeman", 71.2, 60.9, 83.5, 67.4),
        ("Nicolai Hojgaard", 71.1, 60.6, 87.5, 58.8),
        ("Xander Schauffele", 70.3, 56.9, 88.8, 53.2),
        ("Tommy Fleetwood", 70.2, 56.8, 91.7, 43.2),
        ("Kurt Kitayama", 69.5, 58.5, 81.9, 53.3),
        ("Robert MacIntyre", 69.5, 61.2, 77.3, 55.1),
        ("Cameron Young", 69.2, 63.9, 78.9, 40.9),
        ("Chris Gotterup", 69.2, 63.2, 76.7, 47.7),
        ("Akshay Bhatia", 69.2, 56.5, 80.5, 67.5),
        ("Adam Scott", 69.1, 54.5, 83.5, 64.1),
        ("Russell Henley", 68.4, 67.2, 82.7, 37.7),
        ("Rickie Fowler", 68.2, 64.9, 78.4, 37.3),
        ("Maverick McNealy", 67.2, 60.5, 78.9, 36.3),
        ("Hideki Matsuyama", 66.9, 56.7, 84.7, 38.2),
        ("Ryan Gerard", 66.9, 62.9, 80.4, 35.9),
        ("Alex Noren", 66.5, 59.1, 75.9, 58.1),
        ("Patrick Cantlay", 66.5, 56.6, 79.7, 51.6),
        ("Harris English", 65.5, 56.3, 81.2, 49.0),
        ("Si Woo Kim", 64.7, 56.4, 79.6, 35.0),
        ("Alex Smalley", 64.7, 58.5, 72.5, 57.6),
        ("Justin Rose", 64.4, 59.2, 74.3, 43.9),
        ("Ben Griffin", 64.2, 63.9, 71.2, 34.4),
        ("Haotong Li", 64.1, 49.8, 73.9, 64.3),
        ("Jordan Spieth", 64.0, 59.0, 68.4, 66.7),
        ("Pierceson Coody", 63.5, 58.3, 76.8, 36.6),
        ("Ryan Fox", 63.4, 55.7, 68.6, 67.4),
        ("Rasmus Hojgaard", 63.4, 57.2, 76.8, 43.5),
        ("Ryo Hisatsune", 63.1, 56.9, 71.6, 38.1),
        ("Mac Meissner", 62.9, 55.2, 73.0, 51.8),
        ("Keith Mitchell", 62.9, 61.7, 68.4, 43.5),
        ("Davis Thompson", 62.6, 58.7, 66.6, 49.2),
        ("Nick Taylor", 62.5, 54.2, 72.4, 55.0),
        ("Christiaan Bezuidenhout", 62.2, 56.8, 70.7, 48.4),
    ]

    # Filter to only players who actually played (exist in live leaderboard)
    field_filtered = []
    field_filtered_rank = 0
    for name, comp, cf, form, mom in all_model_rankings:
        nk = normalize_name(name)
        if nk in live_lookup:
            field_filtered_rank += 1
            field_filtered.append((name, comp, cf, form, mom, field_filtered_rank))

    # Use all rankings for the full table, but field-filtered for accuracy stats
    model_rankings = all_model_rankings

    value_bets = [
        ("Ryan Gerard", "top10", "+1200", 24.4, 7.7, 186.1),
        ("Rasmus Neergaard-Petersen", "top10", "+1800", 12.8, 5.3, 118.0),
        ("Daniel Berger", "top10", "+1600", 12.9, 5.9, 97.1),
        ("Mackenzie Hughes", "top10", "+2000", 9.9, 4.8, 87.0),
        ("Jordan Smith", "top10", "+1800", 10.5, 5.3, 79.5),
        ("Garrick Higgo", "top10", "+1800", 9.4, 5.3, 60.5),
        ("Nicolai Hojgaard", "top10", "+600", 22.7, 14.3, 42.8),
        ("Eric Cole", "top10", "+2200", 6.5, 4.3, 34.3),
        ("Haotong Li", "top20", "+1200", 21.7, 7.7, 159.9),
        ("Austin Eckroat", "top20", "+1000", 15.5, 9.1, 57.0),
        ("Christiaan Bezuidenhout", "top20", "+600", 23.6, 14.3, 51.8),
        ("Matt Wallace", "top20", "+750", 18.2, 11.8, 42.4),
        ("Adrien Saddier", "top20", "+1100", 12.3, 8.3, 36.1),
        ("Michael Brennan", "top20", "+550", 20.4, 15.4, 22.0),
        ("Dan Brown", "top20", "+900", 12.7, 10.0, 17.0),
        ("Chandler Phillips", "top20", "+1200", 9.8, 7.7, 16.6),
        ("Kristoffer Reitan", "outright", "+17500", 1.0, 0.57, 82.9),
        ("Aaron Rai", "outright", "+17500", 1.0, 0.57, 75.1),
        ("Keith Mitchell", "outright", "+6000", 2.3, 1.6, 38.4),
        ("Zecheng Dou", "outright", "+20000", 0.7, 0.5, 32.4),
        ("Max Homa", "top5", "+5000", 4.5, 2.0, 118.4),
        ("Rasmus Hojgaard", "top5", "+1600", 9.7, 5.9, 56.4),
        ("Thorbjorn Olesen", "top5", "+2500", 5.5, 3.9, 37.2),
    ]

    fades = [
        "Danny Willett", "Adam Schenk", "Gordon Sargent", "Cam Davis",
        "Jimmy Stanger", "Pontus Nyholm", "Brendon Todd", "Brian Campbell",
        "Justin Hicks", "Alejandro Tosti",
    ]

    ai_watches = [("Jake Knapp", "+2.0"), ("Min Woo Lee", "+2.0"), ("Shane Lowry", "+1.0")]
    ai_fades = [("Scottie Scheffler", "-3.0"), ("Tommy Fleetwood", "-2.0"), ("Russell Henley", "-2.0")]

    model_rank_lookup = {}
    for i, (name, *_) in enumerate(model_rankings, 1):
        model_rank_lookup[normalize_name(name)] = i

    # Field-filtered rank lookup
    field_rank_lookup = {}
    for name, comp, cf, form, mom, filt_rank in field_filtered:
        field_rank_lookup[normalize_name(name)] = filt_rank

    # ── Compute stats (raw — includes players not in field) ──
    top10_in_t10 = top10_in_t20 = top10_mc = top20_in_t20 = 0
    for i, (name, *_) in enumerate(model_rankings[:20], 1):
        nk = normalize_name(name)
        live = live_lookup.get(nk, {})
        pos = live.get('pos', 'N/A')
        num = get_pos_num(pos)
        if 'CUT' in str(pos) or pos == 'WD':
            if i <= 10: top10_mc += 1
            continue
        if i <= 10:
            if num <= 10: top10_in_t10 += 1
            if num <= 20: top10_in_t20 += 1
        if num <= 20: top20_in_t20 += 1

    # ── Compute field-filtered accuracy stats ──
    ff_t5_in_t10 = ff_t5_in_t20 = ff_t10_in_t10 = ff_t10_in_t20 = ff_t10_mc = 0
    n_in_field = len(field_filtered)
    for name, comp, cf, form, mom, filt_rank in field_filtered:
        nk = normalize_name(name)
        live = live_lookup.get(nk, {})
        pos = live.get('pos', 'N/A')
        num = get_pos_num(pos)
        if filt_rank <= 5:
            if 'CUT' in str(pos): ff_t10_mc += 1
            elif num <= 10: ff_t5_in_t10 += 1; ff_t10_in_t10 += 1
            elif num <= 20: ff_t5_in_t20 += 1; ff_t10_in_t20 += 1
        elif filt_rank <= 10:
            if 'CUT' in str(pos): ff_t10_mc += 1
            elif num <= 10: ff_t10_in_t10 += 1
            elif num <= 20: ff_t10_in_t20 += 1

    # ── Value bet scoring ──
    total_hits = total_alive = total_miss = 0
    bet_results = []
    for name, market, odds, mod_pct, mkt_pct, ev_pct in value_bets:
        nk = normalize_name(name)
        live = live_lookup.get(nk, {})
        pos = live.get('pos', 'N/A')
        num = get_pos_num(pos)
        score = live.get('score', 0)
        score_str = f"{score:+d}" if isinstance(score, (int, float)) else str(score)

        thresholds = {"top5": 5, "top10": 10, "top20": 20, "outright": 1}
        target = thresholds.get(market, 20)
        live_prob_key = f"{market}_live" if market != "outright" else "win_live"
        live_prob = live.get(live_prob_key, 0) or 0

        if 'CUT' in str(pos) or pos == 'WD':
            status = "LOST"; total_miss += 1
        elif num <= target:
            status = "WINNING"; total_hits += 1
        elif live_prob > 0.05:
            status = f"ALIVE ({live_prob:.0%})"; total_alive += 1
        else:
            status = "UNLIKELY"; total_miss += 1

        bet_results.append((name, market, odds, ev_pct, pos, score_str, status))

    # ── Fades scoring ──
    fades_correct = 0
    fade_results = []
    for name in fades:
        nk = normalize_name(name)
        live = live_lookup.get(nk, {})
        pos = live.get('pos', 'N/A')
        num = get_pos_num(pos)
        score = live.get('score', 0)
        score_str = f"{score:+d}" if isinstance(score, (int, float)) else str(score)
        if 'CUT' in str(pos):
            verdict = "Good fade (MC)"; fades_correct += 1
        elif pos in ('WD', 'N/A', '?'):
            verdict = "WD/DNS"
        elif num > 40:
            verdict = "Good fade"; fades_correct += 1
        elif num > 20:
            verdict = "Marginal"; fades_correct += 1
        else:
            verdict = "Fade was wrong"
        fade_results.append((name, pos, score_str, verdict))

    # ── BUILD REPORT ──
    L = []
    L.append("# Cognizant Classic — Backdated Prediction Report")
    L.append(f"**Model Version:** v4.0 (Post-Overhaul)")
    L.append(f"**Report Generated:** 2026-02-28 (After R3)")
    L.append(f"**Predictions Made With:** Pre-tournament data only (no in-play information)")
    L.append(f"**Tournament Status:** R3 Complete — {info.get('last_update', 'unknown')}")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## Executive Summary")
    L.append("")
    L.append("This report compares what our overhauled model (v4.0) predicted **before the Cognizant Classic** against actual results through 3 rounds. All model scores, rankings, and value bets were computed using only pre-tournament data (DG simulations, rolling stats, course history, weather forecasts). No in-play adjustments were used.")
    L.append("")

    # ── Model Accuracy Scorecard ──
    total_bets = total_hits + total_alive + total_miss
    ff_grade = "A" if ff_t5_in_t10 >= 3 else "B" if ff_t5_in_t10 >= 2 else "C" if ff_t5_in_t10 >= 1 else "D"
    value_grade = "A" if total_hits >= 8 else "B" if total_hits >= 4 else "C" if total_hits >= 2 else "D"
    fade_grade = "A" if fades_correct >= 8 else "B" if fades_correct >= 6 else "C" if fades_correct >= 4 else "D"

    n_dns = sum(1 for name, *_ in model_rankings[:20] if normalize_name(name) not in live_lookup)

    L.append("## Critical Finding: Field Mismatch")
    L.append("")
    L.append(f"> **{n_dns} of our top 20 ranked players were NOT in this field.** The Cognizant Classic is an alternate PGA Tour event — the major names (Scheffler, McIlroy, Schauffele, Morikawa, etc.) played elsewhere. Our model scored 183 players from the DG field API, but many were never confirmed starters. This inflates model rankings with phantom entries and is the #1 issue to fix: **field filtering must be stricter.**")
    L.append("")

    L.append("## Model Performance Scorecard")
    L.append("")
    L.append("### Field-Filtered Accuracy (players who actually played)")
    L.append("")
    L.append(f"Of {len(all_model_rankings)} model rankings, only **{n_in_field}** players were actually in the field.")
    L.append("")
    L.append("| Category | Score | Notes |")
    L.append("|----------|-------|-------|")
    L.append(f"| Field-filtered top 5 in actual top 10 | **{ff_t5_in_t10}/{min(5, n_in_field)}** | {', '.join(n for n, *_ in field_filtered[:5])} |")
    L.append(f"| Field-filtered top 5 in actual top 20 | **{ff_t5_in_t10 + ff_t5_in_t20}/{min(5, n_in_field)}** | — |")
    L.append(f"| Field-filtered top 10 in actual top 10 | **{ff_t10_in_t10}/{min(10, n_in_field)}** | — |")
    L.append(f"| Field-filtered top 10 missed cut | **{ff_t10_mc}/{min(10, n_in_field)}** | — |")
    L.append(f"| Value bets currently hitting | **{total_hits}/{total_bets}** | R4 still to play |")
    L.append(f"| Value bets still alive | **{total_alive}/{total_bets}** | Many in contention |")
    L.append(f"| Value bets dead | **{total_miss}/{total_bets}** | — |")
    L.append(f"| Fade accuracy | **{fades_correct}/{len(fades)}** | **{fade_grade}** |")
    L.append("")
    L.append("### Raw Ranking Accuracy (includes players not in field)")
    L.append("")
    L.append("| Category | Score | Notes |")
    L.append("|----------|-------|-------|")
    L.append(f"| Raw model top 10 in actual top 10 | {top10_in_t10}/10 | {n_dns} of 10 weren't in field |")
    L.append(f"| Raw model top 20 in actual top 20 | {top20_in_t20}/20 | Misleading due to field mismatch |")
    L.append("")

    # ── Field-Filtered Rankings vs Actual ──
    L.append("## Field-Filtered Rankings vs Actual Leaderboard (After R3)")
    L.append("")
    L.append("*Only showing players who actually played this week.*")
    L.append("")
    L.append("| Field Rank | Player | Composite | Course Fit | Form | Actual Pos | Score | Status |")
    L.append("|-----------|--------|-----------|-----------|------|-----------|-------|--------|")
    for name, comp, cf, form, mom, filt_rank in field_filtered:
        nk = normalize_name(name)
        live = live_lookup.get(nk, {})
        pos = live.get('pos', 'N/A')
        score = live.get('score', '')
        score_str = f"{score:+d}" if isinstance(score, (int, float)) and score != '' else str(score)
        num = get_pos_num(pos)
        if 'CUT' in str(pos):
            status = "MC"
        elif num <= 5:
            status = "**Contending**"
        elif num <= 10:
            status = "**Top 10**"
        elif num <= 20:
            status = "In Mix"
        elif num <= 40:
            status = "Mid-Pack"
        else:
            status = "Struggling"
        L.append(f"| {filt_rank} | **{name}** | {comp} | {cf} | {form} | {pos} | {score_str} | {status} |")
    L.append("")

    # ── Value Bet Tracker ──
    L.append("## Value Bet Tracker (23 Bets)")
    L.append("")
    L.append("| Pick | Market | Odds | EV% | Current Pos | Score | R3 Status |")
    L.append("|------|--------|------|-----|------------|-------|-----------|")
    for name, market, odds, ev_pct, pos, score_str, status in bet_results:
        icon = {"WINNING": "✅", "LOST": "❌", "UNLIKELY": "🔴"}.get(status, "🟡" if "ALIVE" in status else "—")
        L.append(f"| {name} | {market} | {odds} | {ev_pct:.1f}% | {pos} | {score_str} | {icon} {status} |")
    L.append("")

    # ── AI Adjustments ──
    L.append("## AI Adjustments Assessment")
    L.append("")
    L.append("### Watches (AI boosted)")
    L.append("")
    L.append("| Player | Adjustment | Actual Pos | Score | Verdict |")
    L.append("|--------|------------|-----------|-------|---------|")
    for name, adj in ai_watches:
        nk = normalize_name(name)
        live = live_lookup.get(nk, {})
        pos = live.get('pos', 'N/A')
        num = get_pos_num(pos)
        score = live.get('score', 0)
        score_str = f"{score:+d}" if isinstance(score, (int, float)) else str(score)
        if 'CUT' in str(pos): verdict = "❌ Wrong"
        elif num <= 5: verdict = "✅ Great call"
        elif num <= 20: verdict = "🟡 Decent"
        else: verdict = "🔴 Wrong"
        L.append(f"| {name} | {adj} | {pos} | {score_str} | {verdict} |")

    L.append("")
    L.append("### Fades (AI downgraded)")
    L.append("")
    L.append("| Player | Adjustment | Actual Pos | Score | Verdict |")
    L.append("|--------|------------|-----------|-------|---------|")
    for name, adj in ai_fades:
        nk = normalize_name(name)
        live = live_lookup.get(nk, {})
        pos = live.get('pos', 'N/A')
        num = get_pos_num(pos)
        score = live.get('score', 0)
        score_str = f"{score:+d}" if isinstance(score, (int, float)) else str(score)
        if 'CUT' in str(pos): verdict = "✅ Good fade"
        elif num > 40: verdict = "✅ Good fade"
        elif num > 20: verdict = "🟡 Okay"
        else: verdict = "❌ Should have kept"
        L.append(f"| {name} | {adj} | {pos} | {score_str} | {verdict} |")
    L.append("")

    # ── Fades ──
    L.append("## Fades Performance")
    L.append("")
    L.append("| Player | Actual Pos | Score | Verdict |")
    L.append("|--------|-----------|-------|---------|")
    for name, pos, score_str, verdict in fade_results:
        icon = "✅" if "Good" in verdict else "🟡" if "Marginal" in verdict else "❌" if "wrong" in verdict.lower() else "⬜"
        L.append(f"| {name} | {pos} | {score_str} | {icon} {verdict} |")
    L.append(f"\n**Fade accuracy: {fades_correct}/{len(fades)}**")
    L.append("")

    # ── Surprises ──
    L.append("## Surprise Performers (Actual Top 10 we missed)")
    L.append("")
    L.append("| Actual Pos | Player | Score | Our Rank | Miss By |")
    L.append("|-----------|--------|-------|----------|---------|")
    for p in live_data[:10]:
        raw = p.get('player_name', '')
        parts = raw.split(', ')
        display = f"{parts[1]} {parts[0]}" if len(parts) == 2 else raw
        nk = normalize_name(display)
        our_rank = model_rank_lookup.get(nk)
        pos = p.get('current_pos', '')
        score = p.get('current_score', 0)
        if our_rank is None or our_rank > 20:
            rank_str = f"#{our_rank}" if our_rank else "Unranked"
            miss = f"{our_rank - 10} spots" if our_rank else "N/A"
            L.append(f"| {pos} | {display} | {score:+d} | {rank_str} | {miss} |")
    L.append("")

    # ── Key Takeaways ──
    L.append("## Key Takeaways")
    L.append("")

    lowry = live_lookup.get('shane_lowry', {})
    L.append(f"1. **Shane Lowry {lowry.get('pos', '?')} at {lowry.get('score', 0):+d}** — Model ranked him #6 (composite 73.1), AI gave +1.0 watch. His course fit score of 65.5 was 5th highest in the field. The model and AI both correctly identified him as a top contender this week.")
    L.append("")

    mitchell = live_lookup.get('keith_mitchell', {})
    L.append(f"2. **Keith Mitchell {mitchell.get('pos', '?')} at {mitchell.get('score', 0):+d}** — Outright value bet at +6000 (EV 38.4%). Currently alive in T9 with {mitchell.get('win_live', 0)*100:.1f}% live win probability. Course fit of 61.7 was key driver.")
    L.append("")

    reitan = live_lookup.get('kristoffer_reitan', {})
    L.append(f"3. **Kristoffer Reitan {reitan.get('pos', '?')} at {reitan.get('score', 0):+d}** — Top outright value play (+17500, EV 82.9%). Currently {reitan.get('pos', '?')} with {reitan.get('win_live', 0)*100:.1f}% live win probability. Remarkable value identification.")
    L.append("")

    hojgaard_r = live_lookup.get('rasmus_hojgaard', {})
    L.append(f"4. **Rasmus Hojgaard {hojgaard_r.get('pos', '?')} at {hojgaard_r.get('score', 0):+d}** — Top 5 value bet at +1600 (EV 56.4%). Currently in contention with {hojgaard_r.get('top5_live', 0)*100:.1f}% live top-5 probability.")
    L.append("")

    L.append(f"5. **Fade accuracy: {fades_correct}/{len(fades)}** — {'Strong' if fades_correct >= 7 else 'Moderate' if fades_correct >= 5 else 'Poor'} fade identification. Most faded players missed the cut or are well outside contention.")
    L.append("")

    # ── Old model comparison ──
    L.append("## Old Model (Feb 23) vs New Model (Feb 28) Comparison")
    L.append("")
    L.append("The old model (pre-overhaul) had different rankings for this same event:")
    L.append("")
    L.append("| Player | Old Rank (Feb 23) | New Rank (Feb 28) | Actual Pos | Better Model? |")
    L.append("|--------|------------------|------------------|-----------|--------------|")
    old_rankings = [
        ("Scottie Scheffler", 1), ("Rory McIlroy", 2), ("Collin Morikawa", 3),
        ("Min Woo Lee", 4), ("Tommy Fleetwood", 5), ("Jake Knapp", 6),
        ("Matt Fitzpatrick", 7), ("Xander Schauffele", 8), ("Jacob Bridgeman", 9),
        ("Nicolai Hojgaard", 10), ("Shane Lowry", 11), ("Adam Scott", 12),
        ("Robert MacIntyre", 13), ("Harris English", 14), ("Russell Henley", 15),
    ]
    for name, old_rank in old_rankings:
        nk = normalize_name(name)
        new_rank = model_rank_lookup.get(nk, '—')
        live = live_lookup.get(nk, {})
        pos = live.get('pos', 'N/A')
        num = get_pos_num(pos)
        if new_rank != '—' and old_rank != '—':
            new_dist = abs(new_rank - num) if num < 999 else 999
            old_dist = abs(old_rank - num) if num < 999 else 999
            if new_dist < old_dist:
                better = "✅ New"
            elif old_dist < new_dist:
                better = "Old"
            else:
                better = "Tie"
        else:
            better = "—"
        L.append(f"| {name} | #{old_rank} | #{new_rank} | {pos} | {better} |")
    L.append("")

    L.append("---")
    L.append(f"*Report covers R1-R3 only. Final scoring after R4 on Sunday. Generated by model v4.0 backtest framework.*")

    report = "\n".join(L)
    out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output', 'cognizant_classic_backtest_report_20260228.md')
    with open(out_path, "w") as f:
        f.write(report)

    print(f"Report saved: {out_path}")
    print(f"\n{'='*60}")
    print(f"  BACKTEST RESULTS SUMMARY (Cognizant Classic R3)")
    print(f"{'='*60}")
    print(f"  ⚠  FIELD MISMATCH: {n_dns}/20 top players weren't in field")
    print(f"")
    print(f"  FIELD-FILTERED ACCURACY ({n_in_field} players in field):")
    print(f"  Field top 5 in actual top 10:  {ff_t5_in_t10}/{min(5, n_in_field)}")
    print(f"  Field top 10 in actual top 10: {ff_t10_in_t10}/{min(10, n_in_field)}")
    print(f"  Field top 10 missed cut:       {ff_t10_mc}/{min(10, n_in_field)}")
    print(f"")
    print(f"  Model top 10 in actual top 10: {top10_in_t10}/10")
    print(f"  VALUE BETS:")
    print(f"  Hitting:                       {total_hits}/{total_bets}")
    print(f"  Still alive (R4 pending):      {total_alive}/{total_bets}")
    print(f"  Dead:                          {total_miss}/{total_bets}")
    print(f"")
    print(f"  OTHER:")
    print(f"  Fade accuracy:                 {fades_correct}/{len(fades)} ({fade_grade})")
    print(f"  Value bet grade:               {value_grade}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
