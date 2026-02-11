"""
Rolling Stats Computation Engine

Replaces Betsperts CSVs by computing all rolling SG windows,
course-specific averages, traditional stat averages, and field
rankings from the round-level data stored in the rounds table.

Output is written to the metrics table in the same schema that
csv_parser.py uses, so form.py / course_fit.py / momentum.py
work without changes.

Usage:
    compute_rolling_metrics(tournament_id, field_player_keys, course_num)
"""

from src import db
from src.player_normalizer import display_name

# Round windows to compute (matches what Betsperts provides)
ROUND_WINDOWS = [8, 12, 16, 24]

# SG categories available in round data
SG_CATEGORIES = {
    "SG:TOT": "sg_total",
    "SG:OTT": "sg_ott",
    "SG:APP": "sg_app",
    "SG:ARG": "sg_arg",
    "SG:P": "sg_putt",
    "SG:T2G": "sg_t2g",
}

# Traditional stats from round data
TRADITIONAL_STATS = {
    "Dr Distance": "driving_dist",
    "Dr Accuracy %": "driving_acc",
    "GIR %": "gir",
    "Scrambling %": "scrambling",
    "FW Prox": "prox_fw",
    "Rough Prox": "prox_rgh",
}


def _compute_average(rounds: list[dict], field: str) -> float | None:
    """Compute average of a field across rounds, skipping None values."""
    vals = [r[field] for r in rounds if r.get(field) is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _rank_players(player_values: dict[str, float | None], higher_is_better: bool = True) -> dict[str, int]:
    """
    Rank players by their values. Returns {player_key: rank}.
    Rank 1 = best. Players with None values get the worst rank.
    """
    # Separate players with values from those without
    with_vals = {k: v for k, v in player_values.items() if v is not None}
    without_vals = {k: v for k, v in player_values.items() if v is None}

    # Sort: for SG, higher is better; for some stats it varies
    sorted_players = sorted(with_vals.items(), key=lambda x: x[1],
                            reverse=higher_is_better)

    ranks = {}
    for i, (pk, _) in enumerate(sorted_players):
        ranks[pk] = i + 1

    # Players without data get the next rank (field_size)
    next_rank = len(with_vals) + 1
    for pk in without_vals:
        ranks[pk] = next_rank

    return ranks


def compute_rolling_metrics(tournament_id: int,
                            field_player_keys: list[str],
                            course_num: int = None) -> dict:
    """
    Compute all rolling stats and rankings for a tournament field,
    then write them into the metrics table.

    This is the main function that replaces Betsperts CSV ingestion.

    Args:
        tournament_id: The tournament to store metrics for.
        field_player_keys: List of normalized player_key values in the field.
        course_num: DG course_num for course-specific computations (optional).

    Returns:
        Summary dict with counts of what was computed.
    """
    if not field_player_keys:
        return {"error": "No players in field"}

    # Fetch display names from existing metrics or rounds
    display_names = db.get_player_display_names(tournament_id)

    # Also build from rounds if needed
    conn = db.get_conn()
    for pk in field_player_keys:
        if pk not in display_names:
            row = conn.execute(
                "SELECT player_name FROM rounds WHERE player_key = ? LIMIT 1",
                (pk,),
            ).fetchone()
            if row:
                display_names[pk] = display_name(row["player_name"])
    conn.close()

    all_metric_rows = []
    sg_computed = 0
    trad_computed = 0
    course_computed = 0

    # ═══ 1. Rolling SG windows ═══
    # For each window size, compute average SG per category, then rank
    for window in ROUND_WINDOWS:
        # Collect averages for each player and each SG category
        player_sg_avgs = {}  # {player_key: {sg_name: avg_value}}

        for pk in field_player_keys:
            rounds = db.get_player_recent_rounds_by_key(pk, limit=window)
            if not rounds:
                continue

            avgs = {}
            for sg_name, db_field in SG_CATEGORIES.items():
                avg = _compute_average(rounds, db_field)
                avgs[sg_name] = avg
            avgs["_rounds_used"] = len(rounds)
            player_sg_avgs[pk] = avgs

        # Compute ranks within the field for each SG category
        for sg_name in SG_CATEGORIES:
            values = {pk: avgs.get(sg_name) for pk, avgs in player_sg_avgs.items()}
            # Include all field players (those without data get worst rank)
            for pk in field_player_keys:
                if pk not in values:
                    values[pk] = None

            ranks = _rank_players(values, higher_is_better=True)

            for pk, rank in ranks.items():
                pdisp = display_names.get(pk, pk)
                all_metric_rows.append({
                    "tournament_id": tournament_id,
                    "csv_import_id": None,
                    "player_key": pk,
                    "player_display": pdisp,
                    "metric_category": "strokes_gained",
                    "data_mode": "recent_form",
                    "round_window": str(window),
                    "metric_name": sg_name,
                    "metric_value": float(rank),
                    "metric_text": None,
                })

                # Also store the raw average as a separate metric for the AI brain
                raw_val = values.get(pk)
                if raw_val is not None:
                    all_metric_rows.append({
                        "tournament_id": tournament_id,
                        "csv_import_id": None,
                        "player_key": pk,
                        "player_display": pdisp,
                        "metric_category": "strokes_gained_value",
                        "data_mode": "recent_form",
                        "round_window": str(window),
                        "metric_name": sg_name,
                        "metric_value": round(raw_val, 4),
                        "metric_text": None,
                    })
                sg_computed += 1

        # Store rounds_played as meta for each window
        for pk, avgs in player_sg_avgs.items():
            pdisp = display_names.get(pk, pk)
            all_metric_rows.append({
                "tournament_id": tournament_id,
                "csv_import_id": None,
                "player_key": pk,
                "player_display": pdisp,
                "metric_category": "meta",
                "data_mode": "recent_form",
                "round_window": str(window),
                "metric_name": "rounds_played",
                "metric_value": float(avgs.get("_rounds_used", 0)),
                "metric_text": None,
            })

    # ═══ 2. "All" window (no limit — full history in DB) ═══
    player_all_avgs = {}
    for pk in field_player_keys:
        rounds = db.get_player_recent_rounds_by_key(pk, limit=9999)
        if not rounds:
            continue
        avgs = {}
        for sg_name, db_field in SG_CATEGORIES.items():
            avgs[sg_name] = _compute_average(rounds, db_field)
        avgs["_rounds_used"] = len(rounds)
        player_all_avgs[pk] = avgs

    for sg_name in SG_CATEGORIES:
        values = {pk: avgs.get(sg_name) for pk, avgs in player_all_avgs.items()}
        for pk in field_player_keys:
            if pk not in values:
                values[pk] = None
        ranks = _rank_players(values, higher_is_better=True)
        for pk, rank in ranks.items():
            pdisp = display_names.get(pk, pk)
            all_metric_rows.append({
                "tournament_id": tournament_id,
                "csv_import_id": None,
                "player_key": pk,
                "player_display": pdisp,
                "metric_category": "strokes_gained",
                "data_mode": "recent_form",
                "round_window": "all",
                "metric_name": sg_name,
                "metric_value": float(rank),
                "metric_text": None,
            })

    # ═══ 3. Traditional stats (using last 24 rounds) ═══
    for stat_name, db_field in TRADITIONAL_STATS.items():
        values = {}
        for pk in field_player_keys:
            rounds = db.get_player_recent_rounds_by_key(pk, limit=24)
            avg = _compute_average(rounds, db_field) if rounds else None
            values[pk] = avg

        # For most stats higher is better, except proximity (lower is better)
        higher_better = db_field not in ("prox_fw", "prox_rgh")
        ranks = _rank_players(values, higher_is_better=higher_better)

        # Map to metric categories that match what csv_parser produces
        if db_field in ("driving_dist", "driving_acc"):
            cat = "ott"
        elif db_field in ("gir", "prox_fw", "prox_rgh"):
            cat = "approach"
        elif db_field == "scrambling":
            cat = "around_green"
        else:
            cat = "misc"

        for pk, rank in ranks.items():
            pdisp = display_names.get(pk, pk)
            all_metric_rows.append({
                "tournament_id": tournament_id,
                "csv_import_id": None,
                "player_key": pk,
                "player_display": pdisp,
                "metric_category": cat,
                "data_mode": "recent_form",
                "round_window": "24",
                "metric_name": stat_name,
                "metric_value": float(rank),
                "metric_text": None,
            })
            trad_computed += 1

    # ═══ 4. Course-specific averages ═══
    if course_num:
        player_course_avgs = {}
        for pk in field_player_keys:
            # Look up dg_id for this player
            dg_id = db.get_dg_id_for_player(pk)
            if not dg_id:
                continue
            rounds = db.get_player_course_rounds(dg_id, course_num)
            if not rounds:
                continue

            avgs = {}
            for sg_name, db_field in SG_CATEGORIES.items():
                avgs[sg_name] = _compute_average(rounds, db_field)
            avgs["_rounds_used"] = len(rounds)
            player_course_avgs[pk] = avgs

        # Rank within field
        for sg_name in SG_CATEGORIES:
            values = {pk: avgs.get(sg_name) for pk, avgs in player_course_avgs.items()}
            for pk in field_player_keys:
                if pk not in values:
                    values[pk] = None
            ranks = _rank_players(values, higher_is_better=True)

            for pk, rank in ranks.items():
                pdisp = display_names.get(pk, pk)
                all_metric_rows.append({
                    "tournament_id": tournament_id,
                    "csv_import_id": None,
                    "player_key": pk,
                    "player_display": pdisp,
                    "metric_category": "strokes_gained",
                    "data_mode": "course_specific",
                    "round_window": "all",
                    "metric_name": sg_name,
                    "metric_value": float(rank),
                    "metric_text": None,
                })
                course_computed += 1

        # Store rounds_played at course as meta
        for pk, avgs in player_course_avgs.items():
            pdisp = display_names.get(pk, pk)
            all_metric_rows.append({
                "tournament_id": tournament_id,
                "csv_import_id": None,
                "player_key": pk,
                "player_display": pdisp,
                "metric_category": "meta",
                "data_mode": "course_specific",
                "round_window": "all",
                "metric_name": "rounds_played",
                "metric_value": float(avgs.get("_rounds_used", 0)),
                "metric_text": None,
            })

    # ═══ 5. Log import and store all metrics ═══
    if all_metric_rows:
        import_id = db.log_csv_import(
            tournament_id, "computed_rolling_stats", "computed",
            "recent_form", "all", len(all_metric_rows), source="computed"
        )
        # Update csv_import_id for all rows
        for row in all_metric_rows:
            if row["csv_import_id"] is None:
                row["csv_import_id"] = import_id

        db.store_metrics(all_metric_rows)

    summary = {
        "total_metrics": len(all_metric_rows),
        "sg_metrics": sg_computed,
        "traditional_stat_metrics": trad_computed,
        "course_specific_metrics": course_computed,
        "players_in_field": len(field_player_keys),
        "windows_computed": ROUND_WINDOWS + ["all"],
    }

    return summary


def get_field_from_metrics(tournament_id: int) -> list[str]:
    """Get the list of player keys that have metrics for a tournament."""
    return db.get_all_players(tournament_id)


def get_field_from_rounds(dg_ids: list[int] = None) -> list[str]:
    """
    Get player keys from the rounds table for a list of dg_ids.

    Useful when you have the field from DG field-updates but need player_keys.
    """
    if not dg_ids:
        return []
    conn = db.get_conn()
    placeholders = ",".join("?" for _ in dg_ids)
    rows = conn.execute(
        f"SELECT DISTINCT player_key FROM rounds WHERE dg_id IN ({placeholders})",
        dg_ids,
    ).fetchall()
    conn.close()
    return [r["player_key"] for r in rows if r["player_key"]]
