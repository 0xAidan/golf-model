"""Preflight checks for autoresearch: DB coverage for walk-forward replay."""

from __future__ import annotations

from typing import Any

from backtester.weighted_walkforward import load_historical_events
from src import config as src_config
from src import db


def validate_autoresearch_data_health(
    years: list[int] | None = None,
) -> dict[str, Any]:
    """
    Summarize whether golf.db has enough historical data for meaningful autoresearch.

    Returns ok=False when events or PIT/odds coverage is too thin for guardrails.
    """
    events = load_historical_events(years)
    event_count = len(events)
    params = src_config.get_autoresearch_guardrail_params()
    min_bets_required = int(params.get("min_bets", 30))

    conn = db.get_conn()
    pit_rows = 0
    odds_rows = 0
    matchup_rows = 0
    if years:
        ph = ",".join("?" * len(years))
        pit_rows = conn.execute(
            f"SELECT COUNT(*) AS c FROM pit_rolling_stats WHERE year IN ({ph})",
            years,
        ).fetchone()["c"]
        odds_rows = conn.execute(
            f"SELECT COUNT(*) AS c FROM historical_odds WHERE year IN ({ph})",
            years,
        ).fetchone()["c"]
        matchup_rows = conn.execute(
            f"SELECT COUNT(*) AS c FROM historical_matchup_odds WHERE year IN ({ph})",
            years,
        ).fetchone()["c"]
    else:
        pit_rows = conn.execute("SELECT COUNT(*) AS c FROM pit_rolling_stats").fetchone()["c"]
        odds_rows = conn.execute("SELECT COUNT(*) AS c FROM historical_odds").fetchone()["c"]
        matchup_rows = conn.execute("SELECT COUNT(*) AS c FROM historical_matchup_odds").fetchone()["c"]

    live_picks_tournaments = 0
    tournaments_in_years = 0
    if years:
        ph = ",".join("?" * len(years))
        live_picks_tournaments = conn.execute(
            f"""
            SELECT COUNT(DISTINCT p.tournament_id) AS c FROM picks p
            JOIN tournaments t ON t.id = p.tournament_id
            WHERE t.year IN ({ph})
            """,
            years,
        ).fetchone()["c"]
        tournaments_in_years = conn.execute(
            f"SELECT COUNT(*) AS c FROM tournaments WHERE year IN ({ph})",
            years,
        ).fetchone()["c"]
    else:
        live_picks_tournaments = conn.execute(
            "SELECT COUNT(DISTINCT tournament_id) AS c FROM picks"
        ).fetchone()["c"]
    conn.close()

    warnings: list[str] = []
    if event_count < 3:
        warnings.append(
            f"Very few historical events ({event_count}) for selected years — run backfill and build PIT stats."
        )
    if pit_rows < 50:
        warnings.append(
            f"Low pit_rolling_stats row count ({pit_rows}) — run backtester.pit_stats.build_all_pit_stats for your years."
        )
    if odds_rows < 20:
        warnings.append(
            f"Sparse historical_odds ({odds_rows}) — backfill odds for walk-forward placement replay."
        )
    if matchup_rows < 10:
        warnings.append(
            f"Few historical_matchup_odds rows ({matchup_rows}) — matchup replay may be empty."
        )

    if tournaments_in_years and live_picks_tournaments < max(1, tournaments_in_years // 2):
        warnings.append(
            f"Live picks sparse: {live_picks_tournaments}/{tournaments_in_years} "
            "tournaments have picks rows (expected for track record / calibration)."
        )

    ok = event_count >= 3 and pit_rows >= 50 and (odds_rows >= 20 or matchup_rows >= 10)

    return {
        "ok": ok,
        "event_count": event_count,
        "pit_rolling_stats_rows": pit_rows,
        "historical_odds_rows": odds_rows,
        "historical_matchup_odds_rows": matchup_rows,
        "live_picks_tournaments": live_picks_tournaments,
        "tournaments_in_years": tournaments_in_years,
        "min_bets_guardrail": min_bets_required,
        "years": list(years) if years else None,
        "warnings": warnings,
        "summary": (
            "Data coverage looks usable for autoresearch."
            if ok
            else "Autoresearch may return weak or empty metrics until backfill/PIT/odds data improves."
        ),
    }
