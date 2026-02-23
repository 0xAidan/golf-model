"""
Market performance tracking and graduated adaptation.

Tracks wins, losses, and ROI by market type with rolling windows.
Provides graduated response: raise EV thresholds, reduce stakes,
or suppress markets based on rolling performance.
"""

from src import db


def compute_roi_pct(wagered: float, returned: float) -> float | None:
    """Compute ROI percentage. Returns None if no wagers."""
    if wagered is None or wagered <= 0:
        return None
    return round((returned - wagered) / wagered * 100.0, 2)


def aggregate_market_performance_for_tournament(tournament_id: int) -> dict:
    """Aggregate prediction_log results into market_performance for a tournament.

    Groups settled predictions by bet_type, computes win/loss/ROI stats,
    and upserts into market_performance. Returns dict keyed by market_type.
    """
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT bet_type,
                      COUNT(*) as bets,
                      SUM(CASE WHEN actual_outcome = 1 THEN 1 ELSE 0 END) as wins,
                      SUM(CASE WHEN actual_outcome = 0 THEN 1 ELSE 0 END) as losses,
                      SUM(profit) as total_profit
               FROM prediction_log
               WHERE tournament_id = ? AND actual_outcome IS NOT NULL
               GROUP BY bet_type""",
            (tournament_id,),
        ).fetchall()

        if not rows:
            return {}

        result = {}
        for row in rows:
            market_type = row["bet_type"]
            bets_placed = row["bets"]
            wins = row["wins"]
            losses = row["losses"]
            pushes = bets_placed - wins - losses
            units_wagered = float(bets_placed)
            total_profit = row["total_profit"] or 0.0
            units_returned = units_wagered + total_profit
            roi = compute_roi_pct(units_wagered, units_returned)

            conn.execute(
                "DELETE FROM market_performance WHERE market_type = ? AND tournament_id = ?",
                (market_type, tournament_id),
            )
            conn.execute(
                """INSERT INTO market_performance
                   (market_type, tournament_id, bets_placed, wins, losses, pushes,
                    units_wagered, units_returned, roi_pct, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
                (market_type, tournament_id, bets_placed, wins, losses, pushes,
                 units_wagered, units_returned, roi),
            )

            result[market_type] = {
                "bets_placed": bets_placed,
                "wins": wins,
                "losses": losses,
                "pushes": pushes,
                "units_wagered": units_wagered,
                "units_returned": units_returned,
                "roi_pct": roi,
            }

        conn.commit()
        return result
    finally:
        conn.close()


def _count_consecutive_losses(conn, market_type: str) -> int:
    """Count consecutive actual_outcome=0 from the most recent predictions."""
    rows = conn.execute(
        """SELECT actual_outcome FROM prediction_log
           WHERE bet_type = ? AND actual_outcome IS NOT NULL
           ORDER BY id DESC""",
        (market_type,),
    ).fetchall()

    count = 0
    for row in rows:
        if row["actual_outcome"] == 0:
            count += 1
        else:
            break
    return count


def get_rolling_market_performance(market_type: str, last_n: int = 20) -> dict:
    """Rolling performance summary across recent tournaments.

    Accumulates tournament-level market_performance rows (ordered by
    tournament date DESC) until total bets_placed >= last_n.
    """
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT mp.bets_placed, mp.wins, mp.losses,
                      mp.units_wagered, mp.units_returned
               FROM market_performance mp
               JOIN tournaments t ON mp.tournament_id = t.id
               WHERE mp.market_type = ?
               ORDER BY t.date DESC""",
            (market_type,),
        ).fetchall()

        if not rows:
            return {
                "total_bets": 0,
                "total_wins": 0,
                "total_losses": 0,
                "total_wagered": 0.0,
                "total_returned": 0.0,
                "roi_pct": None,
                "tournaments_included": 0,
                "consecutive_losses": 0,
            }

        total_bets = 0
        total_wins = 0
        total_losses = 0
        total_wagered = 0.0
        total_returned = 0.0
        tournaments_included = 0

        for row in rows:
            total_bets += row["bets_placed"]
            total_wins += row["wins"]
            total_losses += row["losses"]
            total_wagered += row["units_wagered"]
            total_returned += row["units_returned"]
            tournaments_included += 1
            if total_bets >= last_n:
                break

        roi = compute_roi_pct(total_wagered, total_returned)
        consecutive_losses = _count_consecutive_losses(conn, market_type)

        return {
            "total_bets": total_bets,
            "total_wins": total_wins,
            "total_losses": total_losses,
            "total_wagered": total_wagered,
            "total_returned": total_returned,
            "roi_pct": roi,
            "tournaments_included": tournaments_included,
            "consecutive_losses": consecutive_losses,
        }
    finally:
        conn.close()


def get_adaptation_state(market_type: str, min_bets: int = 15) -> dict:
    """Graduated adaptation state based on rolling market performance.

    States: normal (default), caution (tighten EV), cold (reduce stakes),
    frozen (suppress entirely). Also freezes on 10+ consecutive losses.
    """
    perf = get_rolling_market_performance(market_type)

    total_bets = perf["total_bets"]
    roi_pct = perf["roi_pct"]
    consecutive_losses = perf["consecutive_losses"]
    tournaments_included = perf["tournaments_included"]

    base = {
        "roi_pct": roi_pct,
        "total_bets": total_bets,
        "consecutive_losses": consecutive_losses,
        "tournaments_included": tournaments_included,
    }

    if total_bets < min_bets:
        return {**base, "state": "normal", "ev_threshold": 0.05,
                "stake_multiplier": 1.0, "suppress": False}

    if consecutive_losses >= 10:
        return {**base, "state": "frozen", "ev_threshold": None,
                "stake_multiplier": 0, "suppress": True}

    if roi_pct is None or roi_pct >= 0:
        return {**base, "state": "normal", "ev_threshold": 0.05,
                "stake_multiplier": 1.0, "suppress": False}

    if roi_pct > -20:
        return {**base, "state": "caution", "ev_threshold": 0.08,
                "stake_multiplier": 1.0, "suppress": False}

    if roi_pct > -40:
        return {**base, "state": "cold", "ev_threshold": 0.12,
                "stake_multiplier": 0.5, "suppress": False}

    return {**base, "state": "frozen", "ev_threshold": None,
            "stake_multiplier": 0, "suppress": True}


def check_recovery(market_type: str, last_n_tracking: int = 5) -> dict:
    """Check whether a frozen market shows recovery signs.

    Looks at the most recent last_n_tracking settled predictions for this
    market_type. If 2+ were wins, signals readiness to unfreeze.
    Does NOT auto-unfreeze; returns advisory data only.
    """
    conn = db.get_conn()
    try:
        rows = conn.execute(
            """SELECT actual_outcome FROM prediction_log
               WHERE bet_type = ? AND actual_outcome IS NOT NULL
               ORDER BY id DESC LIMIT ?""",
            (market_type, last_n_tracking),
        ).fetchall()

        wins = sum(1 for r in rows if r["actual_outcome"] == 1)

        return {
            "should_unfreeze": wins >= 2,
            "wins_in_window": wins,
        }
    finally:
        conn.close()
