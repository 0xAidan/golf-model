"""
Parse and auto-classify any Betsperts Rabbit Hole CSV.

Given a CSV file, this module:
1. Reads it and detects the column layout
2. Classifies the file type (strokes_gained, ott, approach, sim, etc.)
3. Detects the round window (all, 8, 12, 16, 24, etc.) from filename or data
4. Detects data mode (course_specific vs recent_form) from filename
5. Normalizes player names
6. Returns structured metric rows ready for db.store_metrics()
"""

import csv
import os
import re
import pandas as pd
from typing import Optional

from src.player_normalizer import normalize_name, display_name


# ── File type classification ────────────────────────────────────────
# Each file type is identified by signature columns that appear in
# that view's CSV export from Betsperts.

FILE_TYPE_SIGNATURES = {
    "sim": ["Win %", "Top 5 %", "Top 10 %", "Top 20 %"],
    "cheat_sheet": ["TOT", "OTT", "APP", "ARG", "PUTT", "T2G", "BS", "DD", "DA"],
    "recent_form": ["SG:AVG/rd"],
    "ott": ["Dr Distance", "Dr Accuracy %", "Carry Distance"],
    "approach": ["GIR %", "OVR Prox", "GFG %"],
    "approach_prox": ["50-100 Prox", "100-150 Prox"],
    "fairway_approach_prox": ["FW 50-100 Prox"],
    "rough_approach_prox": ["RGH 50-100 Prox"],
    "around_green": ["Scrambling %", "SG Short Grass %"],
    "around_green_shot_types": ["Bunker Save %", "Lob %"],
    "putting": ["Putting 5-10ft", "5-10 ft"],
    "putting_ranges": ["3-5 ft %", "5-10 ft %"],
    "scoring": ["Bogey Avd", "BoB %"],
    "par3_efficiency": ["Par 3 BoB %", "Par 3 Avg"],
    "par4_efficiency": ["Par 4 BoB %", "Par 4 Avg"],
    "par5_efficiency": ["Par 5 BoB %", "Par 5 Avg"],
    "misc": ["Scrambling %"],
    "floor_ceiling": ["Floor", "Ceiling"],
    "finish": ["Avg Finish", "Best Finish"],
    "rolling_averages": ["L4", "L8", "L20"],
    # Default: strokes_gained (SG:TOT, SG:T2G, SG:OTT, SG:APP, SG:BS, SG:ARG, SG:P, SG:SG)
    "strokes_gained": ["SG:TOT", "SG:T2G"],
}


def classify_file_type(columns: list[str], filename: str) -> str:
    """Determine file type from column names, with filename as hint."""
    col_set = set(columns)
    fname_lower = filename.lower()

    # Check filename hints first for ambiguous cases
    if "sim" in fname_lower or "tournament sim" in fname_lower:
        return "sim"
    if "cheat sheet" in fname_lower:
        return "cheat_sheet"
    if "recent form" in fname_lower:
        return "recent_form"
    if "rolling average" in fname_lower or "rolling_average" in fname_lower:
        return "rolling_averages"
    if "floor" in fname_lower and "ceiling" in fname_lower:
        return "floor_ceiling"
    if "finish" in fname_lower:
        return "finish"

    # Check column signatures (order matters — more specific first)
    for file_type, sig_cols in FILE_TYPE_SIGNATURES.items():
        if all(any(sig.lower() in c.lower() for c in columns) for sig in sig_cols):
            return file_type

    # Fallback: if it has SG columns, it's strokes_gained
    if any("SG:" in c for c in columns):
        return "strokes_gained"

    return "unknown"


def detect_round_window(filename: str, df: pd.DataFrame) -> str:
    """Detect round window from filename or data."""
    fname_lower = filename.lower()

    # Check filename for round indicators
    patterns = [
        (r"(\d+)\s*r\b", None),       # "12r", "24r", "16r"
        (r"last\s*(\d+)\s*round", None),  # "last 16 rounds"
        (r"(\d+)\s*round", None),      # "16 round"
    ]
    for pattern, _ in patterns:
        m = re.search(pattern, fname_lower)
        if m:
            return m.group(1)

    if "all round" in fname_lower:
        return "all"

    # Check if there's a 'Rounds' column with consistent values
    if "Rounds" in df.columns:
        # The Rounds column in Betsperts shows how many rounds of data per player
        # Not a single round window, so leave as 'all' if mixed
        pass

    return "all"


def detect_data_mode(filename: str) -> str:
    """Detect whether data is course-specific or recent form."""
    fname_lower = filename.lower()

    # Course-specific indicators
    course_keywords = [
        "tpc", "pebble", "augusta", "torrey", "riviera", "bay hill",
        "sawgrass", "colonial", "muirfield", "quail hollow",
        "course data", "course specific",
    ]
    if any(kw in fname_lower for kw in course_keywords):
        return "course_specific"

    # Recent form / all-courses indicators
    form_keywords = ["12 month", "16r", "12r", "24r", "recent form",
                     "rolling average", "last 6 month", "last 12"]
    if any(kw in fname_lower for kw in form_keywords):
        return "recent_form"

    # Files like "my-file.csv" (from Betsperts main view) default to recent_form
    # Course-specific files usually have the course name in them
    return "recent_form"


# ── Parsing helpers ─────────────────────────────────────────────────

def _find_player_column(columns: list[str]) -> Optional[str]:
    """Find the player name column."""
    for c in columns:
        if c.lower() in ("playername", "player", "player name", "name"):
            return c
    # Check partial matches
    for c in columns:
        if "player" in c.lower() or "name" in c.lower():
            return c
    return None


def _parse_numeric(val) -> Optional[float]:
    """Try to parse a value as numeric. Return None if not possible."""
    if val is None or val == "" or (isinstance(val, str) and val.strip() == ""):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        # Handle percentage strings like "51.43"
        s = str(val).strip().strip('"').strip("%")
        return float(s)
    except (ValueError, TypeError):
        return None


def _parse_finish(val) -> Optional[str]:
    """Parse a finish position value (T14, CUT, W/D, DQ, etc.)."""
    if val is None:
        return None
    s = str(val).strip().strip('"')
    if s == "" or s.lower() == "nan":
        return None
    return s


# ── Main parse function ────────────────────────────────────────────

def parse_csv(filepath: str, tournament_id: int, csv_import_id: int,
              data_mode_override: str = None,
              round_window_override: str = None) -> list[dict]:
    """
    Parse a single Betsperts CSV into metric rows.

    Returns a list of dicts ready for db.store_metrics().
    """
    filename = os.path.basename(filepath)

    # Read CSV
    df = pd.read_csv(filepath, dtype=str)
    df.columns = [c.strip().strip('"') for c in df.columns]

    columns = list(df.columns)
    file_type = classify_file_type(columns, filename)
    data_mode = data_mode_override or detect_data_mode(filename)
    round_window = round_window_override or detect_round_window(filename, df)

    player_col = _find_player_column(columns)
    if not player_col:
        print(f"  WARNING: No player column found in {filename}. Skipping.")
        return []

    # Determine which columns are metrics (skip player name, salary, tee time, etc.)
    skip_cols = {player_col.lower(), "fav"}
    meta_cols = {"draftkings", "fanduel", "salary", "teetime", "tee time", "rounds", "rds+", "rds+(i)"}

    rows = []
    for _, row in df.iterrows():
        raw_name = str(row[player_col]).strip().strip('"')
        if not raw_name or raw_name.lower() == "nan":
            continue

        pkey = normalize_name(raw_name)
        pdisp = display_name(raw_name)

        if not pkey:
            continue

        # Store salary and tee time as special metrics
        for mc in ["DraftKings", "FanDuel", "Salary", "TeeTime", "Tee Time"]:
            if mc in df.columns:
                val = row.get(mc)
                numeric = _parse_numeric(val)
                if numeric is not None or (val and str(val).strip()):
                    rows.append({
                        "tournament_id": tournament_id,
                        "csv_import_id": csv_import_id,
                        "player_key": pkey,
                        "player_display": pdisp,
                        "metric_category": "meta",
                        "data_mode": data_mode,
                        "round_window": round_window,
                        "metric_name": mc.lower().replace(" ", "_"),
                        "metric_value": numeric,
                        "metric_text": str(val).strip() if numeric is None else None,
                    })

        # Store Rounds as meta
        if "Rounds" in df.columns:
            rval = _parse_numeric(row.get("Rounds"))
            if rval is not None:
                rows.append({
                    "tournament_id": tournament_id,
                    "csv_import_id": csv_import_id,
                    "player_key": pkey,
                    "player_display": pdisp,
                    "metric_category": "meta",
                    "data_mode": data_mode,
                    "round_window": round_window,
                    "metric_name": "rounds_played",
                    "metric_value": rval,
                    "metric_text": None,
                })

        # Parse all metric columns
        for col in columns:
            col_lower = col.lower().replace(" ", "").replace("_", "")
            if col == player_col:
                continue
            if col_lower in {c.lower().replace(" ", "").replace("_", "") for c in meta_cols}:
                continue
            if col_lower in skip_cols:
                continue
            if col_lower in {"draftkings", "fanduel", "salary",
                             "teetime", "tee time", "rounds", "rds+", "rds+(i)"}:
                continue

            val = row.get(col)
            numeric = _parse_numeric(val)
            text_val = _parse_finish(val) if numeric is None else None

            if numeric is not None or text_val is not None:
                rows.append({
                    "tournament_id": tournament_id,
                    "csv_import_id": csv_import_id,
                    "player_key": pkey,
                    "player_display": pdisp,
                    "metric_category": file_type,
                    "data_mode": data_mode,
                    "round_window": round_window,
                    "metric_name": col,
                    "metric_value": numeric,
                    "metric_text": text_val,
                })

    return rows


def ingest_folder(folder_path: str, tournament_id: int,
                  data_mode_override: str = None) -> dict:
    """
    Ingest all CSV files from a folder.

    Returns summary: {filename: {type, mode, window, rows}}
    """
    from src.db import log_csv_import, store_metrics

    summary = {}
    csv_files = sorted([
        f for f in os.listdir(folder_path)
        if f.lower().endswith(".csv")
    ])

    if not csv_files:
        print(f"No CSV files found in {folder_path}")
        return summary

    print(f"\nIngesting {len(csv_files)} CSV files from {folder_path}...")

    for fname in csv_files:
        fpath = os.path.join(folder_path, fname)
        print(f"\n  Parsing: {fname}")

        try:
            # Quick peek to classify
            df_peek = pd.read_csv(fpath, nrows=1, dtype=str)
            df_peek.columns = [c.strip().strip('"') for c in df_peek.columns]
            file_type = classify_file_type(list(df_peek.columns), fname)
            dm = data_mode_override or detect_data_mode(fname)
            rw = detect_round_window(fname, df_peek)

            # Log the import
            df_full = pd.read_csv(fpath, dtype=str)
            import_id = log_csv_import(
                tournament_id, fname, file_type, dm, rw, len(df_full)
            )

            # Parse and store
            metric_rows = parse_csv(fpath, tournament_id, import_id, dm, rw)
            store_metrics(metric_rows)

            summary[fname] = {
                "type": file_type,
                "mode": dm,
                "window": rw,
                "rows": len(metric_rows),
            }
            print(f"    → type={file_type}, mode={dm}, window={rw}, metrics={len(metric_rows)}")

        except Exception as e:
            print(f"    ERROR: {e}")
            summary[fname] = {"type": "error", "error": str(e)}

    total = sum(s.get("rows", 0) for s in summary.values())
    print(f"\n  Total metrics stored: {total}")
    return summary
