"""
Weather Adjustment Module

Fetches weather forecasts and computes per-player adjustments based on:
1. Forecasted conditions severity (wind, rain, cold)
2. AM/PM tee time wave advantage
3. Player historical performance in adverse weather

This module only activates when conditions are meaningful (wind >15 km/h,
rain >2mm, or temp <10C). In calm conditions, adjustments are zero.

Data sources:
  - Open-Meteo Forecast API (free, no key required)
  - tournament_weather + rounds tables (historical performance)
  - Tee times from metrics table
"""

import logging
import requests
from typing import Optional

from src import db

logger = logging.getLogger("weather")

# Thresholds for "meaningful" weather
WIND_THRESHOLD_KMH = 15.0
RAIN_THRESHOLD_MM = 2.0
COLD_THRESHOLD_C = 10.0

# Maximum adjustment magnitude (points on 0-100 composite scale)
MAX_WAVE_ADJUSTMENT = 3.0
MAX_RESILIENCE_ADJUSTMENT = 5.0


def fetch_forecast(latitude: float, longitude: float,
                   start_date: str, days: int = 5) -> dict | None:
    """
    Fetch weather forecast from Open-Meteo for a tournament location.

    Returns dict with per-day summaries:
    {
        "days": [
            {"date": "2026-02-19", "avg_wind_kmh": 22.0, "max_gust_kmh": 45.0,
             "total_precip_mm": 3.0, "avg_temp_c": 12.0,
             "am_wind_kmh": 18.0, "pm_wind_kmh": 28.0, "conditions_rating": 35.0},
            ...
        ],
        "tournament_severity": 25.0,  # average conditions_rating across round days
    }
    """
    from datetime import datetime as _dt, timedelta as _td

    url = "https://api.open-meteo.com/v1/forecast"

    # Open-Meteo's forecast API uses start_date/end_date OR forecast_days,
    # but not both together. When start_date is provided, compute end_date
    # and omit forecast_days to avoid a 400 error.
    hourly_params = ",".join([
        "temperature_2m", "wind_speed_10m", "wind_gusts_10m",
        "precipitation", "relative_humidity_2m",
    ])

    try:
        start_dt = _dt.strptime(start_date, "%Y-%m-%d")
        end_dt = start_dt + _td(days=days - 1)
        today = _dt.now().date()
        days_ahead = (start_dt.date() - today).days

        if days_ahead > 16:
            logger.warning(
                "Start date %s is %d days ahead (max 16). Cannot fetch forecast.",
                start_date, days_ahead,
            )
            return None

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": hourly_params,
            "start_date": start_date,
            "end_date": end_dt.strftime("%Y-%m-%d"),
            "timezone": "auto",
        }
    except ValueError:
        # Invalid date format, fall back to forecast_days from today
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": hourly_params,
            "forecast_days": min(days, 16),
            "timezone": "auto",
        }

    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("Weather forecast fetch failed: %s", e)
        return None

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    if not times:
        return None

    # Group by date
    by_date = {}
    for i, ts in enumerate(times):
        date = ts[:10]
        if date not in by_date:
            by_date[date] = {"winds": [], "gusts": [], "precips": [], "temps": [],
                             "am_winds": [], "pm_winds": []}
        hour = int(ts[11:13]) if len(ts) >= 13 else 0
        wind = _safe_idx(hourly, "wind_speed_10m", i)
        gust = _safe_idx(hourly, "wind_gusts_10m", i)
        precip = _safe_idx(hourly, "precipitation", i)
        temp = _safe_idx(hourly, "temperature_2m", i)

        if wind is not None:
            by_date[date]["winds"].append(wind)
            if 6 <= hour < 12:
                by_date[date]["am_winds"].append(wind)
            elif 12 <= hour < 18:
                by_date[date]["pm_winds"].append(wind)
        if gust is not None:
            by_date[date]["gusts"].append(gust)
        if precip is not None:
            by_date[date]["precips"].append(precip)
        if temp is not None:
            by_date[date]["temps"].append(temp)

    day_summaries = []
    for date in sorted(by_date.keys()):
        d = by_date[date]
        avg_wind = _avg(d["winds"])
        max_gust = max(d["gusts"]) if d["gusts"] else None
        total_precip = sum(d["precips"]) if d["precips"] else None
        avg_temp = _avg(d["temps"])
        am_wind = _avg(d["am_winds"])
        pm_wind = _avg(d["pm_winds"])

        rating = _conditions_rating(avg_wind, max_gust, total_precip, avg_temp)

        day_summaries.append({
            "date": date,
            "avg_wind_kmh": round(avg_wind, 1) if avg_wind else None,
            "max_gust_kmh": round(max_gust, 1) if max_gust else None,
            "total_precip_mm": round(total_precip, 1) if total_precip is not None else None,
            "avg_temp_c": round(avg_temp, 1) if avg_temp else None,
            "am_wind_kmh": round(am_wind, 1) if am_wind else None,
            "pm_wind_kmh": round(pm_wind, 1) if pm_wind else None,
            "conditions_rating": round(rating, 1),
        })

    # Tournament severity = average of round days (skip day 0 practice)
    round_days = day_summaries[1:5] if len(day_summaries) > 4 else day_summaries[:4]
    ratings = [d["conditions_rating"] for d in round_days if d["conditions_rating"] is not None]
    severity = sum(ratings) / len(ratings) if ratings else 0.0

    return {
        "days": day_summaries,
        "tournament_severity": round(severity, 1),
    }


def compute_wave_advantage(forecast: dict) -> dict:
    """
    Compute AM vs PM wave wind advantage for each round day.

    Returns dict with round-level wave data:
    {1: {"am_wind": 18.0, "pm_wind": 28.0, "advantage": "AM", "diff_kmh": 10.0}, ...}
    """
    if not forecast or not forecast.get("days"):
        return {}

    days = forecast["days"]
    round_days = days[1:5] if len(days) > 4 else days[:4]

    wave_data = {}
    for round_num, day in enumerate(round_days, 1):
        am = day.get("am_wind_kmh")
        pm = day.get("pm_wind_kmh")
        if am is None or pm is None:
            continue

        diff = abs(am - pm)
        if diff < 3.0:
            advantage = "neutral"
        elif am < pm:
            advantage = "AM"
        else:
            advantage = "PM"

        wave_data[round_num] = {
            "am_wind": am,
            "pm_wind": pm,
            "advantage": advantage,
            "diff_kmh": round(diff, 1),
        }

    return wave_data


def build_player_weather_profiles(min_rounds: int = 20) -> dict:
    """
    Build per-player weather resilience profiles from historical data.

    Cross-references rounds with tournament_weather to compute:
    - SG in windy conditions (>15 km/h) vs calm
    - SG in wet conditions (>2mm rain) vs dry
    - SG in cold conditions (<10C) vs warm

    Returns {player_key: {"wind_sg_diff": float, "rain_sg_diff": float,
                          "cold_sg_diff": float, "total_rounds": int}}
    """
    conn = db.get_conn()

    # Get all rounds joined with weather summary data
    rows = conn.execute("""
        SELECT r.player_key, r.sg_total, r.round_num,
               r.event_id, r.year,
               ws.avg_wind_kmh, ws.total_precip_mm, ws.avg_temp_c,
               ws.conditions_rating
        FROM rounds r
        JOIN tournament_weather_summary ws
            ON r.event_id = ws.event_id AND r.year = ws.year AND r.round_num = ws.round_num
        WHERE r.sg_total IS NOT NULL
    """).fetchall()
    conn.close()

    if not rows:
        return {}

    # Accumulate per-player stats in different conditions
    player_data = {}
    for r in rows:
        pk = r["player_key"]
        sg = r["sg_total"]
        wind = r["avg_wind_kmh"]
        precip = r["total_precip_mm"]
        temp = r["avg_temp_c"]

        if pk not in player_data:
            player_data[pk] = {
                "windy_sg": [], "calm_sg": [],
                "wet_sg": [], "dry_sg": [],
                "cold_sg": [], "warm_sg": [],
                "total_rounds": 0,
            }

        player_data[pk]["total_rounds"] += 1

        if wind is not None:
            if wind > WIND_THRESHOLD_KMH:
                player_data[pk]["windy_sg"].append(sg)
            else:
                player_data[pk]["calm_sg"].append(sg)

        if precip is not None:
            if precip > RAIN_THRESHOLD_MM:
                player_data[pk]["wet_sg"].append(sg)
            else:
                player_data[pk]["dry_sg"].append(sg)

        if temp is not None:
            if temp < COLD_THRESHOLD_C:
                player_data[pk]["cold_sg"].append(sg)
            else:
                player_data[pk]["warm_sg"].append(sg)

    # Compute differentials
    profiles = {}
    for pk, d in player_data.items():
        if d["total_rounds"] < min_rounds:
            continue

        wind_diff = _safe_diff(d["windy_sg"], d["calm_sg"])
        rain_diff = _safe_diff(d["wet_sg"], d["dry_sg"])
        cold_diff = _safe_diff(d["cold_sg"], d["warm_sg"])

        profiles[pk] = {
            "wind_sg_diff": round(wind_diff, 3) if wind_diff is not None else None,
            "rain_sg_diff": round(rain_diff, 3) if rain_diff is not None else None,
            "cold_sg_diff": round(cold_diff, 3) if cold_diff is not None else None,
            "windy_rounds": len(d["windy_sg"]),
            "total_rounds": d["total_rounds"],
        }

    return profiles


def compute_weather_adjustments(
    forecast: dict,
    player_keys: list[str],
    tee_times: dict = None,
    weather_profiles: dict = None,
) -> dict:
    """
    Compute per-player weather adjustments to apply to composite scores.

    Returns {player_key: {"adjustment": float, "wave_adj": float,
                          "resilience_adj": float, "reason": str}}

    Only returns non-zero adjustments when conditions are meaningful.
    """
    if not forecast:
        return {}

    severity = forecast.get("tournament_severity", 0)
    if severity < 10:
        return {}

    wave_data = compute_wave_advantage(forecast)
    if weather_profiles is None:
        weather_profiles = {}

    # Determine if any round has meaningful wave splits
    has_wave_split = any(
        wd.get("diff_kmh", 0) >= 5.0 and wd.get("advantage") != "neutral"
        for wd in wave_data.values()
    )

    # Forecasted conditions for resilience scoring
    round_days = forecast["days"][1:5] if len(forecast["days"]) > 4 else forecast["days"][:4]
    avg_wind = _avg([d["avg_wind_kmh"] for d in round_days if d.get("avg_wind_kmh")])
    total_rain = sum(d["total_precip_mm"] for d in round_days if d.get("total_precip_mm"))
    avg_temp = _avg([d["avg_temp_c"] for d in round_days if d.get("avg_temp_c")])

    is_windy = avg_wind is not None and avg_wind > WIND_THRESHOLD_KMH
    is_rainy = total_rain > RAIN_THRESHOLD_MM * 2
    is_cold = avg_temp is not None and avg_temp < COLD_THRESHOLD_C

    adjustments = {}
    for pk in player_keys:
        wave_adj = 0.0
        resilience_adj = 0.0
        reasons = []

        # Wave advantage from tee times
        # PGA Tour tee times alternate: R1 morning = R2 afternoon, R3 morning = R4 afternoon
        if has_wave_split and tee_times and pk in tee_times:
            tee = tee_times[pk]
            tee_str = str(tee).strip()
            is_am_tee_r1 = False
            try:
                if ":" in tee_str:
                    hour = int(tee_str.split(":")[0])
                    is_am_tee_r1 = hour < 12
            except (ValueError, IndexError):
                pass

            for round_num, wd in wave_data.items():
                if wd["advantage"] == "neutral":
                    continue

                # Flip AM/PM between rounds: odd rounds match R1, even rounds flip
                rn = int(round_num) if isinstance(round_num, (int, str)) else 1
                is_am_this_round = is_am_tee_r1 if (rn % 2 == 1) else (not is_am_tee_r1)

                favorable = (
                    (wd["advantage"] == "AM" and is_am_this_round) or
                    (wd["advantage"] == "PM" and not is_am_this_round)
                )
                if favorable:
                    wave_adj += min(MAX_WAVE_ADJUSTMENT, wd["diff_kmh"] * 0.3)
                    reasons.append(f"favorable {wd['advantage']} wave R{round_num}")
                elif not favorable and wd["diff_kmh"] >= 8:
                    wave_adj -= min(MAX_WAVE_ADJUSTMENT * 0.5, wd["diff_kmh"] * 0.15)
                    reasons.append(f"unfavorable wave R{round_num}")

        # Weather resilience from historical profile
        profile = weather_profiles.get(pk)
        if profile:
            if is_windy and profile.get("wind_sg_diff") is not None:
                wind_diff = profile["wind_sg_diff"]
                if profile.get("windy_rounds", 0) >= 8:
                    resilience_adj += min(MAX_RESILIENCE_ADJUSTMENT,
                                         max(-MAX_RESILIENCE_ADJUSTMENT, wind_diff * 3))
                    if wind_diff > 0.2:
                        reasons.append(f"wind specialist (+{wind_diff:.2f} SG)")
                    elif wind_diff < -0.2:
                        reasons.append(f"struggles in wind ({wind_diff:.2f} SG)")

            if is_rainy and profile.get("rain_sg_diff") is not None:
                rain_diff = profile["rain_sg_diff"]
                resilience_adj += min(2.0, max(-2.0, rain_diff * 2))

            if is_cold and profile.get("cold_sg_diff") is not None:
                cold_diff = profile["cold_sg_diff"]
                resilience_adj += min(2.0, max(-2.0, cold_diff * 2))

        total_adj = wave_adj + resilience_adj
        if abs(total_adj) >= 0.5:
            adjustments[pk] = {
                "adjustment": round(total_adj, 2),
                "wave_adj": round(wave_adj, 2),
                "resilience_adj": round(resilience_adj, 2),
                "reason": "; ".join(reasons) if reasons else "weather conditions",
            }

    return adjustments


# ── Helpers ────────────────────────────────────────────────────────

def _safe_idx(hourly: dict, key: str, i: int):
    vals = hourly.get(key, [])
    return vals[i] if i < len(vals) else None


def _avg(values: list) -> Optional[float]:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None


def _safe_diff(group_a: list, group_b: list, min_samples: int = 5) -> Optional[float]:
    """Compute mean difference between two groups, with minimum sample check."""
    if len(group_a) < min_samples or len(group_b) < min_samples:
        return None
    return (sum(group_a) / len(group_a)) - (sum(group_b) / len(group_b))


def _conditions_rating(avg_wind, max_gust, total_precip, avg_temp) -> float:
    """Rate conditions severity: 0 = perfect, 100 = brutal."""
    rating = 0.0
    if avg_wind and avg_wind > 15:
        rating += min(40, (avg_wind - 15) * 3)
    if max_gust and max_gust > 40:
        rating += min(20, (max_gust - 40) * 2)
    if total_precip and total_precip > 0:
        rating += min(30, total_precip * 10)
    if avg_temp and avg_temp < 10:
        rating += min(10, (10 - avg_temp) * 2)
    return min(100, rating)
