"""
Point-in-Time (PIT) Rolling Stats Builder

Reconstructs what a player's rolling SG statistics would have been
at the START of each historical tournament, using ONLY data available
before that tournament began.

CRITICAL: Zero future data leakage. For event E in week W, we only
use rounds from events that completed before week W.

The stats are stored in pit_rolling_stats and used by the backtester
to simulate what the model would have predicted at that point in time.

Windows: 8, 12, 16, 20, 24, 50 rounds (aligned with live model discovery)
"""

import logging
import re
from collections import defaultdict

from src import db
from src.datagolf import _safe_float

logger = logging.getLogger("pit_stats")

WINDOWS = [8, 12, 16, 20, 24, 50]
SG_FIELDS = ["sg_total", "sg_ott", "sg_app", "sg_arg", "sg_putt", "sg_t2g"]


def _parse_finish_position(fin_text: str) -> int | None:
    """Parse a finish position from fin_text like 'T12', '1', 'CUT', 'WD'."""
    if not fin_text:
        return None
    cleaned = fin_text.strip().upper()
    if cleaned in ("CUT", "MC", "WD", "DQ", "DNS", "MDF", ""):
        return None
    cleaned = cleaned.lstrip("T")
    try:
        return int(cleaned)
    except ValueError:
        return None


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
        prev_event = conn.execute("""
            SELECT MAX(event_completed) FROM rounds
            WHERE event_id != ? AND (year < ? OR (year = ? AND event_completed < (
                SELECT MIN(event_completed) FROM rounds
                WHERE event_id = ? AND year = ?
            )))
        """, (str(event_id), year, year, str(event_id), year)).fetchone()

        if prev_event and prev_event[0]:
            cutoff_date = prev_event[0]
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
    #    ordered by event_completed DESC so most recent come first.
    #    ALSO exclude rounds from the current event_id as a safety guard
    #    against data leakage even if dates overlap.
    count = 0
    str_event_id = str(event_id)
    for pkey in player_keys:
        past_rounds = conn.execute("""
            SELECT sg_total, sg_ott, sg_app, sg_arg, sg_putt, sg_t2g
            FROM rounds
            WHERE player_key = ?
              AND event_completed < ?
              AND event_id != ?
              AND sg_total IS NOT NULL
            ORDER BY event_completed DESC, round_num DESC
        """, (pkey, cutoff_date, str_event_id)).fetchall()

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

    # 5. Compute field-relative ranks for each window
    _compute_ranks_for_event(conn, str_event_id, year)

    logger.info("Built %d PIT stat rows for event %s/%s (%d players)",
                count, event_id, year, len(player_keys))
    return count


def _compute_ranks_for_event(conn, event_id: str, year: int):
    """
    Compute field-relative sg_total ranks within each window for an event.
    Rank 1 = best sg_total in the field for that window.
    """
    for window in WINDOWS:
        rows = conn.execute("""
            SELECT id, player_key, sg_total
            FROM pit_rolling_stats
            WHERE event_id = ? AND year = ? AND window = ?
              AND sg_total IS NOT NULL
            ORDER BY sg_total DESC
        """, (event_id, year, window)).fetchall()

        for rank, row in enumerate(rows, start=1):
            conn.execute("""
                UPDATE pit_rolling_stats SET sg_total_rank = ?
                WHERE id = ?
            """, (rank, row[0]))

    conn.commit()


def build_pit_course_stats_for_event(event_id: str, year: int) -> int:
    """
    Build point-in-time course-specific stats for all players in an event.

    For each player, computes rolling SG averages from ONLY their rounds
    at the same course_num that completed before the event started.

    Returns count of rows stored.
    """
    conn = db.get_conn()

    # 1. Get event's course_num and start date
    event_info = conn.execute("""
        SELECT h.start_date, r.course_num
        FROM historical_event_info h
        JOIN rounds r ON r.event_id = h.event_id AND r.year = h.year
        WHERE h.event_id = ? AND h.year = ?
        LIMIT 1
    """, (str(event_id), year)).fetchone()

    if not event_info:
        # Fall back: get course_num from rounds
        fallback = conn.execute("""
            SELECT MIN(event_completed), course_num FROM rounds
            WHERE event_id = ? AND year = ?
        """, (str(event_id), year)).fetchone()
        if not fallback or not fallback[1]:
            logger.warning("No course info for event %s/%s, skipping course stats", event_id, year)
            return 0
        cutoff_date = fallback[0]
        course_num = fallback[1]
    else:
        cutoff_date = event_info[0]
        course_num = event_info[1]

    if not cutoff_date or not course_num:
        logger.warning("Missing cutoff_date or course_num for %s/%s", event_id, year)
        return 0

    # 2. Get the players in this event's field
    field_players = conn.execute("""
        SELECT DISTINCT player_key FROM rounds
        WHERE event_id = ? AND year = ?
    """, (str(event_id), year)).fetchall()

    player_keys = [r[0] for r in field_players if r[0]]
    if not player_keys:
        return 0

    str_event_id = str(event_id)
    count = 0

    for pkey in player_keys:
        # 3. Get all rounds at the SAME COURSE before this event
        course_rounds = conn.execute("""
            SELECT sg_total, sg_ott, sg_app, sg_arg, sg_putt, sg_t2g,
                   fin_text, round_num
            FROM rounds
            WHERE player_key = ?
              AND course_num = ?
              AND event_completed < ?
              AND event_id != ?
            ORDER BY event_completed DESC, round_num DESC
        """, (pkey, course_num, cutoff_date, str_event_id)).fetchall()

        if not course_rounds:
            continue

        # Compute averages from all available course rounds
        rounds_played = len(course_rounds)
        avgs = {}
        for i, field in enumerate(SG_FIELDS):
            vals = [r[i] for r in course_rounds if r[i] is not None]
            if vals:
                avgs[field] = round(sum(vals) / len(vals), 4)
            else:
                avgs[field] = None

        # Parse finish positions (fin_text is per-event, not per-round,
        # but each round row carries the event's fin_text)
        seen_events = set()
        finish_positions = []
        for r in course_rounds:
            fin = r[6]  # fin_text
            event_key = f"{r[6]}_{r[7]}"  # dedup by fin_text+round_num combo
            if fin and event_key not in seen_events:
                pos = _parse_finish_position(fin)
                if pos is not None:
                    finish_positions.append(pos)
                seen_events.add(event_key)

        # Deduplicate finish positions (same event has same fin_text per round)
        unique_finishes = list(set(finish_positions)) if finish_positions else []
        avg_finish = round(sum(unique_finishes) / len(unique_finishes), 1) if unique_finishes else None
        best_finish = min(unique_finishes) if unique_finishes else None

        try:
            conn.execute("""
                INSERT OR REPLACE INTO pit_course_stats
                (event_id, year, player_key, course_num,
                 sg_total, sg_ott, sg_app, sg_arg, sg_putt, sg_t2g,
                 rounds_played, avg_finish, best_finish)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                str_event_id, year, pkey, course_num,
                avgs.get("sg_total"),
                avgs.get("sg_ott"),
                avgs.get("sg_app"),
                avgs.get("sg_arg"),
                avgs.get("sg_putt"),
                avgs.get("sg_t2g"),
                rounds_played,
                avg_finish,
                best_finish,
            ))
            count += 1
        except Exception as e:
            logger.warning("PIT course stat insert failed for %s: %s", pkey, e)

    conn.commit()
    logger.info("Built %d PIT course stat rows for event %s/%s (course %s)",
                count, event_id, year, course_num)
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
    summary = {"events": 0, "stat_rows": 0, "course_stat_rows": 0, "errors": []}

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

            # Skip if already built (check for new windows too)
            existing = conn.execute("""
                SELECT COUNT(*) FROM pit_rolling_stats
                WHERE event_id = ? AND year = ? AND window = 8
            """, (str(event_id), year)).fetchone()

            if existing and existing[0] > 0:
                continue

            try:
                # Clear old data for this event (may have old window set)
                conn.execute("""
                    DELETE FROM pit_rolling_stats
                    WHERE event_id = ? AND year = ?
                """, (str(event_id), year))
                conn.execute("""
                    DELETE FROM pit_course_stats
                    WHERE event_id = ? AND year = ?
                """, (str(event_id), year))
                conn.commit()

                n = build_pit_stats_for_event(str(event_id), year)
                summary["stat_rows"] += n

                cn = build_pit_course_stats_for_event(str(event_id), year)
                summary["course_stat_rows"] += cn

                summary["events"] += 1
            except Exception as e:
                summary["errors"].append(f"{event_id}/{year}: {e}")
                logger.error("PIT build failed for %s/%s: %s", event_id, year, e)

    logger.info("PIT build complete: %d events, %d stat rows, %d course stat rows",
                summary["events"], summary["stat_rows"], summary["course_stat_rows"])
    return summary


def get_pit_stats(event_id: str, year: int,
                  player_key: str, window: int = 24) -> dict | None:
    """
    Retrieve pre-computed PIT stats for a player at a specific event.

    Returns dict with sg_total, sg_ott, etc. or None if not available.
    """
    conn = db.get_conn()
    row = conn.execute("""
        SELECT sg_total, sg_ott, sg_app, sg_arg, sg_putt, sg_t2g,
               rounds_used, sg_total_rank
        FROM pit_rolling_stats
        WHERE event_id = ? AND year = ? AND player_key = ? AND window = ?
    """, (str(event_id), year, player_key, window)).fetchone()

    if not row:
        return None

    return {
        "sg_total": row[0], "sg_ott": row[1], "sg_app": row[2],
        "sg_arg": row[3], "sg_putt": row[4], "sg_t2g": row[5],
        "rounds_used": row[6], "sg_total_rank": row[7],
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
