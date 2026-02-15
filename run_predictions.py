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
    fetch_all_outright_odds,
    fetch_matchup_odds,
    store_skill_ratings_as_metrics,
    store_rankings_as_metrics,
    store_approach_skill_as_metrics,
)
from src.rolling_stats import compute_rolling_metrics
from src.models.composite import compute_composite
from src.course_profile import load_course_profile, course_to_model_weights
from src.odds import get_best_odds
from src.value import find_value_bets
from src.card import generate_card
from src.player_normalizer import normalize_name, display_name
from src.ai_brain import (
    is_ai_available,
    pre_tournament_analysis,
    make_betting_decisions,
    apply_ai_adjustments,
    get_ai_status,
)


def print_header(text):
    print(f"\n{'─' * 60}")
    print(f"  {text}")
    print(f"{'─' * 60}")


def _wrap_text(text: str, width: int = 56) -> list[str]:
    """Word-wrap text for terminal display."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    return lines


def safe_api_call(description, func, *args, **kwargs):
    """Call an API function with rate-limit awareness."""
    time.sleep(2)  # Polite pause between API calls
    try:
        return func(*args, **kwargs)
    except Exception as e:
        print(f"  ⚠ {description} error: {e}")
        return None


def _check_and_run_post_review(skip_tournament_id: int = None):
    """
    Check if any past completed tournament needs a post-review.

    Looks at ai_decisions for past tournaments. If a tournament has
    pre_analysis or betting_decisions but no post_review, and the
    tournament is over (results available), run the full learning cycle.

    skip_tournament_id: the current week's tournament to exclude
    """
    from src.learning import post_tournament_learn, log_predictions_for_tournament
    from src.ai_brain import post_tournament_review
    from src.datagolf import auto_ingest_results

    conn = db.get_conn()

    # Find tournaments that have AI pre-analysis but no post-review
    reviewed = conn.execute(
        "SELECT DISTINCT tournament_id FROM ai_decisions WHERE phase = 'post_review'"
    ).fetchall()
    reviewed_ids = {r["tournament_id"] for r in reviewed}

    analyzed = conn.execute(
        "SELECT DISTINCT tournament_id FROM ai_decisions WHERE phase = 'pre_analysis'"
    ).fetchall()
    analyzed_ids = {r["tournament_id"] for r in analyzed}

    pending_review = analyzed_ids - reviewed_ids

    if not pending_review:
        # Also check: any tournament with logged predictions but no post-review?
        has_preds = conn.execute(
            """SELECT DISTINCT tournament_id FROM prediction_log
               WHERE tournament_id NOT IN (
                   SELECT DISTINCT tournament_id FROM ai_decisions WHERE phase = 'post_review'
               )"""
        ).fetchall()
        pending_review = {r["tournament_id"] for r in has_preds}

    # Also check for tournaments with results but no review
    if not pending_review:
        all_tournaments = conn.execute(
            "SELECT DISTINCT id, name, course FROM tournaments"
        ).fetchall()
        for t in all_tournaments:
            results = conn.execute(
                "SELECT COUNT(*) as cnt FROM results WHERE tournament_id = ?",
                (t["id"],),
            ).fetchone()
            if results and results["cnt"] > 0 and t["id"] not in reviewed_ids:
                pending_review.add(t["id"])

    conn.close()

    # Skip the current week's tournament (it hasn't happened yet)
    if skip_tournament_id:
        pending_review.discard(skip_tournament_id)

    if not pending_review:
        print("  No previous tournament needs review.")
        print("  (Post-review runs automatically after tournaments complete)")
        return

    for tid in pending_review:
        conn = db.get_conn()
        t_info = conn.execute(
            "SELECT * FROM tournaments WHERE id = ?", (tid,)
        ).fetchone()
        conn.close()

        if not t_info:
            continue

        t_name = t_info["name"]
        t_course = t_info["course"]
        print(f"\n  Found unreviewed tournament: {t_name}")

        # Try to get results from DG round data
        # Look up event_id from metrics or schedule
        conn = db.get_conn()
        meta = conn.execute(
            """SELECT metric_value FROM metrics
               WHERE tournament_id = ? AND metric_name = 'dg_id'
               LIMIT 1""",
            (tid,),
        ).fetchone()

        # Check if results already exist
        existing_results = conn.execute(
            "SELECT COUNT(*) as cnt FROM results WHERE tournament_id = ?",
            (tid,),
        ).fetchone()
        conn.close()

        has_results = existing_results and existing_results["cnt"] > 0

        if not has_results:
            # Try to ingest results from the most recent completed tournament
            # We need the event_id — try to find it from the schedule
            print(f"  Checking for results data...")
            try:
                schedule = safe_api_call("schedule", _call_api,
                                        "get-schedule", {"tour": "pga"})
                if isinstance(schedule, dict):
                    schedule = schedule.get("schedule", [])

                # Find completed events (ones with a winner or past end_date)
                from datetime import datetime as dt
                today = dt.now().date()
                for evt in (schedule or []):
                    evt_name = evt.get("event_name", "")
                    # Check if this matches our tournament
                    if (t_name.lower() in evt_name.lower()
                            or evt_name.lower() in t_name.lower()):
                        end_date_str = evt.get("end_date", "")
                        if end_date_str:
                            try:
                                end_date = dt.strptime(end_date_str, "%Y-%m-%d").date()
                                if end_date < today:
                                    event_id = evt.get("event_id", "")
                                    calendar_year = end_date.year
                                    print(f"  Ingesting results for {evt_name} (event_id={event_id})...")
                                    result = auto_ingest_results(tid, str(event_id), calendar_year)
                                    if result.get("status") == "ok":
                                        has_results = True
                                        print(f"    → {result.get('stored', 0)} results ingested")
                                    else:
                                        print(f"    → {result.get('message', 'No results available')}")
                            except (ValueError, TypeError):
                                pass
                        break
            except Exception as e:
                print(f"  ⚠ Could not fetch results: {e}")

        if not has_results:
            print(f"  Tournament may still be in progress or no results available.")
            print(f"  Skipping post-review for now.")
            continue

        # Run the full learning cycle
        print(f"\n  Running post-tournament learning cycle...")

        try:
            # Get value bets from prediction_log if available
            conn = db.get_conn()
            pred_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM prediction_log WHERE tournament_id = ?",
                (tid,),
            ).fetchone()
            conn.close()

            learn_result = post_tournament_learn(
                tournament_id=tid,
                course_name=t_course,
            )

            scoring = learn_result.get("steps", {}).get("scoring", {})
            if scoring.get("status") == "ok":
                print(f"    Picks scored: {scoring.get('scored', 0)}, "
                      f"Hits: {scoring.get('hits', 0)}, "
                      f"Hit rate: {scoring.get('hit_rate', 0):.0%}")
                print(f"    Profit: {scoring.get('total_profit', 0):+.1f} units")

            cal = learn_result.get("calibration", {})
            if cal.get("brier_score"):
                print(f"    Brier score: {cal['brier_score']:.4f}")
            roi = cal.get("roi", {})
            if roi.get("total_bets"):
                print(f"    Cumulative ROI: {roi['roi_pct']:.1f}% "
                      f"({roi['total_profit']:+.1f}u over {roi['total_bets']} bets)")

        except Exception as e:
            print(f"    ⚠ Learning cycle error: {e}")

        # Run AI post-tournament review (stores learnings in memory)
        if is_ai_available():
            try:
                print(f"\n  Running AI post-tournament review...")
                scoring_result = learn_result.get("steps", {}).get("scoring", {})

                ai_review = post_tournament_review(
                    tournament_id=tid,
                    scoring_result=scoring_result,
                    tournament_name=t_name,
                    course_name=t_course,
                )

                summary = ai_review.get("summary", "")
                if summary:
                    print(f"\n  AI Review Summary:")
                    for line in _wrap_text(summary, 56):
                        print(f"    {line}")

                learnings = ai_review.get("learnings", [])
                if learnings:
                    print(f"\n  Learnings stored in memory ({len(learnings)}):")
                    for l in learnings:
                        print(f"    [{l['topic']}] {l['insight'][:80]}...")

                wt = ai_review.get("weight_suggestions", {})
                if wt:
                    print(f"\n  AI weight suggestions: "
                          f"course={wt.get('course_fit', '?')}, "
                          f"form={wt.get('form', '?')}, "
                          f"momentum={wt.get('momentum', '?')}")

            except Exception as e:
                print(f"    ⚠ AI review error: {e}")

        print(f"\n  ✓ Post-review complete for {t_name}")


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

    # ── Get current event (needed early for post-review skip) ──
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

    # ── Post-Tournament Review of PREVIOUS tournaments ────────
    print_header("Step 1b: Post-Tournament Review Check")
    _check_and_run_post_review(skip_tournament_id=tid)

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

    # ── Sync DG Skill Ratings, Rankings & Approach Skill ──────
    print_header("Step 3b: Syncing DG Skill Data")

    # Get list of player_keys currently in field (for matching)
    field_keys = db.get_all_players(tid)
    print(f"  Field size: {len(field_keys)} players")

    # Skill Ratings — true SG per category (field-strength adjusted)
    print("  Fetching DG skill ratings...")
    n_skill = safe_api_call("skill ratings", store_skill_ratings_as_metrics, tid, field_keys)
    if n_skill:
        print(f"    → {n_skill} skill rating metrics")
    else:
        print(f"    → No skill ratings stored (may not match field)")

    # DG Rankings — global rank + skill estimate
    print("  Fetching DG rankings...")
    n_rank = safe_api_call("rankings", store_rankings_as_metrics, tid, field_keys)
    if n_rank:
        print(f"    → {n_rank} ranking metrics")
    else:
        print(f"    → No ranking metrics stored")

    # Approach Skill — detailed approach by yardage/lie
    print("  Fetching approach skill data...")
    n_app = safe_api_call("approach skill", store_approach_skill_as_metrics, tid, field_keys)
    if n_app:
        print(f"    → {n_app} approach skill metrics")
    else:
        print(f"    → No approach skill metrics stored")

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
        source = profile.get("course_facts", {}).get("source", "screenshots")
        adj = course_to_model_weights(profile)
        ratings = profile.get("skill_ratings", {})
        print(f"  ✓ Course profile: {primary_course} (source: {source})")
        for k in ["sg_ott", "sg_app", "sg_arg", "sg_putting"]:
            if k in ratings:
                mult = adj.get(f"course_{k}_mult", 1.0)
                print(f"    {k}: {ratings[k]} ({mult}x weight)")
    else:
        # Auto-generate from DG decomposition data
        print(f"  No saved profile for '{primary_course}'")
        print(f"  Auto-generating from DG decomposition data...")
        from src.course_profile import generate_profile_from_decompositions
        if decomps:
            profile = generate_profile_from_decompositions(decomps)
            if profile:
                adj = course_to_model_weights(profile)
                ratings = profile.get("skill_ratings", {})
                print(f"  ✓ Auto-generated course profile: {primary_course}")
                for k in ["sg_ott", "sg_app", "sg_arg", "sg_putting"]:
                    if k in ratings:
                        mult = adj.get(f"course_{k}_mult", 1.0)
                        print(f"    {k}: {ratings[k]} ({mult}x weight)")
                print(f"  (Saved to data/courses/ for future use)")
                print(f"  (For more detail, add screenshots to data/course_images/)")
            else:
                print(f"  Could not auto-generate profile (not enough data)")
        else:
            print(f"  No decomposition data available for auto-generation")

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

    # ── AI Pre-Tournament Analysis ──────────────────────────────
    print_header("Step 6b: AI Pre-Tournament Analysis")
    ai_pre_analysis = None
    ai_decisions = None

    if is_ai_available():
        ai_status = get_ai_status()
        print(f"  AI Provider: {ai_status['provider']} ({ai_status['model']})")
        print(f"  Persistent memories: {ai_status['memory_count']}")
        if ai_status['memory_topics']:
            print(f"  Memory topics: {', '.join(ai_status['memory_topics'][:10])}")

        try:
            print(f"\n  Running pre-tournament analysis...")
            print(f"  (Sending field, course profile, and memories to AI)")
            ai_pre_analysis = pre_tournament_analysis(
                tournament_id=tid,
                composite_results=composite,
                course_profile=profile if profile else None,
                tournament_name=event_name,
                course_name=primary_course,
            )

            # Display AI narrative
            narrative = ai_pre_analysis.get("course_narrative", "")
            if narrative:
                print(f"\n  AI Narrative:")
                # Word-wrap the narrative for terminal
                for line in _wrap_text(narrative, 56):
                    print(f"    {line}")

            key_factors = ai_pre_analysis.get("key_factors", [])
            if key_factors:
                print(f"\n  Key Factors This Week:")
                for i, kf in enumerate(key_factors, 1):
                    print(f"    {i}. {kf}")

            # Show players to watch
            watch = ai_pre_analysis.get("players_to_watch", [])
            if watch:
                print(f"\n  Players to Watch (AI sees edge):")
                for p in watch:
                    adj = p.get("adjustment", 0)
                    sign = "+" if adj > 0 else ""
                    print(f"    ✦ {p['player']:<25} {sign}{adj:.1f} — {p['edge']}")

            # Show fades
            fades = ai_pre_analysis.get("players_to_fade", [])
            if fades:
                print(f"\n  Players to Fade (AI sees risk):")
                for p in fades:
                    adj = p.get("adjustment", 0)
                    sign = "+" if adj > 0 else ""
                    print(f"    ✗ {p['player']:<25} {sign}{adj:.1f} — {p['reason']}")

            conf = ai_pre_analysis.get("confidence", 0)
            print(f"\n  AI Confidence in model this week: {conf:.0%}")

            # Apply AI adjustments to composite scores
            old_top3 = [r["player_display"] for r in composite[:3]]
            composite = apply_ai_adjustments(composite, ai_pre_analysis)
            new_top3 = [r["player_display"] for r in composite[:3]]
            if old_top3 != new_top3:
                print(f"\n  ⚡ Rankings shifted after AI adjustments")
                print(f"     Before: {', '.join(old_top3)}")
                print(f"     After:  {', '.join(new_top3)}")
            else:
                print(f"\n  Rankings unchanged after AI adjustments")

        except Exception as e:
            print(f"\n  ⚠ AI analysis error: {e}")
            print(f"  Continuing without AI adjustments...")
    else:
        print("  AI not available (no OPENAI_API_KEY set)")
        print("  Running quantitative model only")

    # ── Fetch live odds from Data Golf ──────────────────────────
    from src.odds import _get_preferred_book
    _pbook = _get_preferred_book()
    print_header("Step 7: Fetching Live Sportsbook Odds")
    print(f"  Primary book: {_pbook} (EV calculated against {_pbook} odds)")
    print("  Also tracking: DraftKings, FanDuel, BetMGM, Pinnacle, + 10 others")

    all_odds_by_market = safe_api_call("outright odds", fetch_all_outright_odds, "pga")
    if all_odds_by_market is None:
        all_odds_by_market = {}

    from src.value import DEFAULT_EV_THRESHOLD
    print(f"  EV threshold: {DEFAULT_EV_THRESHOLD:.0%} (set EV_THRESHOLD env to change)")

    value_bets = {}
    for market_key, odds_list in all_odds_by_market.items():
        if not odds_list:
            continue
        best = get_best_odds(odds_list)
        # Map market to bet type
        if market_key == "outrights":
            bt = "outright"
        elif market_key == "frl":
            bt = "frl"
        else:
            bt = market_key.replace("top_", "top")
        vb = find_value_bets(composite, best, bet_type=bt, tournament_id=tid)
        value_bets[bt] = vb
        value_count = sum(1 for v in vb if v.get("is_value"))
        book_count = len(set(o["bookmaker"] for o in odds_list))
        print(f"    {market_key}: {len(best)} players, {book_count} books, "
              f"{value_count} value plays")

    if not all_odds_by_market:
        print("    ⚠ Could not fetch odds (may not be posted yet)")

    # ── AI Betting Decisions ─────────────────────────────────────
    if ai_pre_analysis and is_ai_available() and value_bets:
        print_header("Step 7b: AI Betting Decisions")
        try:
            print("  AI is reviewing value bets and building a portfolio...")
            ai_decisions = make_betting_decisions(
                tournament_id=tid,
                value_bets_by_type=value_bets,
                pre_analysis=ai_pre_analysis,
                composite_results=composite,
                tournament_name=event_name,
                course_name=primary_course,
            )

            decisions_list = ai_decisions.get("decisions", [])
            if decisions_list:
                print(f"\n  AI Recommended Bets ({len(decisions_list)} picks):")
                print(f"  {'Player':<25} {'Bet':<10} {'Odds':>8} {'Stake':>8} "
                      f"{'Conf':<8} Reasoning")
                print(f"  {'─' * 90}")
                for d in decisions_list:
                    reasoning = d.get("reasoning", "")
                    # Truncate reasoning for terminal display
                    if len(reasoning) > 60:
                        reasoning = reasoning[:57] + "..."
                    print(f"  {d['player']:<25} {d['bet_type']:<10} "
                          f"{d.get('odds', '?'):>8} {d.get('recommended_stake', '?'):>8} "
                          f"{d.get('confidence', '?'):<8} {reasoning}")

            portfolio_notes = ai_decisions.get("portfolio_notes", "")
            if portfolio_notes:
                print(f"\n  Portfolio Notes:")
                for line in _wrap_text(portfolio_notes, 56):
                    print(f"    {line}")

            pass_notes = ai_decisions.get("pass_notes", "")
            if pass_notes:
                print(f"\n  Passing On:")
                for line in _wrap_text(pass_notes, 56):
                    print(f"    {line}")

            total_units = ai_decisions.get("total_units", 0)
            expected_roi = ai_decisions.get("expected_roi", "N/A")
            print(f"\n  Total units wagered: {total_units}")
            print(f"  Expected ROI: {expected_roi}")

            # ── Auto-log AI picks to the picks table for post-tournament scoring ──
            if decisions_list:
                # Build a lookup from composite results for model scores
                composite_lookup = {r["player_key"]: r for r in composite}
                display_to_key = {r["player_display"].lower(): r["player_key"] for r in composite}

                pick_rows = []
                for d in decisions_list:
                    # Match AI player name to a composite player_key
                    player_name = d.get("player", "")
                    pk = normalize_name(player_name)
                    # Fallback: try matching by display name
                    if pk not in composite_lookup:
                        pk = display_to_key.get(player_name.lower(), pk)

                    comp_data = composite_lookup.get(pk, {})

                    # Parse odds string to int (e.g. "+200" -> 200, "-150" -> -150)
                    odds_str = str(d.get("odds", ""))
                    try:
                        odds_int = int(odds_str.replace("+", ""))
                    except (ValueError, TypeError):
                        odds_int = None

                    # Map AI bet_type names to our standard types
                    ai_bt = d.get("bet_type", "").lower().replace(" ", "_")
                    bt_map = {
                        "outright": "outright", "outright_win": "outright",
                        "top_5": "top5", "top5": "top5", "top_5_finish": "top5",
                        "top_10": "top10", "top10": "top10", "top_10_finish": "top10",
                        "top_20": "top20", "top20": "top20", "top_20_finish": "top20",
                        "frl": "frl", "first_round_leader": "frl",
                        "make_cut": "make_cut",
                    }
                    bet_type = bt_map.get(ai_bt, ai_bt)

                    market_implied = None
                    if odds_int is not None:
                        from src.odds import american_to_implied_prob
                        market_implied = american_to_implied_prob(odds_int)

                    pick_rows.append({
                        "tournament_id": tid,
                        "bet_type": bet_type,
                        "player_key": pk,
                        "player_display": d.get("player", ""),
                        "opponent_key": None,
                        "opponent_display": None,
                        "composite_score": comp_data.get("composite"),
                        "course_fit_score": comp_data.get("course_fit"),
                        "form_score": comp_data.get("form"),
                        "momentum_score": comp_data.get("momentum"),
                        "model_prob": d.get("model_ev"),
                        "market_odds": odds_str,
                        "market_implied_prob": market_implied,
                        "ev": d.get("model_ev"),
                        "confidence": d.get("confidence"),
                        "reasoning": d.get("reasoning", ""),
                    })

                if pick_rows:
                    db.store_picks(pick_rows)
                    print(f"\n  ✓ {len(pick_rows)} AI picks logged for post-tournament scoring")

        except Exception as e:
            print(f"\n  ⚠ AI betting decisions error: {e}")
            print(f"  Value bets still shown below without AI portfolio optimization")

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

    # ── Value bets with real sportsbook odds ──────────────────
    PREFERRED_BOOK = _get_preferred_book()
    for bt_label, bt_key in [("OUTRIGHT WINNER", "outright"),
                              ("TOP 5 FINISH", "top5"),
                              ("TOP 10 FINISH", "top10"),
                              ("TOP 20 FINISH", "top20"),
                              ("FIRST ROUND LEADER", "frl")]:
        vb_list = value_bets.get(bt_key, [])
        value_only = [v for v in vb_list if v.get("is_value")]
        if not value_only:
            continue

        print()
        print_header(f"VALUE BETS: {bt_label} ({PREFERRED_BOOK})")
        print(f"  {'Player':<25} {'Rank':>4}  {'Odds':>10} "
              f"{'Model%':>7} {'Market%':>8} {'EV':>7}  Better Elsewhere?")
        print("  " + "─" * 85)
        for v in value_only[:10]:
            odds_str = f"+{v['best_odds']}" if v["best_odds"] > 0 else str(v["best_odds"])
            better = v.get("better_odds_note", "")
            if better:
                better = f"→ {better}"
            print(f"  {v['player_display']:<25} #{v['rank']:>2}  {odds_str:>10} "
                  f"{v['model_prob']:>6.1%} {v['market_prob']:>7.1%} "
                  f"{v['ev']:>+6.1%}  {better}")

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

    # ── Log predictions for next week's review ──────────────────
    if value_bets:
        from src.learning import log_predictions_for_tournament
        try:
            n_logged = log_predictions_for_tournament(tid, value_bets)
            if n_logged:
                print(f"\n  Logged {n_logged} predictions for post-tournament review")
        except Exception as e:
            print(f"\n  ⚠ Could not log predictions: {e}")

    # ── Generate card ─────────────────────────────────────────
    print_header("Step 8: Generating Betting Card")
    filepath = generate_card(
        event_name,
        primary_course,
        composite,
        value_bets,
        output_dir="output",
        ai_pre_analysis=ai_pre_analysis,
        ai_decisions=ai_decisions,
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
