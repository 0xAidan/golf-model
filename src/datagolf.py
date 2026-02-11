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
    resp = requests.get(url, params=params, timeout=120)
    resp.raise_for_status()
    return resp.json()


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

    # raw_data can be a dict with top-level keys or a list of events
    # depending on whether event_id='all' or specific
    if isinstance(raw_data, dict):
        # Single event or wrapper
        if "scores" in raw_data:
            events = [raw_data]
        elif "event_completed" in raw_data:
            events = [raw_data]
        else:
            # Might be wrapped differently
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
    # Handle response format: may be a dict with nested structure
    if isinstance(predictions, dict):
        player_list = predictions.get("baseline_history_fit", [])
        if not player_list:
            player_list = predictions.get("baseline", [])
        if not player_list:
            # Try as flat list
            player_list = [predictions]
    elif isinstance(predictions, list):
        player_list = predictions
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
            if value is not None:
                metric_rows.append({
                    "tournament_id": tournament_id,
                    "csv_import_id": import_id,
                    "player_key": pkey,
                    "player_display": pdisp,
                    "metric_category": "sim",
                    "data_mode": "recent_form",
                    "round_window": "all",
                    "metric_name": metric_name,
                    "metric_value": float(value),
                    "metric_text": None,
                })

        # Store dg_id as meta
        if p.get("dg_id"):
            metric_rows.append({
                "tournament_id": tournament_id,
                "csv_import_id": import_id,
                "player_key": pkey,
                "player_display": pdisp,
                "metric_category": "meta",
                "data_mode": "recent_form",
                "round_window": "all",
                "metric_name": "dg_id",
                "metric_value": float(p["dg_id"]),
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
        player_list = decompositions if "player_name" in decompositions else []
        if not player_list:
            # Try common wrapper keys
            for key in ["data", "players", "decompositions"]:
                if key in decompositions:
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

        # DG decomposition fields (varies by response format)
        sg_fields = {
            "dg_sg_total": p.get("sg_total") or p.get("total"),
            "dg_sg_ott": p.get("sg_ott") or p.get("off_the_tee"),
            "dg_sg_app": p.get("sg_app") or p.get("approach"),
            "dg_sg_arg": p.get("sg_arg") or p.get("around_the_green"),
            "dg_sg_putt": p.get("sg_putt") or p.get("putting"),
            "dg_sg_t2g": p.get("sg_t2g") or p.get("tee_to_green"),
        }

        for metric_name, value in sg_fields.items():
            if value is not None:
                metric_rows.append({
                    "tournament_id": tournament_id,
                    "csv_import_id": import_id,
                    "player_key": pkey,
                    "player_display": pdisp,
                    "metric_category": "dg_decomposition",
                    "data_mode": "course_specific",
                    "round_window": "all",
                    "metric_name": metric_name,
                    "metric_value": float(value),
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
    if isinstance(field_data, dict):
        player_list = field_data.get("field", [])
        if not player_list:
            player_list = [field_data] if "player_name" in field_data else []
    elif isinstance(field_data, list):
        player_list = field_data
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
            elif value is not None:
                metric_rows.append({
                    "tournament_id": tournament_id,
                    "csv_import_id": import_id,
                    "player_key": pkey,
                    "player_display": pdisp,
                    "metric_category": "meta",
                    "data_mode": "recent_form",
                    "round_window": "all",
                    "metric_name": metric_name,
                    "metric_value": float(value),
                    "metric_text": None,
                })

        # Store dg_id as meta for cross-referencing
        if p.get("dg_id"):
            metric_rows.append({
                "tournament_id": tournament_id,
                "csv_import_id": import_id,
                "player_key": pkey,
                "player_display": pdisp,
                "metric_category": "meta",
                "data_mode": "recent_form",
                "round_window": "all",
                "metric_name": "dg_id",
                "metric_value": float(p["dg_id"]),
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

    Call this before running the analysis pipeline.
    """
    summary = {
        "predictions": 0,
        "decompositions": 0,
        "field": 0,
        "errors": [],
    }

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
