"""
Data Golf API Client

Handles all interactions with the Data Golf API:
  - Historical round-level data (backfill)
  - Pre-tournament predictions
  - Player skill decompositions
  - Field updates (salaries, tee times, WDs)
  - Auto-results ingestion from round data

Requires DATAGOLF_API_KEY environment variable.
"""

import os
import requests
from typing import Optional

from src import db
from src.player_normalizer import normalize_name, display_name

BASE_URL = "https://feeds.datagolf.com"


def _safe_float(val) -> float | None:
    """Safely convert a value to float, returning None for non-numeric."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _get_api_key() -> str:
    key = os.environ.get("DATAGOLF_API_KEY", "")
    if not key:
        raise RuntimeError(
            "DATAGOLF_API_KEY not set. Get your key from https://datagolf.com/api-access "
            "and set it: export DATAGOLF_API_KEY=your_key_here (or add to .env)"
        )
    return key


def _call_api(endpoint: str, params: dict = None) -> dict | list:
    """
    Call a Data Golf API endpoint.

    Returns parsed JSON (dict or list).
    Raises on HTTP errors or missing key.
    """
    key = _get_api_key()
    params = params or {}
    params["key"] = key
    params.setdefault("file_format", "json")

    url = f"{BASE_URL}/{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=120)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Data Golf API timeout on {endpoint} (120s)")
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"Data Golf API HTTP error on {endpoint}: {e}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Data Golf API connection error on {endpoint}: {e}")

    try:
        return resp.json()
    except ValueError:
        raise RuntimeError(f"Data Golf API returned non-JSON for {endpoint}: {resp.text[:200]}")


# ═══════════════════════════════════════════════════════════════════
#  Historical Raw Data
# ═══════════════════════════════════════════════════════════════════

def fetch_historical_rounds(tour: str = "pga", event_id: str = "all",
                            year: int = 2025) -> list[dict]:
    """
    Fetch round-level data from the historical-raw-data/rounds endpoint.

    Returns the raw JSON (list of event objects with nested round data).
    One call with event_id='all' returns the entire season.
    """
    data = _call_api("historical-raw-data/rounds", {
        "tour": tour,
        "event_id": event_id,
        "year": str(year),
    })
    return data


def _parse_rounds_response(raw_data, tour: str, year: int) -> list[dict]:
    """
    Parse the nested Data Golf rounds response into flat rows for the DB.

    DG response structure:
    {
        "event_completed": "2025-01-12",
        "event_id": "535",
        "event_name": "The Sentry",
        "scores": [
            {
                "dg_id": 12345,
                "player_name": "Scheffler, Scottie",
                "fin_text": "1",
                "round_1": { "score": 65, "sg_total": 5.2, ... },
                "round_2": { ... },
                ...
            },
            ...
        ]
    }
    """
    rows = []

    # raw_data can be:
    #   1. A single event dict (when event_id is specific): {"scores": [...], "event_name": ...}
    #   2. A dict keyed by event_id (when event_id='all'): {"14": {"scores": [...]}, "16": {...}}
    #   3. A list of event dicts
    if isinstance(raw_data, dict):
        if "scores" in raw_data:
            # Single event response
            events = [raw_data]
        else:
            # Dict keyed by event_id — check if values look like event dicts
            first_val = next(iter(raw_data.values()), None) if raw_data else None
            if isinstance(first_val, dict) and ("scores" in first_val or "event_name" in first_val):
                events = list(raw_data.values())
            else:
                events = [raw_data]
    elif isinstance(raw_data, list):
        events = raw_data
    else:
        return rows

    for event in events:
        if not isinstance(event, dict):
            continue
        event_completed = event.get("event_completed", "")
        event_id = str(event.get("event_id", ""))
        event_name = event.get("event_name", "")
        season = event.get("season", year)

        scores = event.get("scores", [])
        for player in scores:
            if not isinstance(player, dict):
                continue
            dg_id = player.get("dg_id")
            raw_name = player.get("player_name", "")
            fin_text = player.get("fin_text", "")

            if not dg_id:
                continue

            pkey = normalize_name(raw_name)

            # Each round is keyed as round_1, round_2, round_3, round_4
            for round_num in range(1, 5):
                round_key = f"round_{round_num}"
                rd = player.get(round_key)
                if not rd or not isinstance(rd, dict):
                    continue

                # Skip if no score (incomplete round)
                if rd.get("score") is None:
                    continue

                rows.append({
                    "dg_id": dg_id,
                    "player_name": raw_name,
                    "player_key": pkey,
                    "tour": tour,
                    "season": season if season else year,
                    "year": year,
                    "event_id": event_id,
                    "event_name": event_name,
                    "event_completed": event_completed,
                    "course_name": rd.get("course_name", ""),
                    "course_num": rd.get("course_num"),
                    "course_par": rd.get("course_par"),
                    "round_num": round_num,
                    "score": rd.get("score"),
                    "sg_total": rd.get("sg_total"),
                    "sg_ott": rd.get("sg_ott"),
                    "sg_app": rd.get("sg_app"),
                    "sg_arg": rd.get("sg_arg"),
                    "sg_putt": rd.get("sg_putt"),
                    "sg_t2g": rd.get("sg_t2g"),
                    "driving_dist": rd.get("driving_dist"),
                    "driving_acc": rd.get("driving_acc"),
                    "gir": rd.get("gir"),
                    "scrambling": rd.get("scrambling"),
                    "prox_fw": rd.get("prox_fw"),
                    "prox_rgh": rd.get("prox_rgh"),
                    "great_shots": rd.get("great_shots"),
                    "poor_shots": rd.get("poor_shots"),
                    "birdies": rd.get("birdies"),
                    "pars": rd.get("pars"),
                    "bogies": rd.get("bogies"),
                    "doubles_or_worse": rd.get("doubles_or_worse"),
                    "eagles_or_better": rd.get("eagles_or_better"),
                    "fin_text": fin_text,
                    "teetime": rd.get("teetime"),
                    "start_hole": rd.get("start_hole"),
                })

    return rows


def backfill_rounds(tours: list[str] = None, years: list[int] = None) -> dict:
    """
    Pull and store historical round data for given tours and years.

    Default: PGA Tour, 2024-2026.
    Uses INSERT OR IGNORE so safe to re-run (skips existing rounds).

    Returns: {(tour, year): {"rounds_fetched": N, "rounds_new": N}}
    """
    if tours is None:
        tours = ["pga"]
    if years is None:
        years = [2024, 2025, 2026]

    summary = {}
    for tour in tours:
        for year in years:
            key = f"{tour}_{year}"
            print(f"  Fetching {tour.upper()} {year}...")
            try:
                raw = fetch_historical_rounds(tour=tour, event_id="all", year=year)
                rows = _parse_rounds_response(raw, tour, year)

                before = db.get_rounds_count()
                db.store_rounds(rows)
                after = db.get_rounds_count()

                summary[key] = {
                    "rounds_fetched": len(rows),
                    "rounds_new": after - before,
                    "status": "ok",
                }
                print(f"    → {len(rows)} rounds fetched, {after - before} new")
            except Exception as e:
                summary[key] = {"status": "error", "error": str(e)}
                print(f"    → ERROR: {e}")

    return summary


# ═══════════════════════════════════════════════════════════════════
#  Pre-Tournament Predictions
# ═══════════════════════════════════════════════════════════════════

def fetch_pre_tournament(tour: str = "pga") -> list[dict]:
    """
    Fetch pre-tournament predictions (baseline + course-history models).

    Returns list of player prediction dicts with keys like:
      dg_id, player_name, win (baseline), win_course_history,
      top_5, top_10, top_20, make_cut, etc.
    """
    return _call_api("preds/pre-tournament", {
        "tour": tour,
        "odds_format": "percent",
    })


def _store_predictions_as_metrics(predictions: list | dict,
                                  tournament_id: int) -> int:
    """
    Map DG pre-tournament predictions into the metrics table
    as sim-equivalent data (so form.py and value.py can use them).
    """
    # Handle response format: DG may return a list directly or a dict wrapper
    if isinstance(predictions, list):
        player_list = predictions
    elif isinstance(predictions, dict):
        # Try common wrapper keys
        player_list = []
        for key in ["baseline_history_fit", "baseline", "data", "players"]:
            if key in predictions and isinstance(predictions[key], list):
                player_list = predictions[key]
                break
        if not player_list and "player_name" in predictions:
            # Single player dict
            player_list = [predictions]
    else:
        return 0

    import_id = db.log_csv_import(
        tournament_id, "datagolf_pre_tournament", "sim",
        "recent_form", "all", len(player_list), source="datagolf"
    )

    metric_rows = []
    for p in player_list:
        if not isinstance(p, dict):
            continue
        raw_name = p.get("player_name", "")
        pkey = normalize_name(raw_name)
        pdisp = display_name(raw_name)

        if not pkey:
            continue

        # Map DG probability fields to our sim metric names
        prob_fields = {
            "Win %": p.get("win"),
            "Top 5 %": p.get("top_5"),
            "Top 10 %": p.get("top_10"),
            "Top 20 %": p.get("top_20"),
            "Make Cut %": p.get("make_cut"),
        }
        # Also store course-history model versions if available
        prob_fields_ch = {
            "Win % (CH)": p.get("win_course_history"),
            "Top 5 % (CH)": p.get("top_5_course_history"),
            "Top 10 % (CH)": p.get("top_10_course_history"),
            "Top 20 % (CH)": p.get("top_20_course_history"),
            "Make Cut % (CH)": p.get("make_cut_course_history"),
        }

        for metric_name, value in {**prob_fields, **prob_fields_ch}.items():
            fval = _safe_float(value)
            if fval is not None:
                metric_rows.append({
                    "tournament_id": tournament_id,
                    "csv_import_id": import_id,
                    "player_key": pkey,
                    "player_display": pdisp,
                    "metric_category": "sim",
                    "data_mode": "recent_form",
                    "round_window": "all",
                    "metric_name": metric_name,
                    "metric_value": fval,
                    "metric_text": None,
                })

        # Store dg_id as meta
        dg_id_val = _safe_float(p.get("dg_id"))
        if dg_id_val is not None:
            metric_rows.append({
                "tournament_id": tournament_id,
                "csv_import_id": import_id,
                "player_key": pkey,
                "player_display": pdisp,
                "metric_category": "meta",
                "data_mode": "recent_form",
                "round_window": "all",
                "metric_name": "dg_id",
                "metric_value": dg_id_val,
                "metric_text": None,
            })

    db.store_metrics(metric_rows)
    return len(metric_rows)


# ═══════════════════════════════════════════════════════════════════
#  Player Skill Decompositions
# ═══════════════════════════════════════════════════════════════════

def fetch_decompositions(tour: str = "pga") -> list[dict]:
    """
    Fetch player skill decompositions (course-adjusted SG predictions).
    """
    return _call_api("preds/player-decompositions", {"tour": tour})


def _store_decompositions_as_metrics(decompositions: list | dict,
                                     tournament_id: int) -> int:
    """Map DG decompositions into metrics as course-specific data."""
    if isinstance(decompositions, dict):
        if "player_name" in decompositions:
            # Single player dict — wrap in list
            player_list = [decompositions]
        else:
            # Try common wrapper keys
            player_list = []
            for key in ["data", "players", "decompositions"]:
                if key in decompositions and isinstance(decompositions[key], list):
                    player_list = decompositions[key]
                    break
    elif isinstance(decompositions, list):
        player_list = decompositions
    else:
        return 0

    if not player_list:
        return 0

    import_id = db.log_csv_import(
        tournament_id, "datagolf_decompositions", "dg_decomposition",
        "course_specific", "all", len(player_list), source="datagolf"
    )

    metric_rows = []
    for p in player_list:
        if not isinstance(p, dict):
            continue
        raw_name = p.get("player_name", "")
        pkey = normalize_name(raw_name)
        pdisp = display_name(raw_name)
        if not pkey:
            continue

        # DG decomposition fields — actual API field names from preds/player-decompositions
        sg_fields = {
            "dg_sg_total": p.get("final_pred") or p.get("sg_total") or p.get("total"),
            "dg_baseline_pred": p.get("baseline_pred"),
            "dg_total_fit_adj": p.get("total_fit_adjustment"),
            "dg_total_ch_adj": p.get("total_course_history_adjustment"),
            "dg_sg_category_adj": p.get("strokes_gained_category_adjustment"),
            "dg_driving_dist_adj": p.get("driving_distance_adjustment"),
            "dg_driving_acc_adj": p.get("driving_accuracy_adjustment"),
            "dg_cf_approach": p.get("cf_approach_comp"),
            "dg_cf_short": p.get("cf_short_comp"),
        }

        for metric_name, value in sg_fields.items():
            fval = _safe_float(value)
            if fval is not None:
                metric_rows.append({
                    "tournament_id": tournament_id,
                    "csv_import_id": import_id,
                    "player_key": pkey,
                    "player_display": pdisp,
                    "metric_category": "dg_decomposition",
                    "data_mode": "course_specific",
                    "round_window": "all",
                    "metric_name": metric_name,
                    "metric_value": fval,
                    "metric_text": None,
                })

    db.store_metrics(metric_rows)
    return len(metric_rows)


# ═══════════════════════════════════════════════════════════════════
#  Field Updates
# ═══════════════════════════════════════════════════════════════════

def fetch_field_updates(tour: str = "pga") -> list[dict]:
    """Fetch current field with tee times, salaries, WDs."""
    return _call_api("field-updates", {"tour": tour})


def _store_field_as_metrics(field_data: list | dict,
                            tournament_id: int) -> int:
    """Store field updates (salaries, tee times) as meta metrics."""
    if isinstance(field_data, list):
        player_list = field_data
    elif isinstance(field_data, dict):
        player_list = []
        for key in ["field", "data", "players"]:
            if key in field_data and isinstance(field_data[key], list):
                player_list = field_data[key]
                break
        if not player_list and "player_name" in field_data:
            player_list = [field_data]
    else:
        return 0

    if not player_list:
        return 0

    import_id = db.log_csv_import(
        tournament_id, "datagolf_field_updates", "meta",
        "recent_form", "all", len(player_list), source="datagolf"
    )

    metric_rows = []
    for p in player_list:
        if not isinstance(p, dict):
            continue
        raw_name = p.get("player_name", "")
        pkey = normalize_name(raw_name)
        pdisp = display_name(raw_name)
        if not pkey:
            continue

        meta_fields = {
            "draftkings": p.get("dk_salary") or p.get("draftkings_salary"),
            "fanduel": p.get("fd_salary") or p.get("fanduel_salary"),
            "teetime": None,  # stored as text
        }
        tee_time_text = p.get("tee_time") or p.get("teetime")

        for metric_name, value in meta_fields.items():
            if metric_name == "teetime" and tee_time_text:
                metric_rows.append({
                    "tournament_id": tournament_id,
                    "csv_import_id": import_id,
                    "player_key": pkey,
                    "player_display": pdisp,
                    "metric_category": "meta",
                    "data_mode": "recent_form",
                    "round_window": "all",
                    "metric_name": "teetime",
                    "metric_value": None,
                    "metric_text": str(tee_time_text),
                })
            else:
                fval = _safe_float(value)
                if fval is not None:
                    metric_rows.append({
                        "tournament_id": tournament_id,
                        "csv_import_id": import_id,
                        "player_key": pkey,
                        "player_display": pdisp,
                        "metric_category": "meta",
                        "data_mode": "recent_form",
                        "round_window": "all",
                        "metric_name": metric_name,
                        "metric_value": fval,
                        "metric_text": None,
                    })

        # Store dg_id as meta for cross-referencing
        dg_id_val = _safe_float(p.get("dg_id"))
        if dg_id_val is not None:
            metric_rows.append({
                "tournament_id": tournament_id,
                "csv_import_id": import_id,
                "player_key": pkey,
                "player_display": pdisp,
                "metric_category": "meta",
                "data_mode": "recent_form",
                "round_window": "all",
                "metric_name": "dg_id",
                "metric_value": dg_id_val,
                "metric_text": None,
            })

    db.store_metrics(metric_rows)
    return len(metric_rows)


# ═══════════════════════════════════════════════════════════════════
#  Orchestrators
# ═══════════════════════════════════════════════════════════════════

def sync_tournament(tournament_id: int, tour: str = "pga") -> dict:
    """
    Full tournament sync: fetch predictions, decompositions, and field updates
    from Data Golf and store in the metrics table.

    Also auto-updates round data for the current year so rolling stats
    include the most recently completed events.

    Call this before running the analysis pipeline.
    """
    from datetime import datetime as _dt

    summary = {
        "predictions": 0,
        "decompositions": 0,
        "field": 0,
        "rounds_updated": 0,
        "errors": [],
    }

    # 0. Auto-update rounds for current year (fast — skips existing data)
    try:
        current_year = _dt.now().year
        print(f"  Updating {tour.upper()} {current_year} round data...")
        raw = fetch_historical_rounds(tour=tour, event_id="all", year=current_year)
        rows = _parse_rounds_response(raw, tour, current_year)
        before = db.get_rounds_count()
        db.store_rounds(rows)
        after = db.get_rounds_count()
        new_rounds = after - before
        summary["rounds_updated"] = new_rounds
        if new_rounds > 0:
            print(f"    → {new_rounds} new rounds added")
        else:
            print(f"    → Already up to date")
    except Exception as e:
        summary["errors"].append(f"rounds_update: {e}")
        print(f"    → Round update error (non-fatal): {e}")

    # 1. Pre-tournament predictions
    try:
        print("  Fetching DG pre-tournament predictions...")
        preds = fetch_pre_tournament(tour)
        n = _store_predictions_as_metrics(preds, tournament_id)
        summary["predictions"] = n
        print(f"    → {n} prediction metrics stored")
    except Exception as e:
        summary["errors"].append(f"predictions: {e}")
        print(f"    → ERROR: {e}")

    # 2. Player decompositions
    try:
        print("  Fetching DG player decompositions...")
        decomps = fetch_decompositions(tour)
        n = _store_decompositions_as_metrics(decomps, tournament_id)
        summary["decompositions"] = n
        print(f"    → {n} decomposition metrics stored")
    except Exception as e:
        summary["errors"].append(f"decompositions: {e}")
        print(f"    → ERROR: {e}")

    # 3. Field updates
    try:
        print("  Fetching DG field updates...")
        field = fetch_field_updates(tour)
        n = _store_field_as_metrics(field, tournament_id)
        summary["field"] = n
        print(f"    → {n} field metrics stored")
    except Exception as e:
        summary["errors"].append(f"field: {e}")
        print(f"    → ERROR: {e}")

    total = summary["predictions"] + summary["decompositions"] + summary["field"]
    summary["total_metrics"] = total
    return summary


def auto_ingest_results(tournament_id: int, event_id: str,
                        year: int) -> dict:
    """
    Auto-ingest tournament results from DG round data already in the DB.

    Pulls finish positions (fin_text) from rounds table and stores in results table.
    Returns summary of ingestion.
    """
    event_results = db.get_event_results(event_id, year)
    if not event_results:
        return {"status": "no_data", "message": f"No rounds found for event {event_id}/{year}"}

    results_list = []
    for r in event_results:
        fin = r.get("fin_text", "")
        if not fin:
            continue

        # Parse finish position
        finish_pos = None
        made_cut = 1
        fin_upper = fin.strip().upper()

        if fin_upper in ("CUT", "MC"):
            made_cut = 0
        elif fin_upper in ("WD", "W/D", "DQ"):
            made_cut = 0
        else:
            try:
                finish_pos = int(fin_upper.replace("T", ""))
            except ValueError:
                pass

        results_list.append({
            "player_key": r["player_key"],
            "player_display": display_name(r.get("player_name", "")),
            "finish_position": finish_pos,
            "finish_text": fin,
            "made_cut": made_cut,
        })

    if results_list:
        db.store_results(tournament_id, results_list)

    return {
        "status": "ok",
        "results_stored": len(results_list),
        "players": len(event_results),
    }


# ═══════════════════════════════════════════════════════════════════
#  Player Skill Ratings, Rankings & Approach Skill
# ═══════════════════════════════════════════════════════════════════

def fetch_skill_ratings() -> list[dict]:
    """
    Fetch DG's true player skill estimates by SG category.

    Returns list of player dicts with:
      sg_total, sg_ott, sg_app, sg_arg, sg_putt, driving_dist, driving_acc
    These are strokes-gained PER ROUND estimates, properly adjusted
    for field strength across all tours. More accurate than simple
    rolling averages.
    """
    data = _call_api("preds/skill-ratings", {"display": "value"})
    return data.get("players", []) if isinstance(data, dict) else []


def fetch_dg_rankings() -> list[dict]:
    """
    Fetch top 500 DG rankings with global skill estimates + OWGR rank.

    Each player has: dg_skill_estimate, datagolf_rank, owgr_rank, primary_tour
    """
    data = _call_api("preds/get-dg-rankings")
    return data.get("rankings", []) if isinstance(data, dict) else []


def fetch_approach_skill(period: str = "l24") -> list[dict]:
    """
    Fetch detailed approach performance stats by yardage/lie bucket.

    period: 'l24' (last 24 months), 'l12', 'ytd'
    Returns per-player approach stats broken down by:
      50-100, 100-150, 150-200, 200+ yards from fairway and rough.
      Each bucket has: sg_per_shot, proximity, gir_rate, good_shot_rate, poor_shot_avoid_rate
    """
    data = _call_api("preds/approach-skill", {"period": period})
    return data.get("data", data.get("players", [])) if isinstance(data, dict) else []


def store_skill_ratings_as_metrics(tournament_id: int, field_player_keys: list[str]) -> int:
    """
    Fetch DG skill ratings and store as metrics for field players.

    These provide a high-confidence baseline skill signal that's
    better than rolling averages (adjusted for field strength across tours).
    """
    players = fetch_skill_ratings()
    if not players:
        return 0

    # Build lookup by player_key
    skill_by_key = {}
    for p in players:
        pkey = normalize_name(p.get("player_name", ""))
        if pkey:
            skill_by_key[pkey] = p

    import_id = db.log_csv_import(
        tournament_id, "dg_skill_ratings", "dg_skill",
        "recent_form", "all", len(players), source="datagolf"
    )

    metric_rows = []
    for pk in field_player_keys:
        p = skill_by_key.get(pk)
        if not p:
            continue
        pdisp = display_name(p.get("player_name", ""))

        fields = {
            "dg_sg_total": p.get("sg_total"),
            "dg_sg_ott": p.get("sg_ott"),
            "dg_sg_app": p.get("sg_app"),
            "dg_sg_arg": p.get("sg_arg"),
            "dg_sg_putt": p.get("sg_putt"),
            "dg_driving_dist": p.get("driving_dist"),
            "dg_driving_acc": p.get("driving_acc"),
        }
        for metric_name, value in fields.items():
            fval = _safe_float(value)
            if fval is not None:
                metric_rows.append({
                    "tournament_id": tournament_id,
                    "csv_import_id": import_id,
                    "player_key": pk,
                    "player_display": pdisp,
                    "metric_category": "dg_skill",
                    "data_mode": "recent_form",
                    "round_window": "all",
                    "metric_name": metric_name,
                    "metric_value": fval,
                    "metric_text": None,
                })

    db.store_metrics(metric_rows)
    return len(metric_rows)


def store_rankings_as_metrics(tournament_id: int, field_player_keys: list[str]) -> int:
    """Fetch DG rankings and store rank + skill estimate for field players."""
    rankings = fetch_dg_rankings()
    if not rankings:
        return 0

    rank_by_key = {}
    for r in rankings:
        pkey = normalize_name(r.get("player_name", ""))
        if pkey:
            rank_by_key[pkey] = r

    import_id = db.log_csv_import(
        tournament_id, "dg_rankings", "dg_ranking",
        "recent_form", "all", len(rankings), source="datagolf"
    )

    metric_rows = []
    for pk in field_player_keys:
        r = rank_by_key.get(pk)
        if not r:
            continue
        pdisp = display_name(r.get("player_name", ""))

        for metric_name, value in [
            ("dg_rank", r.get("datagolf_rank")),
            ("owgr_rank", r.get("owgr_rank")),
            ("dg_skill_estimate", r.get("dg_skill_estimate")),
        ]:
            fval = _safe_float(value)
            if fval is not None:
                metric_rows.append({
                    "tournament_id": tournament_id,
                    "csv_import_id": import_id,
                    "player_key": pk,
                    "player_display": pdisp,
                    "metric_category": "dg_ranking",
                    "data_mode": "recent_form",
                    "round_window": "all",
                    "metric_name": metric_name,
                    "metric_value": fval,
                    "metric_text": None,
                })

    db.store_metrics(metric_rows)
    return len(metric_rows)


def store_approach_skill_as_metrics(tournament_id: int, field_player_keys: list[str]) -> int:
    """
    Fetch detailed approach skill data and store for field players.

    Stores SG per shot and proximity for each yardage/lie bucket.
    Critical for course-fit analysis at approach-heavy courses.
    """
    players = fetch_approach_skill("l24")
    if not players:
        return 0

    app_by_key = {}
    for p in players:
        pkey = normalize_name(p.get("player_name", ""))
        if pkey:
            app_by_key[pkey] = p

    import_id = db.log_csv_import(
        tournament_id, "dg_approach_skill", "dg_approach",
        "recent_form", "all", len(players), source="datagolf"
    )

    # Key approach buckets to store
    buckets = ["50_100", "100_150", "150_200", "200_plus"]
    lies = ["fw", "rgh"]
    stats = ["sg_per_shot", "proximity_per_shot", "gir_rate"]

    metric_rows = []
    for pk in field_player_keys:
        p = app_by_key.get(pk)
        if not p:
            continue
        pdisp = display_name(p.get("player_name", pk))

        for bucket in buckets:
            for lie in lies:
                for stat in stats:
                    field_name = f"{bucket}_{lie}_{stat}"
                    fval = _safe_float(p.get(field_name))
                    if fval is not None:
                        metric_rows.append({
                            "tournament_id": tournament_id,
                            "csv_import_id": import_id,
                            "player_key": pk,
                            "player_display": pdisp,
                            "metric_category": "dg_approach",
                            "data_mode": "recent_form",
                            "round_window": "all",
                            "metric_name": field_name,
                            "metric_value": fval,
                            "metric_text": None,
                        })

        # Also store overall approach SG composite (average across buckets)
        sg_vals = []
        for bucket in buckets:
            for lie in lies:
                v = _safe_float(p.get(f"{bucket}_{lie}_sg_per_shot"))
                if v is not None:
                    sg_vals.append(v)
        if sg_vals:
            metric_rows.append({
                "tournament_id": tournament_id,
                "csv_import_id": import_id,
                "player_key": pk,
                "player_display": pdisp,
                "metric_category": "dg_approach",
                "data_mode": "recent_form",
                "round_window": "all",
                "metric_name": "approach_sg_composite",
                "metric_value": round(sum(sg_vals) / len(sg_vals), 4),
                "metric_text": None,
            })

    db.store_metrics(metric_rows)
    return len(metric_rows)


# ═══════════════════════════════════════════════════════════════════
#  Betting Tools — Live Odds from Sportsbooks
# ═══════════════════════════════════════════════════════════════════

# Sportsbook display names
BOOK_NAMES = {
    "draftkings": "DraftKings", "fanduel": "FanDuel", "betmgm": "BetMGM",
    "caesars": "Caesars", "bovada": "Bovada", "pinnacle": "Pinnacle",
    "bet365": "bet365", "betonline": "BetOnline", "betway": "Betway",
    "pointsbet": "PointsBet", "williamhill": "WilliamHill", "unibet": "Unibet",
    "skybet": "SkyBet", "betcris": "Betcris", "circa": "Circa",
}

# Keys in the response that are NOT sportsbooks
NON_BOOK_KEYS = {"player_name", "dg_id", "datagolf", "am"}


def _parse_american_odds(val) -> int | None:
    """Parse American odds from a string like '+4000' or '-150' or 'n/a'.

    Returns None for invalid or unreasonable values (e.g., +500000).
    """
    if val is None or val == "n/a" or val == "":
        return None
    try:
        price = int(str(val).replace("+", ""))
        # Reject clearly unreasonable odds (bad API data)
        # Real golf odds max out around +50000 for outrights
        if price > 50000 or price < -10000 or price == 0:
            return None
        return price
    except (ValueError, TypeError):
        return None


def fetch_outright_odds(market: str = "win", tour: str = "pga",
                        odds_format: str = "american") -> list[dict]:
    """
    Fetch live outright odds from Data Golf's betting tools.

    market: 'win', 'top_5', 'top_10', 'top_20', 'make_cut', 'frl'
    Returns list of {player, bookmaker, price, implied_prob, market}
    in the same format that odds.py uses.
    """
    from src.odds import american_to_implied_prob

    raw = _call_api("betting-tools/outrights", {
        "tour": tour,
        "market": market,
        "odds_format": odds_format,
    })

    odds_list = raw.get("odds", []) if isinstance(raw, dict) else []

    # Map DG market names to our internal bet_type names
    market_name_map = {
        "win": "outrights", "top_5": "top_5", "top_10": "top_10",
        "top_20": "top_20", "make_cut": "make_cut", "frl": "frl",
    }
    display_market = market_name_map.get(market, market)

    results = []
    for player in odds_list:
        if not isinstance(player, dict):
            continue
        player_name = player.get("player_name", "")
        if not player_name:
            continue

        # Extract odds from each sportsbook
        for book_key, book_display in BOOK_NAMES.items():
            odds_val = player.get(book_key)
            if odds_val is None or odds_val == "n/a" or odds_val == "":
                continue

            price = _parse_american_odds(odds_val)
            if price is None:
                continue

            impl_prob = american_to_implied_prob(price)
            results.append({
                "player": display_name(player_name),
                "bookmaker": book_display,
                "price": price,
                "implied_prob": round(impl_prob, 4),
                "market": display_market,
            })

        # Also extract DG's own model odds for reference
        dg_odds = player.get("datagolf", {})
        if isinstance(dg_odds, dict):
            for dg_key, dg_label in [("baseline_history_fit", "DG-CH"),
                                      ("baseline", "DG-Base")]:
                dg_price = _parse_american_odds(dg_odds.get(dg_key))
                if dg_price is not None:
                    results.append({
                        "player": display_name(player_name),
                        "bookmaker": dg_label,
                        "price": dg_price,
                        "implied_prob": round(american_to_implied_prob(dg_price), 4),
                        "market": display_market,
                    })

    return results


def fetch_matchup_odds(market: str = "tournament_matchups", tour: str = "pga",
                        odds_format: str = "american") -> list[dict]:
    """
    Fetch live matchup/3-ball odds from Data Golf's betting tools.

    market: 'tournament_matchups', 'round_matchups', '3_balls'
    Returns list of matchup dicts.
    """
    raw = _call_api("betting-tools/matchups", {
        "tour": tour,
        "market": market,
        "odds_format": odds_format,
    })

    if isinstance(raw, dict):
        match_list = raw.get("match_list", [])
        if isinstance(match_list, list):
            return match_list
    return []


def fetch_all_outright_odds(tour: str = "pga") -> dict:
    """
    Fetch odds for all outright markets and return organized by market.

    Returns: {market_name: [list of odds dicts]}
    """
    import time
    all_odds = {}

    for market in ["win", "top_5", "top_10", "top_20", "frl"]:
        time.sleep(1)  # Respect rate limits
        try:
            odds = fetch_outright_odds(market=market, tour=tour)
            if odds:
                # Map to internal market names
                market_name_map = {
                    "win": "outrights", "top_5": "top_5",
                    "top_10": "top_10", "top_20": "top_20",
                    "frl": "frl",
                }
                key = market_name_map.get(market, market)
                all_odds[key] = odds
        except Exception as e:
            print(f"    ⚠ {market} odds error: {e}")

    return all_odds


def get_current_event_info(tour: str = "pga") -> dict | None:
    """
    Get the current/upcoming event info from the schedule.

    Returns dict with event_id, event_name, course, etc. or None.
    """
    try:
        schedule = _call_api("get-schedule", {
            "tour": tour,
            "upcoming_only": "yes",
        })
        if isinstance(schedule, list) and schedule:
            return schedule[0]
        elif isinstance(schedule, dict):
            events = schedule.get("schedule", [])
            if events:
                return events[0]
    except Exception:
        pass
    return None


def fetch_closing_odds(tour: str = "pga") -> dict:
    """
    Fetch closing odds from Data Golf for CLV tracking.

    Uses /betting-tools/outrights with market=closing (if available).
    Falls back to latest pre-tournament odds if closing not available.

    Returns: {player_dg_id: {market: closing_decimal_odds}} or empty dict.
    """
    results = {}
    for market in ["win", "top_5", "top_10", "top_20"]:
        try:
            raw = _call_api("betting-tools/outrights", {
                "tour": tour,
                "market": market,
                "odds_format": "decimal",
            })
            if not raw:
                continue
            odds_list = raw if isinstance(raw, list) else raw.get("odds", [])
            for entry in odds_list:
                player_name = entry.get("player_name", "")
                dg_id = entry.get("dg_id")
                book_odds = []
                for key, val in entry.items():
                    if key not in ("player_name", "dg_id", "country", "course_name") and isinstance(val, (int, float)) and val > 1.0:
                        book_odds.append(val)
                if book_odds:
                    avg_odds = sum(book_odds) / len(book_odds)
                    pk = player_name
                    if pk not in results:
                        results[pk] = {}
                    market_map = {"win": "outright", "top_5": "top5", "top_10": "top10", "top_20": "top20"}
                    results[pk][market_map.get(market, market)] = round(avg_odds, 2)
        except Exception:
            continue
    return results
