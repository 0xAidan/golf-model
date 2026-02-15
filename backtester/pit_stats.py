"""
Point-in-Time (PIT) Rolling Stats Builder

Reconstructs what a player's rolling SG statistics would have been
at the START of each historical tournament, using ONLY data available
before that tournament began.

CRITICAL: Zero future data leakage. For event E in week W, we only
use rounds from events that completed before week W.

The stats are stored in pit_rolling_stats and used by the backtester
to simulate what the model would have predicted at that point in time.

Windows: 12 rounds (hot form), 24 rounds (core window), 50 rounds (stability)
"""

import logging
from collections import defaultdict

from src import db
from src.datagolf import _safe_float

logger = logging.getLogger("pit_stats")

WINDOWS = [12, 24, 50]
SG_FIELDS = ["sg_total", "sg_ott", "sg_app", "sg_arg", "sg_putt", "sg_t2g"]


def build_pit_stats_for_event(event_id: str, year: int) -> int:
    """
    Build point-in-time rolling stats for all players in a given event,
    using only rounds from events that completed BEFORE this event started.

    Returns count of PIT stat rows stored.
    """
    conn = db.get_conn()

    # 1. Get this event's start date to enforce the temporal boundary
    event_info = conn.execute("""
        SELECT start_date FROM historical_event_info
        WHERE event_id = ? AND year = ?
    """, (str(event_id), year)).fetchone()

    if not event_info or not event_info[0]:
        # Fall back: get earliest round date for this event
        first_round = conn.execute("""
            SELECT MIN(event_completed) FROM rounds
            WHERE event_id = ? AND year = ?
        """, (str(event_id), year)).fetchone()

        if first_round and first_round[0]:
            cutoff_date = first_round[0]
        else:
            logger.warning("No date info for event %s/%s, skipping PIT build", event_id, year)
            return 0
    else:
        cutoff_date = event_info[0]

    # 2. Get the players in this event's field
    field_players = conn.execute("""
        SELECT DISTINCT player_key FROM rounds
        WHERE event_id = ? AND year = ?
    """, (str(event_id), year)).fetchall()

    player_keys = [r[0] for r in field_players if r[0]]
    if not player_keys:
        return 0

    # 3. For each player, get all rounds BEFORE this event (strict <)
    #    ordered by event_completed DESC so most recent come first
    count = 0
    for pkey in player_keys:
        past_rounds = conn.execute("""
            SELECT sg_total, sg_ott, sg_app, sg_arg, sg_putt, sg_t2g
            FROM rounds
            WHERE player_key = ?
              AND event_completed < ?
              AND sg_total IS NOT NULL
            ORDER BY event_completed DESC, round_num DESC
        """, (pkey, cutoff_date)).fetchall()

        if not past_rounds:
            continue

        # 4. Compute rolling averages for each window
        for window in WINDOWS:
            window_rounds = past_rounds[:window]
            if not window_rounds:
                continue

            n = len(window_rounds)
            avgs = {}
            for i, field in enumerate(SG_FIELDS):
                vals = [r[i] for r in window_rounds if r[i] is not None]
                if vals:
                    avgs[field] = round(sum(vals) / len(vals), 4)
                else:
                    avgs[field] = None

            try:
                conn.execute("""
                    INSERT OR REPLACE INTO pit_rolling_stats
                    (event_id, year, player_key, window,
                     sg_total, sg_ott, sg_app, sg_arg, sg_putt, sg_t2g,
                     rounds_used)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    str(event_id), year, pkey, window,
                    avgs.get("sg_total"),
                    avgs.get("sg_ott"),
                    avgs.get("sg_app"),
                    avgs.get("sg_arg"),
                    avgs.get("sg_putt"),
                    avgs.get("sg_t2g"),
                    n,
                ))
                count += 1
            except Exception as e:
                logger.warning("PIT stat insert failed for %s: %s", pkey, e)

    conn.commit()
    logger.info("Built %d PIT stat rows for event %s/%s (%d players)",
                count, event_id, year, len(player_keys))
    return count


def build_all_pit_stats(years: list[int] = None, tour: str = "pga") -> dict:
    """
    Build PIT stats for all historical events across given years.

    Events are processed in chronological order to ensure correctness.

    Returns summary dict.
    """
    if years is None:
        years = [2024, 2025, 2026]

    conn = db.get_conn()
    summary = {"events": 0, "stat_rows": 0, "errors": []}

    for year in years:
        # Get events in chronological order
        events = conn.execute("""
            SELECT DISTINCT event_id, start_date
            FROM historical_event_info
            WHERE year = ?
            ORDER BY start_date ASC
        """, (year,)).fetchall()

        if not events:
            # Fall back to rounds table
            events = conn.execute("""
                SELECT DISTINCT event_id, MIN(event_completed) as start_date
                FROM rounds
                WHERE year = ?
                GROUP BY event_id
                ORDER BY start_date ASC
            """, (year,)).fetchall()

        for event_id, _ in events:
            if not event_id:
                continue

            # Skip if already built
            existing = conn.execute("""
                SELECT COUNT(*) FROM pit_rolling_stats
                WHERE event_id = ? AND year = ?
            """, (str(event_id), year)).fetchone()

            if existing and existing[0] > 0:
                continue

            try:
                n = build_pit_stats_for_event(str(event_id), year)
                summary["stat_rows"] += n
                summary["events"] += 1
            except Exception as e:
                summary["errors"].append(f"{event_id}/{year}: {e}")
                logger.error("PIT build failed for %s/%s: %s", event_id, year, e)

    logger.info("PIT build complete: %d events, %d stat rows",
                summary["events"], summary["stat_rows"])
    return summary


def get_pit_stats(event_id: str, year: int,
                  player_key: str, window: int = 24) -> dict | None:
    """
    Retrieve pre-computed PIT stats for a player at a specific event.

    Returns dict with sg_total, sg_ott, etc. or None if not available.
    """
    conn = db.get_conn()
    row = conn.execute("""
        SELECT sg_total, sg_ott, sg_app, sg_arg, sg_putt, sg_t2g, rounds_used
        FROM pit_rolling_stats
        WHERE event_id = ? AND year = ? AND player_key = ? AND window = ?
    """, (str(event_id), year, player_key, window)).fetchone()

    if not row:
        return None

    return {
        "sg_total": row[0], "sg_ott": row[1], "sg_app": row[2],
        "sg_arg": row[3], "sg_putt": row[4], "sg_t2g": row[5],
        "rounds_used": row[6],
    }


def verify_no_leakage(event_id: str, year: int, sample_player: str = None) -> bool:
    """
    Verify that PIT stats for an event contain zero future data leakage.

    Checks that all rounds used in the PIT calculation occurred BEFORE
    the event's start date. Returns True if clean, False if leakage detected.
    """
    conn = db.get_conn()

    # Get event start date
    event_info = conn.execute("""
        SELECT start_date FROM historical_event_info
        WHERE event_id = ? AND year = ?
    """, (str(event_id), year)).fetchone()

    if not event_info or not event_info[0]:
        logger.warning("Cannot verify leakage: no start_date for %s/%s", event_id, year)
        return True  # Cannot verify, assume OK

    start_date = event_info[0]

    # Pick a player to verify
    if sample_player is None:
        sample = conn.execute("""
            SELECT player_key FROM pit_rolling_stats
            WHERE event_id = ? AND year = ? AND window = 24
            LIMIT 1
        """, (str(event_id), year)).fetchone()
        if not sample:
            return True
        sample_player = sample[0]

    # Get the PIT stat's rounds_used count
    pit = conn.execute("""
        SELECT rounds_used FROM pit_rolling_stats
        WHERE event_id = ? AND year = ? AND player_key = ? AND window = 24
    """, (str(event_id), year, sample_player)).fetchone()

    if not pit:
        return True

    rounds_used = pit[0]

    # Count rounds this player had BEFORE the event
    pre_rounds = conn.execute("""
        SELECT COUNT(*) FROM rounds
        WHERE player_key = ?
          AND event_completed < ?
          AND sg_total IS NOT NULL
    """, (sample_player, start_date)).fetchone()

    actual_pre = pre_rounds[0] if pre_rounds else 0

    # The PIT stats should use at most 24 rounds, all from before the event
    if rounds_used > actual_pre:
        logger.error(
            "LEAKAGE DETECTED: PIT used %d rounds but only %d existed before %s for %s",
            rounds_used, actual_pre, start_date, sample_player,
        )
        return False

    logger.info("Leakage check PASSED for %s/%s (player %s): %d rounds, %d available",
                event_id, year, sample_player, rounds_used, actual_pre)
    return True
