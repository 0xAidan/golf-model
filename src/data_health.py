"""Read-only data platform health audit (coverage, storage, gaps)."""

from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backtester.autoresearch_data_health import validate_autoresearch_data_health

_REPO_ROOT = Path(__file__).resolve().parents[1]
_OUTPUT_DIR = _REPO_ROOT / "output"

# Retention classifications (exposed in data-health API).
KEEP_FOREVER = frozenset({
    "picks",
    "pick_outcomes",
    "prediction_log",
    "results",
    "tournaments",
    "runs",
    "rounds",
    "metrics",
    "weight_sets",
    "calibration_curve",
    "market_performance",
})

ARCHIVE_THEN_PRUNE = frozenset({
    "live_snapshot_history",
    "market_prediction_rows",
})

SLIM = frozenset({
    "market_prediction_rows",
})

INVESTIGATE = frozenset({
    "ai_decisions",
    "intel_events",
    "shadow_event_simulations",
    "challenger_predictions",
})

# Back-compat aliases used internally.
_RETAIN_FOREVER = KEEP_FOREVER
_PRUNABLE_TICK_TABLES = ARCHIVE_THEN_PRUNE

# Rough bytes-per-row estimates when dbstat is skipped (large DBs).
_ESTIMATED_BYTES_PER_ROW: dict[str, int] = {
    "market_prediction_rows": 2048,
    "live_snapshot_history": 8192,
    "picks": 512,
    "pick_outcomes": 256,
    "prediction_log": 1024,
    "rounds": 256,
    "metrics": 128,
    "challenger_predictions": 1024,
    "ai_decisions": 512,
    "intel_events": 512,
    "shadow_event_simulations": 4096,
}


def _db_file_sizes(db_path: str) -> dict[str, int | None]:
    paths = {
        "main": db_path,
        "wal": db_path + "-wal",
        "shm": db_path + "-shm",
    }
    out: dict[str, int | None] = {}
    for key, p in paths.items():
        try:
            out[key] = os.path.getsize(p) if os.path.exists(p) else None
        except OSError:
            out[key] = None
    return out


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _safe_count(conn: sqlite3.Connection, table: str, where: str = "", params: tuple = ()) -> int:
    if not _table_exists(conn, table):
        return 0
    sql = f"SELECT COUNT(*) AS c FROM {table}"
    if where:
        sql += f" WHERE {where}"
    return int(conn.execute(sql, params).fetchone()["c"])


def _table_byte_stats(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    """Per-table page bytes via dbstat (SQLite 3.16+)."""
    try:
        rows = conn.execute(
            """
            SELECT name AS table_name, SUM(pgsize) AS bytes
            FROM dbstat
            GROUP BY name
            ORDER BY bytes DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    total = sum(int(r["bytes"] or 0) for r in rows)
    result = []
    for r in rows:
        b = int(r["bytes"] or 0)
        result.append({
            "table": r["table_name"],
            "bytes": b,
            "mb": round(b / (1024 * 1024), 2),
            "pct_of_top": round(100.0 * b / total, 1) if total else 0.0,
            "approximate": False,
        })
    return result


def _approximate_table_stats(
    conn: sqlite3.Connection,
    row_counts: dict[str, int],
    main_bytes: int,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Fallback sizing when dbstat is too slow on multi-GB databases."""
    page_count = int(conn.execute("PRAGMA page_count").fetchone()[0] or 0)
    page_size = int(conn.execute("PRAGMA page_size").fetchone()[0] or 4096)
    db_bytes = page_count * page_size if page_count > 0 else main_bytes

    tables = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()]
    estimates: list[tuple[str, int]] = []
    for table in tables:
        count = int(row_counts.get(table, _safe_count(conn, table)))
        per_row = _ESTIMATED_BYTES_PER_ROW.get(table, 256)
        estimates.append((table, max(count * per_row, 0)))

    total_est = sum(b for _, b in estimates) or 1
    scale = db_bytes / total_est if total_est > 0 else 1.0

    result: list[dict[str, Any]] = []
    for table, raw_bytes in sorted(estimates, key=lambda item: item[1], reverse=True)[:limit]:
        b = int(raw_bytes * scale)
        result.append({
            "table": table,
            "bytes": b,
            "mb": round(b / (1024 * 1024), 2),
            "pct_of_top": round(100.0 * b / (db_bytes or 1), 1),
            "approximate": True,
        })
    return result


def _latest_backup_info(backup_dir: str | None = None) -> dict[str, Any] | None:
    path = find_latest_backup(backup_dir)
    if not path:
        return None
    try:
        size_bytes = os.path.getsize(path)
        mtime = os.path.getmtime(path)
    except OSError:
        return {"path": path, "ok": False, "error": "cannot stat backup file"}

    from src.backup import verify_backup_integrity

    integrity = verify_backup_integrity(path)
    return {
        "path": path,
        "name": os.path.basename(path),
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024 * 1024), 2),
        "created": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
        "integrity": integrity,
    }


def _monthly_counts(
    conn: sqlite3.Connection,
    *,
    year: int,
    table: str,
    ts_col: str,
) -> dict[str, int]:
    if not _table_exists(conn, table):
        return {}
    try:
        rows = conn.execute(
            f"""
            SELECT strftime('%Y-%m', {ts_col}) AS mo, COUNT(*) AS c
            FROM {table}
            WHERE {ts_col} IS NOT NULL
              AND CAST(strftime('%Y', {ts_col}) AS INTEGER) = ?
            GROUP BY mo
            ORDER BY mo
            """,
            (year,),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {str(r["mo"]): int(r["c"]) for r in rows if r["mo"]}


def _output_card_events() -> list[dict[str, str]]:
    """Parse committed output/*.md card filenames (not archive)."""
    events: list[dict[str, str]] = []
    if not _OUTPUT_DIR.is_dir():
        return events
    pat = re.compile(r"^(.+)_(\d{8})\.md$")
    for path in sorted(_OUTPUT_DIR.glob("*.md")):
        if "methodology" in path.name:
            continue
        m = pat.match(path.name)
        if not m:
            continue
        stem, ymd = m.group(1), m.group(2)
        events.append({
            "slug": stem,
            "date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}",
            "path": str(path.relative_to(_REPO_ROOT)),
        })
    return events


def _gaps_output_vs_db(conn: sqlite3.Connection, year: int) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    for card in _output_card_events():
        if not card["date"].startswith(str(year)):
            continue
        slug = card["slug"].replace("_", " ")
        row = conn.execute(
            """
            SELECT id, name FROM tournaments
            WHERE year = ?
              AND (
                lower(replace(replace(name, '''', ''), ' ', '_')) LIKE ?
                OR lower(name) LIKE ?
              )
            LIMIT 1
            """,
            (year, f"%{card['slug'][:24]}%", f"%{slug[:32]}%"),
        ).fetchone()
        if not row:
            gaps.append({
                "type": "card_without_tournament",
                "detail": f"output card {card['path']} has no matching tournaments row",
            })
            continue
        tid = int(row["id"])
        pick_n = _safe_count(conn, "picks", "tournament_id = ?", (tid,))
        if pick_n == 0:
            gaps.append({
                "type": "card_without_picks",
                "detail": f"{card['path']} → tournament {row['name']} (id={tid}) has 0 picks",
            })
    return gaps


def build_data_health_report(
    *,
    db_path: str | None = None,
    year: int = 2026,
) -> dict[str, Any]:
    """Full audit payload for API, CLI, and dashboard."""
    from src import db

    path = db_path or db.DB_PATH
    if not os.path.isfile(path):
        return {
            "ok": False,
            "error": f"Database not found: {path}",
            "db_path": path,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    sizes = _db_file_sizes(path)
    main_bytes = sizes.get("main") or 0

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=120.0)
    conn.row_factory = sqlite3.Row
    try:
        storage_warnings: list[str] = []
        # dbstat walks every page — prohibitively slow on multi-GB production DBs.
        use_dbstat = main_bytes < 2 * 1024 ** 3
        table_stats: list[dict[str, Any]] = []
        table_stats_mode = "dbstat"
        if main_bytes > 5 * 1024 ** 3:
            storage_warnings.append(
                f"Database file is {main_bytes / (1024**3):.1f} GB — run prune + VACUUM; "
                "see docs/storage-retention.md."
            )
        wal_bytes = sizes.get("wal")
        if wal_bytes and wal_bytes > 500 * 1024 ** 2:
            storage_warnings.append(
                f"WAL file is {wal_bytes / (1024**2):.0f} MB — consider checkpoint after maintenance."
            )

        months = [f"{year}-{m:02d}" for m in range(1, 13)]
        monthly: dict[str, dict[str, int]] = {}
        for mo in months:
            monthly[mo] = {
                "tournaments": 0,
                "runs": 0,
                "picks": 0,
                "pick_outcomes": 0,
                "prediction_log": 0,
                "market_prediction_rows": 0,
            }

        for mo, c in _monthly_counts(
            conn, year=year, table="tournaments", ts_col="COALESCE(date, created_at)"
        ).items():
            if mo in monthly:
                monthly[mo]["tournaments"] = c
        for mo, c in _monthly_counts(conn, year=year, table="runs", ts_col="created_at").items():
            if mo in monthly:
                monthly[mo]["runs"] = c
        for mo, c in _monthly_counts(conn, year=year, table="picks", ts_col="created_at").items():
            if mo in monthly:
                monthly[mo]["picks"] = c
        for mo, c in _monthly_counts(
            conn, year=year, table="pick_outcomes", ts_col="entered_at"
        ).items():
            if mo in monthly:
                monthly[mo]["pick_outcomes"] = c
        for mo, c in _monthly_counts(
            conn, year=year, table="prediction_log", ts_col="created_at"
        ).items():
            if mo in monthly:
                monthly[mo]["prediction_log"] = c
        for mo, c in _monthly_counts(
            conn, year=year, table="market_prediction_rows", ts_col="generated_at"
        ).items():
            if mo in monthly:
                monthly[mo]["market_prediction_rows"] = c

        row_counts = {
            "rounds": _safe_count(conn, "rounds"),
            "metrics": _safe_count(conn, "metrics"),
            "market_prediction_rows": _safe_count(conn, "market_prediction_rows"),
            "live_snapshot_history": _safe_count(conn, "live_snapshot_history"),
            "picks": _safe_count(conn, "picks"),
            "prediction_log": _safe_count(conn, "prediction_log"),
            "challenger_predictions": _safe_count(conn, "challenger_predictions"),
        }

        if use_dbstat:
            table_stats = _table_byte_stats(conn, limit=25)
        else:
            table_stats = _approximate_table_stats(conn, row_counts, main_bytes, limit=25)
            table_stats_mode = "approximate"
            storage_warnings.append(
                "Table sizes are approximate (database >2GB; dbstat skipped). "
                "Estimates use row counts and page_count."
            )

        top_table = table_stats[0]["table"] if table_stats else None
        top_pct = table_stats[0]["pct_of_top"] if table_stats else 0.0
        if top_table in _PRUNABLE_TICK_TABLES and top_pct >= 25:
            storage_warnings.append(
                f"Table '{top_table}' dominates storage (~{top_pct}% of measured pages)."
            )

        gaps = _gaps_output_vs_db(conn, year)
        autoresearch = validate_autoresearch_data_health(years=[year])

        # Live picks coverage for autoresearch complement
        tournaments_with_picks = conn.execute(
            """
            SELECT COUNT(DISTINCT tournament_id) FROM picks
            WHERE tournament_id IN (SELECT id FROM tournaments WHERE year = ?)
            """,
            (year,),
        ).fetchone()[0]
        tournaments_total = _safe_count(conn, "tournaments", "year = ?", (year,))
        live_picks_ok = int(tournaments_with_picks) >= max(1, tournaments_total // 2)
        if tournaments_total and not live_picks_ok:
            autoresearch.setdefault("warnings", []).append(
                f"Only {tournaments_with_picks}/{tournaments_total} tournaments in {year} have picks rows."
            )

        status = "green"
        if storage_warnings or gaps or not autoresearch.get("ok"):
            status = "yellow"
        if main_bytes > 10 * 1024 ** 3 or (top_table in _PRUNABLE_TICK_TABLES and top_pct > 50):
            status = "red"

        summary_lines = []
        if main_bytes:
            summary_lines.append(f"Database size: {main_bytes / (1024**3):.2f} GB on disk.")
        if top_table:
            summary_lines.append(f"Largest table: {top_table} ({table_stats[0]['mb']} MB in dbstat sample).")
        summary_lines.append(
            f"{year}: {tournaments_total} tournaments, {row_counts['picks']} total picks logged."
        )
        if gaps:
            summary_lines.append(f"{len(gaps)} gap(s) between output/ cards and database rows.")
        if storage_warnings:
            summary_lines.append(storage_warnings[0])

        from src.cold_archive import list_archive_stats

        latest_backup = _latest_backup_info()
        archive_stats = list_archive_stats()
        slim_payload = (os.environ.get("MARKET_PREDICTION_SLIM_PAYLOAD") or "").strip().lower() in {
            "1", "true", "yes", "on",
        }

        return {
            "ok": status != "red",
            "status": status,
            "summary": " ".join(summary_lines),
            "db_path": path,
            "file_sizes_bytes": sizes,
            "file_sizes_human": {
                k: f"{v / (1024**3):.2f} GB" if v and v > 1024**3 else (
                    f"{v / (1024**2):.1f} MB" if v and v > 1024**2 else (
                        f"{v / 1024:.1f} KB" if v else "missing"
                    )
                )
                for k, v in sizes.items()
            },
            "table_byte_stats": table_stats,
            "table_byte_stats_mode": table_stats_mode,
            "row_counts": row_counts,
            "retention_policy": {
                "retain_forever": sorted(_RETAIN_FOREVER),
                "prunable_tick_tables": sorted(_PRUNABLE_TICK_TABLES),
                "snapshot_retain_days": int(
                    os.environ.get("SNAPSHOT_HISTORY_RETAIN_DAYS", "210")
                ),
                "prune_require_archive": (
                    os.environ.get("SNAPSHOT_PRUNE_REQUIRE_ARCHIVE", "1").strip().lower()
                    not in {"0", "false", "no", "off"}
                ),
                "slim_market_payload_enabled": slim_payload,
            },
            "retention_classifications": {
                "KEEP_FOREVER": sorted(KEEP_FOREVER),
                "ARCHIVE_THEN_PRUNE": sorted(ARCHIVE_THEN_PRUNE),
                "SLIM": sorted(SLIM),
                "INVESTIGATE": sorted(INVESTIGATE),
            },
            "latest_backup": latest_backup,
            "archive_stats": archive_stats,
            "monthly_coverage": monthly,
            "gaps": gaps,
            "autoresearch_data_health": autoresearch,
            "live_picks_coverage": {
                "year": year,
                "tournaments_with_picks": int(tournaments_with_picks),
                "tournaments_total": tournaments_total,
                "ok": live_picks_ok,
            },
            "storage_warnings": storage_warnings,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        conn.close()


def find_latest_backup(backup_dir: str | None = None) -> str | None:
    root = backup_dir or str(_REPO_ROOT / "backups")
    patterns = [
        os.path.join(root, "golf_model_*.db"),
        os.path.join(root, "golf_model_*.db.gz"),
    ]
    paths: list[str] = []
    for pat in patterns:
        paths.extend(glob.glob(pat))
    if not paths:
        return None
    return max(paths, key=os.path.getmtime)
