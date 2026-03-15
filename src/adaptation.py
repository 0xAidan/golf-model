"""
Market performance tracking and graduated adaptation.

Tracks wins, losses, and ROI by market type with rolling windows.
Provides graduated response: raise EV thresholds, reduce stakes,
or suppress markets based on rolling performance.
"""

from src import db
from src import config


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
        return {**base, "state": "normal", "ev_threshold": config.ADAPTATION_EV_THRESHOLD_NORMAL,
                "stake_multiplier": 1.0, "suppress": False}

    if consecutive_losses >= config.ADAPTATION_CONSECUTIVE_LOSSES_FROZEN:
        return {**base, "state": "frozen", "ev_threshold": None,
                "stake_multiplier": 0, "suppress": True}

    if roi_pct is None or roi_pct >= 0:
        return {**base, "state": "normal", "ev_threshold": config.ADAPTATION_EV_THRESHOLD_NORMAL,
                "stake_multiplier": 1.0, "suppress": False}

    if roi_pct > config.ADAPTATION_ROI_CAUTION:
        return {**base, "state": "caution", "ev_threshold": config.ADAPTATION_EV_THRESHOLD_CAUTION,
                "stake_multiplier": 1.0, "suppress": False}

    if roi_pct > config.ADAPTATION_ROI_COLD:
        return {**base, "state": "cold", "ev_threshold": config.ADAPTATION_EV_THRESHOLD_COLD,
                "stake_multiplier": config.ADAPTATION_STAKE_MULTIPLIER_COLD, "suppress": False}

    return {**base, "state": "frozen", "ev_threshold": None,
            "stake_multiplier": 0, "suppress": True}


def log_ai_adjustment(tournament_id: int, player_key: str,
                      adjustment_value: float, reasoning: str = None):
    """Log a single AI adjustment to the database."""
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO ai_adjustments (tournament_id, player_key, adjustment_value, reasoning) "
        "VALUES (?, ?, ?, ?)",
        (tournament_id, player_key, adjustment_value, reasoning),
    )
    conn.commit()
    conn.close()


def evaluate_ai_adjustments(tournament_id: int) -> dict:
    """
    After a tournament, evaluate whether AI adjustments helped.

    For each adjustment:
    - Get the player's actual finish vs their composite rank (baseline)
    - If adjustment was positive and player beat baseline: helpful
    - If adjustment was negative and player underperformed baseline: helpful
    - Otherwise: harmful

    Returns summary dict.
    """
    conn = db.get_conn()

    adjustments = conn.execute(
        "SELECT * FROM ai_adjustments WHERE tournament_id = ?",
        (tournament_id,),
    ).fetchall()

    if not adjustments:
        conn.close()
        return {"total": 0, "helpful": 0, "harmful": 0, "inconclusive": 0}

    results = conn.execute(
        "SELECT player_key, finish_position FROM results WHERE tournament_id = ?",
        (tournament_id,),
    ).fetchall()
    conn.close()

    finish_map = {r["player_key"]: r["finish_position"] for r in results if r["player_key"]}

    helpful = 0
    harmful = 0
    inconclusive = 0

    for adj in adjustments:
        pk = adj["player_key"]
        adj_val = adj["adjustment_value"]
        finish = finish_map.get(pk)

        if finish is None:
            inconclusive += 1
            continue

        if adj_val > 0 and finish <= 20:
            helpful += 1
            was_helpful = 1
        elif adj_val < 0 and finish > 20:
            helpful += 1
            was_helpful = 1
        elif adj_val > 0 and finish > 30:
            harmful += 1
            was_helpful = 0
        elif adj_val < 0 and finish <= 10:
            harmful += 1
            was_helpful = 0
        else:
            inconclusive += 1
            was_helpful = None

        conn2 = db.get_conn()
        conn2.execute(
            "UPDATE ai_adjustments SET was_helpful = ?, actual_delta = ? WHERE id = ?",
            (was_helpful, finish, adj["id"]),
        )
        conn2.commit()
        conn2.close()

    return {
        "total": len(adjustments),
        "helpful": helpful,
        "harmful": harmful,
        "inconclusive": inconclusive,
        "net_effect": helpful - harmful,
    }


def get_ai_adjustment_config() -> dict:
    """
    Determine current AI adjustment cap and enabled status based on historical performance.

    Rules:
    - Default: enabled, cap ±5
    - After 10+ tournaments AND 50+ adjustments with net_effect < 0: cap ±2
    - After 5 more tournaments still negative: disabled entirely
    """
    conn = db.get_conn()

    tournament_count = conn.execute(
        "SELECT COUNT(DISTINCT tournament_id) as cnt FROM ai_adjustments"
    ).fetchone()
    total_tournaments = tournament_count["cnt"] if tournament_count else 0

    stats = conn.execute(
        "SELECT COUNT(*) as total, "
        "SUM(CASE WHEN was_helpful = 1 THEN 1 ELSE 0 END) as helpful, "
        "SUM(CASE WHEN was_helpful = 0 THEN 1 ELSE 0 END) as harmful "
        "FROM ai_adjustments WHERE was_helpful IS NOT NULL"
    ).fetchone()
    conn.close()

    total = stats["total"] if stats and stats["total"] else 0
    helpful_count = stats["helpful"] if stats and stats["helpful"] else 0
    harmful_count = stats["harmful"] if stats and stats["harmful"] else 0
    net = helpful_count - harmful_count

    from src import config
    default_cap = config.AI_ADJUSTMENT_CAP  # 3.0
    if total_tournaments < 10 or total < 50:
        return {"enabled": True, "cap": default_cap, "reason": f"Insufficient data ({total_tournaments} tournaments, {total} adjustments)"}

    if net < 0:
        if total_tournaments >= 15:
            return {"enabled": False, "cap": 0.0, "reason": f"Auto-disabled: net effect {net} over {total_tournaments} tournaments"}
        return {"enabled": True, "cap": 2.0, "reason": f"Reduced cap: net effect {net} over {total_tournaments} tournaments"}

    return {"enabled": True, "cap": default_cap, "reason": f"Performing well: net effect +{net}"}


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
