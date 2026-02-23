"""
Historical Data Backfill Module

Pulls historical data from DataGolf, Open-Meteo, and stores it for backtesting.
Tracks progress in the backfill_progress table so interrupted runs resume safely.

DataGolf endpoints used (Scratch Plus tier):
  - historical-raw-data/rounds  (round-level SG stats, already in datagolf.py)
  - preds/pre-tournament-archive (historical pre-tournament predictions)
  - betting-tools/outrights-archive (historical odds snapshots)
  - get-schedule (historical event info with coordinates)

Open-Meteo endpoint:
  - archive-api.open-meteo.com/v1/archive (free hourly historical weather)
"""

import logging
import time
from datetime import datetime, timedelta

from src import db
from src.datagolf import _call_api, _safe_float, _parse_rounds_response
from src.datagolf import fetch_historical_rounds
from src.player_normalizer import normalize_name

logger = logging.getLogger("backfill")


# ═══════════════════════════════════════════════════════════════════
#  Progress Tracking
# ═══════════════════════════════════════════════════════════════════

def _is_done(table_name: str, event_id: str, year: int) -> bool:
    """Check if a (table, event, year) has already been backfilled."""
    conn = db.get_conn()
    row = conn.execute(
        "SELECT 1 FROM backfill_progress WHERE table_name=? AND event_id=? AND year=? AND status='done'",
        (table_name, str(event_id), year),
    ).fetchone()
    return row is not None


def _mark_done(table_name: str, event_id: str, year: int):
    conn = db.get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO backfill_progress(table_name, event_id, year, status) VALUES(?,?,?,?)",
        (table_name, str(event_id), year, "done"),
    )
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
#  DG Schedule / Event Listing
# ═══════════════════════════════════════════════════════════════════

def fetch_schedule(tour: str = "pga", season: int = None) -> list[dict]:
    """Fetch full season schedule from DataGolf.

    Falls back to deriving event list from the rounds table when the
    get-schedule endpoint fails (it only supports recent seasons).
    """
    params = {"tour": tour}
    if season:
        params["season"] = str(season)
    try:
        data = _call_api("get-schedule", params)
        if isinstance(data, dict):
            events = data.get("schedule", data.get("events", []))
        elif isinstance(data, list):
            events = data
        else:
            events = []
        if events:
            return events
    except Exception:
        pass

    # Fallback: derive event list from rounds we already have in the DB
    if season:
        return _events_from_rounds(tour, season)
    return []


def _events_from_rounds(tour: str, year: int) -> list[dict]:
    """Build a minimal event list from the rounds table for a given year.

    This allows backfilling predictions/weather for older seasons
    where get-schedule returns a 400 error. Uses event_completed
    dates from rounds to estimate tournament windows for weather.
    """
    conn = db.get_conn()
    rows = conn.execute("""
        SELECT DISTINCT event_id, event_name, course_num, course_name,
               event_completed
        FROM rounds
        WHERE year = ? AND tour = ?
        ORDER BY event_completed
    """, (year, tour)).fetchall()
    conn.close()

    events = []
    for r in rows:
        end_date = r[4] or ""
        start_date = ""
        if end_date:
            try:
                ed = datetime.strptime(end_date, "%Y-%m-%d")
                sd = ed - timedelta(days=3)
                start_date = sd.strftime("%Y-%m-%d")
            except ValueError:
                pass

        events.append({
            "event_id": r[0],
            "event_name": r[1],
            "course_key": str(r[2]) if r[2] else "",
            "course": r[3] or "",
            "event_completed": end_date or True,
            "start_date": start_date,
            "end_date": end_date,
            "tour": tour,
        })

    if events:
        logger.info("Derived %d events from rounds for %s %d", len(events), tour, year)
    return events


def _store_event_info(events: list[dict], year: int):
    """Store event metadata in historical_event_info."""
    conn = db.get_conn()
    for ev in events:
        if not isinstance(ev, dict):
            continue
        event_id = str(ev.get("event_id", ev.get("id", "")))
        if not event_id:
            continue
        conn.execute("""
            INSERT OR REPLACE INTO historical_event_info
            (event_id, year, event_name, course_id, course_name, tour,
             start_date, end_date, latitude, longitude)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            event_id, year,
            ev.get("event_name", ev.get("name", "")),
            str(ev.get("course_key", ev.get("course_id", ""))),
            ev.get("course", ev.get("course_name", "")),
            ev.get("tour", "pga"),
            ev.get("start_date", ev.get("date", "")),
            ev.get("end_date", ""),
            _safe_float(ev.get("latitude")),
            _safe_float(ev.get("longitude")),
        ))
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
#  Historical Predictions Backfill
# ═══════════════════════════════════════════════════════════════════

def _decimal_odds_to_prob(decimal_odds) -> float | None:
    """Convert decimal odds (e.g. 7.33) to implied probability (e.g. 0.1365).

    Returns None if input is invalid or not positive.
    """
    try:
        val = float(decimal_odds)
        if val <= 0:
            return None
        return 1.0 / val
    except (TypeError, ValueError):
        return None


def backfill_predictions(event_id: str, year: int, tour: str = "pga") -> int:
    """
    Fetch archived pre-tournament predictions for a completed event.

    Uses preds/pre-tournament-archive which returns actual historical data
    with decimal odds (not probabilities). We convert to probabilities.

    Returns count of rows stored.
    """
    table = "historical_predictions"
    if _is_done(table, event_id, year):
        return 0

    try:
        data = _call_api("preds/pre-tournament-archive", {
            "tour": tour,
            "event_id": str(event_id),
            "year": str(year),
        })
    except Exception as e:
        logger.warning("Predictions backfill failed for %s/%s: %s", event_id, year, e)
        return 0

    if not isinstance(data, dict):
        return 0

    # Store both model types: baseline_history_fit (preferred) and baseline
    conn = db.get_conn()
    count = 0

    for model_type in ["baseline_history_fit", "baseline"]:
        players = data.get(model_type, [])
        if not players:
            continue

        for p in players:
            if not isinstance(p, dict):
                continue
            dg_id = p.get("dg_id")
            if not dg_id:
                continue

            # Archive returns decimal odds — convert to probabilities
            win_prob = _decimal_odds_to_prob(p.get("win"))
            top5_prob = _decimal_odds_to_prob(p.get("top_5"))
            top10_prob = _decimal_odds_to_prob(p.get("top_10"))
            top20_prob = _decimal_odds_to_prob(p.get("top_20"))
            make_cut_prob = _decimal_odds_to_prob(p.get("make_cut"))

            try:
                conn.execute("""
                    INSERT OR REPLACE INTO historical_predictions
                    (event_id, year, player_dg_id, player_name, win_prob, top5_prob,
                     top10_prob, top20_prob, make_cut_prob, model_type,
                     actual_finish)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    str(event_id), year, dg_id,
                    p.get("player_name", ""),
                    round(win_prob, 6) if win_prob else None,
                    round(top5_prob, 6) if top5_prob else None,
                    round(top10_prob, 6) if top10_prob else None,
                    round(top20_prob, 6) if top20_prob else None,
                    round(make_cut_prob, 6) if make_cut_prob else None,
                    model_type,
                    p.get("fin_text"),
                ))
                count += 1
            except Exception:
                pass

    conn.commit()

    if count > 0:
        _mark_done(table, event_id, year)
    return count


# ═══════════════════════════════════════════════════════════════════
#  Historical Odds Backfill
# ═══════════════════════════════════════════════════════════════════

def backfill_odds(event_id: str, year: int, tour: str = "pga") -> int:
    """
    Store DG model odds from the predictions archive for a completed event.

    DataGolf does NOT have a historical sportsbook odds archive endpoint.
    Instead, we extract DG's own model decimal odds from the pre-tournament
    archive and store them as synthetic odds. This gives us:
      - A baseline to estimate CLV and market edge
      - Calibrated probabilities for backtesting

    Returns count of rows stored.
    """
    table = "historical_odds"
    if _is_done(table, event_id, year):
        return 0

    try:
        data = _call_api("preds/pre-tournament-archive", {
            "tour": tour,
            "event_id": str(event_id),
            "year": str(year),
        })
    except Exception as e:
        logger.warning("Odds backfill (via predictions archive) %s/%s: %s", event_id, year, e)
        return 0

    if not isinstance(data, dict):
        return 0

    # Market mapping: DG field name → our market name
    market_fields = {
        "win": "win",
        "top_5": "top_5",
        "top_10": "top_10",
        "top_20": "top_20",
        "make_cut": "make_cut",
    }

    conn = db.get_conn()
    total = 0

    for model_type in ["baseline_history_fit", "baseline"]:
        players = data.get(model_type, [])
        book_label = "DG-CH" if model_type == "baseline_history_fit" else "DG-Base"

        for p in players:
            if not isinstance(p, dict):
                continue
            dg_id = p.get("dg_id")
            name = p.get("player_name", "")
            if not dg_id:
                continue

            for dg_field, market_name in market_fields.items():
                decimal_odds = p.get(dg_field)
                if decimal_odds is None:
                    continue
                try:
                    decimal_odds = float(decimal_odds)
                    if decimal_odds <= 1.0:
                        continue
                    # Convert decimal odds to American for storage consistency
                    american = int((decimal_odds - 1.0) * 100)
                except (TypeError, ValueError):
                    continue

                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO historical_odds
                        (event_id, year, player_dg_id, player_name, market, book,
                         close_line, outcome)
                        VALUES (?,?,?,?,?,?,?,?)
                    """, (
                        str(event_id), year, dg_id, name,
                        market_name, book_label, american, None,
                    ))
                    total += 1
                except Exception:
                    pass

    conn.commit()

    if total > 0:
        _mark_done(table, event_id, year)
    return total


# ═══════════════════════════════════════════════════════════════════
#  Historical Rounds Backfill (delegates to datagolf.py)
# ═══════════════════════════════════════════════════════════════════

def backfill_rounds(tour: str = "pga", year: int = 2025) -> dict:
    """
    Wrapper for full-season round backfill. Uses existing datagolf.py logic.
    """
    table = "rounds"
    if _is_done(table, "all", year):
        return {"status": "skipped", "reason": "already_done"}

    try:
        raw = fetch_historical_rounds(tour=tour, event_id="all", year=year)
        rows = _parse_rounds_response(raw, tour, year)
        before = db.get_rounds_count()
        db.store_rounds(rows)
        after = db.get_rounds_count()
        _mark_done(table, "all", year)
        return {
            "status": "ok",
            "rounds_fetched": len(rows),
            "rounds_new": after - before,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ═══════════════════════════════════════════════════════════════════
#  Weather Backfill (Open-Meteo — free, no key needed)
# ═══════════════════════════════════════════════════════════════════

def backfill_weather(event_id: str, year: int,
                     latitude: float, longitude: float,
                     start_date: str, end_date: str) -> int:
    """
    Fetch hourly historical weather from Open-Meteo and store.

    start_date, end_date: YYYY-MM-DD strings for the tournament window.
    Returns count of hourly rows stored.
    """
    import requests

    table = "tournament_weather"
    if _is_done(table, event_id, year):
        return 0

    if not latitude or not longitude or not start_date:
        return 0

    # Extend window by 1 day on each side for practice rounds / travel
    try:
        sd = datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=1)
        if end_date:
            ed = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        else:
            ed = sd + timedelta(days=5)
    except ValueError:
        return 0

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": sd.strftime("%Y-%m-%d"),
        "end_date": ed.strftime("%Y-%m-%d"),
        "hourly": ",".join([
            "temperature_2m", "wind_speed_10m", "wind_gusts_10m",
            "wind_direction_10m", "precipitation", "relative_humidity_2m",
            "cloud_cover", "surface_pressure",
        ]),
        "timezone": "auto",
    }

    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("Weather fetch failed for %s/%s: %s", event_id, year, e)
        return 0

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    if not times:
        return 0

    conn = db.get_conn()
    count = 0
    for i, ts in enumerate(times):
        # ts format: "2024-01-18T06:00"
        try:
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M")
        except ValueError:
            continue
        try:
            conn.execute("""
                INSERT OR REPLACE INTO tournament_weather
                (event_id, year, date, hour,
                 temperature_c, wind_speed_kmh, wind_gusts_kmh,
                 wind_direction, precipitation_mm,
                 humidity_pct, cloud_cover_pct, pressure_hpa)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                str(event_id), year,
                dt.strftime("%Y-%m-%d"), dt.hour,
                _get_idx(hourly, "temperature_2m", i),
                _get_idx(hourly, "wind_speed_10m", i),
                _get_idx(hourly, "wind_gusts_10m", i),
                _get_idx(hourly, "wind_direction_10m", i),
                _get_idx(hourly, "precipitation", i),
                _get_idx(hourly, "relative_humidity_2m", i),
                _get_idx(hourly, "cloud_cover", i),
                _get_idx(hourly, "surface_pressure", i),
            ))
            count += 1
        except Exception:
            pass
    conn.commit()

    if count > 0:
        _mark_done(table, event_id, year)
        _compute_weather_summary(event_id, year)
    return count


def _get_idx(hourly: dict, key: str, i: int):
    """Safely get index i from hourly data list."""
    vals = hourly.get(key, [])
    if i < len(vals):
        return vals[i]
    return None


def _compute_weather_summary(event_id: str, year: int):
    """
    Compute per-round weather summaries from hourly data.

    Assumes tournament rounds on Thursday-Sunday (offset from start_date).
    Calculates AM/PM wave splits for wind advantage detection.
    """
    conn = db.get_conn()
    rows = conn.execute("""
        SELECT date, hour, wind_speed_kmh, wind_gusts_kmh,
               precipitation_mm, temperature_c
        FROM tournament_weather
        WHERE event_id=? AND year=?
        ORDER BY date, hour
    """, (str(event_id), year)).fetchall()

    if not rows:
        return

    # Group by date
    by_date = {}
    for r in rows:
        d = r[0]
        if d not in by_date:
            by_date[d] = []
        by_date[d].append(r)

    dates = sorted(by_date.keys())
    # Skip first date (practice day buffer)
    round_dates = dates[1:5] if len(dates) > 4 else dates[:4]

    for round_num, date in enumerate(round_dates, 1):
        day_rows = by_date.get(date, [])
        if not day_rows:
            continue

        winds = [r[2] for r in day_rows if r[2] is not None]
        gusts = [r[3] for r in day_rows if r[3] is not None]
        precips = [r[4] for r in day_rows if r[4] is not None]
        temps = [r[5] for r in day_rows if r[5] is not None]

        # AM wave (6-11), PM wave (12-17) for tee time advantage
        am_winds = [r[2] for r in day_rows if r[1] in range(6, 12) and r[2] is not None]
        pm_winds = [r[2] for r in day_rows if r[1] in range(12, 18) and r[2] is not None]

        avg_wind = sum(winds) / len(winds) if winds else None
        max_gust = max(gusts) if gusts else None
        total_precip = sum(precips) if precips else None
        avg_temp = sum(temps) / len(temps) if temps else None
        am_wave_wind = sum(am_winds) / len(am_winds) if am_winds else None
        pm_wave_wind = sum(pm_winds) / len(pm_winds) if pm_winds else None

        # Simple conditions rating: 0 = perfect, 100 = brutal
        rating = 0.0
        if avg_wind and avg_wind > 15:
            rating += min(40, (avg_wind - 15) * 3)
        if max_gust and max_gust > 40:
            rating += min(20, (max_gust - 40) * 2)
        if total_precip and total_precip > 0:
            rating += min(30, total_precip * 10)
        if avg_temp and avg_temp < 10:
            rating += min(10, (10 - avg_temp) * 2)

        try:
            conn.execute("""
                INSERT OR REPLACE INTO tournament_weather_summary
                (event_id, year, round_num, avg_wind_kmh, max_gust_kmh,
                 total_precip_mm, avg_temp_c, am_wave_wind, pm_wave_wind,
                 conditions_rating)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                str(event_id), year, round_num,
                round(avg_wind, 1) if avg_wind else None,
                round(max_gust, 1) if max_gust else None,
                round(total_precip, 1) if total_precip else None,
                round(avg_temp, 1) if avg_temp else None,
                round(am_wave_wind, 1) if am_wave_wind else None,
                round(pm_wave_wind, 1) if pm_wave_wind else None,
                round(rating, 1),
            ))
        except Exception:
            pass
    conn.commit()


# ═══════════════════════════════════════════════════════════════════
#  Course Encyclopedia
# ═══════════════════════════════════════════════════════════════════

def upsert_course(course_id: str, course_name: str,
                  latitude: float = None, longitude: float = None,
                  **kwargs) -> None:
    """
    Insert or update a course in the encyclopedia.

    kwargs can include: grass_type_fairway, grass_type_greens, green_speed,
    fairway_width, yardage, par, prevailing_wind, course_type,
    sg_ott_importance, sg_app_importance, sg_arg_importance, sg_putt_importance,
    historical_scoring_avg, ai_course_profile, elevation_m
    """
    conn = db.get_conn()

    existing = conn.execute(
        "SELECT id FROM course_encyclopedia WHERE course_id = ?",
        (course_id,)
    ).fetchone()

    if existing:
        sets = []
        vals = []
        for key, val in kwargs.items():
            if val is not None:
                sets.append(f"{key} = ?")
                vals.append(val)
        if latitude is not None:
            sets.append("latitude = ?")
            vals.append(latitude)
        if longitude is not None:
            sets.append("longitude = ?")
            vals.append(longitude)
        if course_name:
            sets.append("course_name = ?")
            vals.append(course_name)
        sets.append("updated_at = datetime('now')")
        if sets:
            vals.append(course_id)
            conn.execute(
                f"UPDATE course_encyclopedia SET {', '.join(sets)} WHERE course_id = ?",
                vals,
            )
    else:
        conn.execute("""
            INSERT INTO course_encyclopedia
            (course_id, course_name, latitude, longitude,
             elevation_m, grass_type_fairway, grass_type_greens,
             green_speed, fairway_width, yardage, par,
             prevailing_wind, course_type,
             sg_ott_importance, sg_app_importance,
             sg_arg_importance, sg_putt_importance,
             historical_scoring_avg, ai_course_profile)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            course_id, course_name, latitude, longitude,
            kwargs.get("elevation_m"),
            kwargs.get("grass_type_fairway"),
            kwargs.get("grass_type_greens"),
            kwargs.get("green_speed"),
            kwargs.get("fairway_width"),
            kwargs.get("yardage"),
            kwargs.get("par"),
            kwargs.get("prevailing_wind"),
            kwargs.get("course_type"),
            kwargs.get("sg_ott_importance"),
            kwargs.get("sg_app_importance"),
            kwargs.get("sg_arg_importance"),
            kwargs.get("sg_putt_importance"),
            kwargs.get("historical_scoring_avg"),
            kwargs.get("ai_course_profile"),
        ))
    conn.commit()


def build_courses_from_events():
    """
    Build course encyclopedia entries from historical_event_info table.
    Populates stub entries that can be enriched later by AI or manual input.
    """
    conn = db.get_conn()
    events = conn.execute("""
        SELECT DISTINCT course_id, course_name, latitude, longitude
        FROM historical_event_info
        WHERE course_id IS NOT NULL AND course_id != ''
    """).fetchall()

    for ev in events:
        cid, cname, lat, lon = ev
        if cid:
            upsert_course(cid, cname, latitude=lat, longitude=lon)
    logger.info("Built %d course stubs from event history", len(events))


def _load_course_coords() -> dict:
    """Load course coordinates from the encyclopedia for weather fallback.

    Returns {course_id: (latitude, longitude)}.
    """
    try:
        conn = db.get_conn()
        rows = conn.execute("""
            SELECT course_id, latitude, longitude
            FROM course_encyclopedia
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """).fetchall()
        conn.close()
        return {str(r[0]): (r[1], r[2]) for r in rows}
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════════
#  Full Backfill Orchestrator
# ═══════════════════════════════════════════════════════════════════

def run_full_backfill(tours: list[str] = None,
                      years: list[int] = None,
                      include_weather: bool = True,
                      include_odds: bool = True,
                      include_predictions: bool = True) -> dict:
    """
    Run a full historical data backfill.

    Fetches schedule for each tour/year, then backfills:
      - Round-level SG data
      - Pre-tournament predictions
      - Historical odds snapshots
      - Hourly weather data
      - Course encyclopedia stubs

    Progress is tracked so interrupted runs resume where they left off.
    Respects API rate limits with 1-second pauses between calls.

    Returns summary dict with counts.
    """
    if tours is None:
        tours = ["pga"]
    if years is None:
        years = [2024, 2025, 2026]

    summary = {
        "rounds": {},
        "events_processed": 0,
        "predictions_stored": 0,
        "odds_stored": 0,
        "weather_hours": 0,
        "errors": [],
    }

    for tour in tours:
        for year in years:
            logger.info("Backfilling %s %d...", tour.upper(), year)
            print(f"\n{'='*60}")
            print(f"  Backfilling {tour.upper()} {year}")
            print(f"{'='*60}")

            # 1. Rounds (full season pull)
            print("  [1/4] Fetching round data...")
            rd = backfill_rounds(tour=tour, year=year)
            summary["rounds"][f"{tour}_{year}"] = rd
            time.sleep(1)

            # 2. Schedule + event info
            print("  [2/4] Fetching schedule & event info...")
            events = fetch_schedule(tour=tour, season=year)
            if events:
                _store_event_info(events, year)
                print(f"    → {len(events)} events found")
            else:
                print("    → No events found")
            time.sleep(1)

            # 3. Per-event: predictions, odds, weather
            completed = [
                e for e in events
                if isinstance(e, dict) and e.get("event_completed")
            ]
            if not completed:
                completed = events

            # Load course coordinates for weather lookup (fallback for
            # events derived from rounds that lack lat/lon)
            course_coords = _load_course_coords()

            for i, ev in enumerate(completed):
                if not isinstance(ev, dict):
                    continue
                eid = str(ev.get("event_id", ev.get("id", "")))
                ename = ev.get("event_name", ev.get("name", ""))
                if not eid:
                    continue

                print(f"  [{i+1}/{len(completed)}] {ename} (event {eid})...")

                if include_predictions:
                    n = backfill_predictions(eid, year, tour)
                    summary["predictions_stored"] += n
                    if n > 0:
                        print(f"    - {n} prediction rows")
                    time.sleep(1)

                if include_odds:
                    n = backfill_odds(eid, year, tour)
                    summary["odds_stored"] += n
                    if n > 0:
                        print(f"    - {n} odds rows")
                    time.sleep(1)

                if include_weather:
                    lat = _safe_float(ev.get("latitude"))
                    lon = _safe_float(ev.get("longitude"))
                    sd = ev.get("start_date", ev.get("date", ""))
                    ed = ev.get("end_date", "")

                    # Try course encyclopedia if event has no coordinates
                    if (not lat or not lon) and ev.get("course_key"):
                        ckey = str(ev["course_key"])
                        if ckey in course_coords:
                            lat, lon = course_coords[ckey]

                    if lat and lon and sd:
                        n = backfill_weather(eid, year, lat, lon, sd, ed)
                        summary["weather_hours"] += n
                        if n > 0:
                            print(f"    - {n} weather hours")
                    time.sleep(0.3)

                summary["events_processed"] += 1

    # 4. Build course encyclopedia from collected event info
    print("\n  Building course encyclopedia...")
    build_courses_from_events()

    print(f"\n{'='*60}")
    print(f"  Backfill Complete")
    print(f"  Events: {summary['events_processed']}")
    print(f"  Predictions: {summary['predictions_stored']}")
    print(f"  Odds: {summary['odds_stored']}")
    print(f"  Weather hours: {summary['weather_hours']}")
    if summary["errors"]:
        print(f"  Errors: {len(summary['errors'])}")
    print(f"{'='*60}")

    return summary
