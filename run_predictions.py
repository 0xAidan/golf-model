#!/usr/bin/env python3
"""
Run the full prediction pipeline from the terminal.

Usage:
    python3 run_predictions.py

This script:
  1. Loads API keys from .env
  2. Detects the current/upcoming PGA Tour event from Data Golf
  3. Backfills round data if needed (2024-2025)
  4. Syncs DG predictions, decompositions, and field updates
  5. Computes rolling stats from stored round data
  6. Loads course profile (if saved from screenshots)
  7. Runs composite model (course fit + form + momentum)
  8. Outputs ranked predictions and betting card

To process course screenshots first:
    python3 -c "
from src.course_profile import extract_from_folder, save_course_profile
data = extract_from_folder('data/course_images', api_key=None)
save_course_profile('YOUR COURSE NAME', data)
"
"""

import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src import db
from src.datagolf import (
    get_current_event_info,
    fetch_historical_rounds,
    _parse_rounds_response,
    _call_api,
    _store_decompositions_as_metrics,
    _store_field_as_metrics,
    _safe_float,
)
from src.rolling_stats import compute_rolling_metrics
from src.models.composite import compute_composite
from src.course_profile import load_course_profile, course_to_model_weights
from src.card import generate_card
from src.player_normalizer import normalize_name, display_name


def print_header(text):
    print(f"\n{'─' * 60}")
    print(f"  {text}")
    print(f"{'─' * 60}")


def safe_api_call(description, func, *args, **kwargs):
    """Call an API function with rate-limit awareness."""
    time.sleep(2)  # Polite pause between API calls
    try:
        return func(*args, **kwargs)
    except Exception as e:
        print(f"  ⚠ {description} error: {e}")
        return None


def main():
    print("=" * 60)
    print("  GOLF BETTING MODEL — Prediction Pipeline")
    print("=" * 60)

    # ── Check API keys ────────────────────────────────────────
    dg_key = os.environ.get("DATAGOLF_API_KEY")
    if not dg_key:
        print("\n❌ DATAGOLF_API_KEY not set. Add it to your .env file.")
        sys.exit(1)
    print("\n✓ Data Golf API key found")

    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        print("✓ OpenAI API key found (for course profile extraction)")

    # ── Get current event ─────────────────────────────────────
    print_header("Step 1: Detecting Current Event")
    event_info = safe_api_call("get schedule", get_current_event_info, "pga")

    if event_info:
        event_name = event_info.get("event_name", "Unknown")
        event_id = event_info.get("event_id", "")
        courses = event_info.get("course", "Unknown")
        location = event_info.get("location", "")
        start_date = event_info.get("start_date", "")
        print(f"  Event: {event_name}")
        print(f"  Course(s): {courses}")
        print(f"  Location: {location}")
        print(f"  Start: {start_date}")
        print(f"  Event ID: {event_id}")

        # Parse course keys for course-specific stats
        course_keys = event_info.get("course_key", "").split(";")
        course_nums = []
        for ck in course_keys:
            try:
                course_nums.append(int(ck))
            except ValueError:
                pass
        if course_nums:
            print(f"  Course num(s): {course_nums}")
    else:
        # Fallback
        event_name = "AT&T Pebble Beach Pro-Am"
        event_id = "5"
        courses = "Pebble Beach Golf Links"
        course_nums = [5]
        print(f"  Using fallback: {event_name}")

    # Determine the primary course name for profile lookup
    # Use the first course listed
    primary_course = courses.split(";")[0].strip() if courses else "Unknown"

    # ── Create/get tournament ─────────────────────────────────
    tid = db.get_or_create_tournament(event_name, primary_course)
    print(f"\n  Tournament DB ID: {tid}")

    # ── Backfill round data if needed ─────────────────────────
    print_header("Step 2: Checking Round Data")
    status = db.get_rounds_backfill_status()
    total_rounds = db.get_rounds_count()
    print(f"  Rounds in database: {total_rounds}")

    years_needed = []
    for year in [2020, 2021, 2022, 2023, 2024, 2025]:
        found = any(r["tour"] == "pga" and r["year"] == year for r in status)
        if not found:
            years_needed.append(year)

    if years_needed:
        print(f"  Need to backfill: {years_needed}")
        for year in years_needed:
            print(f"  Fetching PGA {year}...")
            raw = safe_api_call(f"fetch {year}", fetch_historical_rounds,
                                tour="pga", event_id="all", year=year)
            if raw:
                rows = _parse_rounds_response(raw, "pga", year)
                before = db.get_rounds_count()
                db.store_rounds(rows)
                after = db.get_rounds_count()
                print(f"    → {after - before} new rounds stored")
    else:
        for r in status:
            print(f"    {r['tour'].upper()} {r['year']}: "
                  f"{r['round_count']} rounds, {r['player_count']} players")

    # Also try to update current year (2026) — may be empty if season just started
    print(f"  Updating 2026 data...")
    raw_2026 = safe_api_call("fetch 2026", fetch_historical_rounds,
                              tour="pga", event_id="all", year=2026)
    if raw_2026:
        rows_2026 = _parse_rounds_response(raw_2026, "pga", 2026)
        before = db.get_rounds_count()
        db.store_rounds(rows_2026)
        after = db.get_rounds_count()
        if after > before:
            print(f"    → {after - before} new 2026 rounds")
        else:
            print(f"    → No new 2026 rounds yet")

    print(f"  Total rounds: {db.get_rounds_count()}")

    # ── Sync DG predictions ───────────────────────────────────
    print_header("Step 3: Syncing Data Golf Predictions")

    # Pre-tournament predictions (baseline + course-history)
    print("  Fetching pre-tournament predictions...")
    preds = safe_api_call("predictions", _call_api,
                           "preds/pre-tournament", {"tour": "pga", "odds_format": "percent"})
    if preds and isinstance(preds, dict):
        baseline = preds.get("baseline", [])
        baseline_ch = preds.get("baseline_history_fit", [])

        # Store baseline
        if baseline:
            import_id = db.log_csv_import(tid, "dg_baseline", "sim",
                                           "recent_form", "all", len(baseline), source="datagolf")
            metric_rows = []
            for p in baseline:
                pkey = normalize_name(p.get("player_name", ""))
                pdisp = display_name(p.get("player_name", ""))
                if not pkey:
                    continue
                for mname, field in [("Win %", "win"), ("Top 5 %", "top_5"),
                                      ("Top 10 %", "top_10"), ("Top 20 %", "top_20"),
                                      ("Make Cut %", "make_cut")]:
                    fval = _safe_float(p.get(field))
                    if fval is not None:
                        metric_rows.append({
                            "tournament_id": tid, "csv_import_id": import_id,
                            "player_key": pkey, "player_display": pdisp,
                            "metric_category": "sim", "data_mode": "recent_form",
                            "round_window": "all", "metric_name": mname,
                            "metric_value": fval, "metric_text": None,
                        })
            db.store_metrics(metric_rows)
            print(f"    → {len(metric_rows)} baseline prediction metrics")

        # Store course-history
        if baseline_ch:
            import_id2 = db.log_csv_import(tid, "dg_baseline_ch", "sim",
                                            "recent_form", "all", len(baseline_ch), source="datagolf")
            metric_rows2 = []
            for p in baseline_ch:
                pkey = normalize_name(p.get("player_name", ""))
                pdisp = display_name(p.get("player_name", ""))
                if not pkey:
                    continue
                for mname, field in [("Win % (CH)", "win"), ("Top 5 % (CH)", "top_5"),
                                      ("Top 10 % (CH)", "top_10"), ("Top 20 % (CH)", "top_20"),
                                      ("Make Cut % (CH)", "make_cut")]:
                    fval = _safe_float(p.get(field))
                    if fval is not None:
                        metric_rows2.append({
                            "tournament_id": tid, "csv_import_id": import_id2,
                            "player_key": pkey, "player_display": pdisp,
                            "metric_category": "sim", "data_mode": "recent_form",
                            "round_window": "all", "metric_name": mname,
                            "metric_value": fval, "metric_text": None,
                        })
                # Store dg_id as meta
                dg_id = _safe_float(p.get("dg_id"))
                if dg_id:
                    metric_rows2.append({
                        "tournament_id": tid, "csv_import_id": import_id2,
                        "player_key": pkey, "player_display": pdisp,
                        "metric_category": "meta", "data_mode": "recent_form",
                        "round_window": "all", "metric_name": "dg_id",
                        "metric_value": dg_id, "metric_text": None,
                    })
            db.store_metrics(metric_rows2)
            print(f"    → {len(metric_rows2)} course-history prediction metrics")

    # Player decompositions
    print("  Fetching player decompositions...")
    decomps = safe_api_call("decompositions", _call_api,
                             "preds/player-decompositions", {"tour": "pga"})
    if decomps:
        n = _store_decompositions_as_metrics(decomps, tid)
        print(f"    → {n} decomposition metrics")

    # Field updates
    print("  Fetching field updates...")
    from src.datagolf import fetch_field_updates
    field_data = safe_api_call("field", fetch_field_updates, "pga")
    if field_data:
        n = _store_field_as_metrics(field_data, tid)
        print(f"    → {n} field metrics")

    # ── Compute rolling stats ─────────────────────────────────
    print_header("Step 4: Computing Rolling Stats")
    field_players = db.get_all_players(tid)
    print(f"  Players in field: {len(field_players)}")

    primary_course_num = course_nums[0] if course_nums else None
    print(f"  Primary course num: {primary_course_num}")

    rolling = compute_rolling_metrics(tid, field_players, course_num=primary_course_num)
    print(f"  Metrics computed: {rolling.get('total_metrics', 0)}")
    print(f"    SG metrics: {rolling.get('sg_metrics', 0)}")
    print(f"    Traditional stats: {rolling.get('traditional_stat_metrics', 0)}")
    print(f"    Course-specific: {rolling.get('course_specific_metrics', 0)}")

    # ── Load course profile ───────────────────────────────────
    print_header("Step 5: Course Profile")
    profile = load_course_profile(primary_course)
    if profile:
        adj = course_to_model_weights(profile)
        ratings = profile.get("skill_ratings", {})
        print(f"  ✓ Course profile: {primary_course}")
        for k in ["sg_ott", "sg_app", "sg_arg", "sg_putting"]:
            if k in ratings:
                mult = adj.get(f"course_{k}_mult", 1.0)
                print(f"    {k}: {ratings[k]} ({mult}x weight)")
    else:
        print(f"  No course profile found for '{primary_course}'")
        print(f"  (Process screenshots: put images in data/course_images/")
        print(f"   then run this script again)")

    # ── Run composite model ───────────────────────────────────
    print_header("Step 6: Running Composite Model")
    weights = db.get_active_weights()
    print(f"  Weights: course={weights.get('course_fit', 0.4):.0%}, "
          f"form={weights.get('form', 0.4):.0%}, "
          f"momentum={weights.get('momentum', 0.2):.0%}")

    composite = compute_composite(tid, weights, course_name=primary_course)
    print(f"  Scored {len(composite)} players")

    if not composite:
        print("\n❌ No players scored. Check data.")
        sys.exit(1)

    # ── Output predictions ────────────────────────────────────
    print_header(f"PREDICTIONS: {event_name}")
    print(f"  Course: {courses}")
    print(f"  Course profile: {'Yes' if profile else 'No'}")
    print(f"  Field size: {len(composite)}")
    print()

    # Column headers
    hdr = (f"{'Rk':>3}  {'Player':<28} {'Comp':>6} {'Course':>7} "
           f"{'Form':>6} {'Mom':>5} {'Trend':>5}  {'DG Win%':>7}  {'DG T10%':>7}")
    print(hdr)
    print("─" * len(hdr))

    # Get DG probabilities for display
    sim_metrics = db.get_metrics_by_category(tid, "sim")
    dg_probs = {}
    for m in sim_metrics:
        pk = m["player_key"]
        if pk not in dg_probs:
            dg_probs[pk] = {}
        dg_probs[pk][m["metric_name"]] = m["metric_value"]

    for r in composite[:40]:
        trend = {"hot": "↑↑", "warming": "↑ ", "cooling": "↓ ", "cold": "↓↓"}.get(
            r.get("momentum_direction", ""), "— ")
        pk = r["player_key"]
        # Get best DG win probability (CH preferred)
        player_dg = dg_probs.get(pk, {})
        win_pct = player_dg.get("Win % (CH)") or player_dg.get("Win %")
        t10_pct = player_dg.get("Top 10 % (CH)") or player_dg.get("Top 10 %")

        win_str = f"{win_pct * 100:.1f}%" if win_pct else "  —  "
        t10_str = f"{t10_pct * 100:.1f}%" if t10_pct else "  —  "

        print(f"{r['rank']:>3}  {r['player_display']:<28} {r['composite']:>6.1f} "
              f"{r['course_fit']:>7.1f} {r['form']:>6.1f} {r['momentum']:>5.1f} "
              f"{trend:>5}  {win_str:>7}  {t10_str:>7}")

    # ── Key insights ──────────────────────────────────────────
    print()
    print_header("KEY INSIGHTS")

    # Strongest course fits
    by_course = sorted(composite, key=lambda x: x["course_fit"], reverse=True)
    print("\n  Best Course Fit:")
    for r in by_course[:5]:
        print(f"    {r['player_display']:<25} course_fit={r['course_fit']:.1f}  "
              f"({r.get('course_rounds', 0):.0f} rounds at course)")

    # Hottest form
    by_form = sorted(composite, key=lambda x: x["form"], reverse=True)
    print("\n  Best Current Form:")
    for r in by_form[:5]:
        print(f"    {r['player_display']:<25} form={r['form']:.1f}")

    # Biggest momentum
    hot_players = [r for r in composite if r.get("momentum_direction") == "hot"]
    hot_players.sort(key=lambda x: x["momentum"], reverse=True)
    if hot_players:
        print("\n  Trending Hot (↑↑):")
        for r in hot_players[:5]:
            print(f"    {r['player_display']:<25} momentum={r['momentum']:.1f}")

    # Cold fades
    cold_players = [r for r in composite if r.get("momentum_direction") == "cold"]
    cold_players.sort(key=lambda x: x["momentum"])
    if cold_players:
        print("\n  Trending Cold / Fades (↓↓):")
        for r in cold_players[:5]:
            print(f"    {r['player_display']:<25} momentum={r['momentum']:.1f}  "
                  f"(rank #{r['rank']})")

    # Value highlights: high course fit + hot momentum
    print("\n  Value Plays (Course Fit > 65 + Hot Momentum):")
    value_plays = [r for r in composite
                   if r.get("course_fit", 0) > 65 and r.get("momentum_direction") == "hot"
                   and r["rank"] > 5]
    if value_plays:
        for r in value_plays[:5]:
            print(f"    {r['player_display']:<25} #{r['rank']}  "
                  f"course={r['course_fit']:.1f}  form={r['form']:.1f}  "
                  f"momentum={r['momentum']:.1f}")
    else:
        print("    (none matching criteria)")

    # ── Generate card ─────────────────────────────────────────
    print_header("Step 7: Generating Betting Card")
    filepath = generate_card(
        event_name,
        primary_course,
        composite,
        {},  # no live odds — add ODDS_API_KEY to get live odds
        output_dir="output",
    )
    print(f"  Card saved to: {filepath}")
    print(f"\n  Open it: open {filepath}")

    print()
    print("=" * 60)
    print("  DONE! Predictions complete.")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
