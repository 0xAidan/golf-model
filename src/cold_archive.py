"""Cold archive export and verification for prunable tick tables."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPORTS_DIR = _REPO_ROOT / "data" / "exports"

PRUNABLE_TICK_TABLES = frozenset({
    "live_snapshot_history",
    "market_prediction_rows",
})

_TS_COLUMN = "generated_at"
ARCHIVE_SCHEMA_VERSION = 2


def open_readonly_database(db_path: str) -> sqlite3.Connection:
    """Read the existing database, including its WAL, without initialization."""
    path = Path(db_path).resolve()
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _database_identity(db_path: str) -> dict[str, Any]:
    path = Path(db_path).resolve()
    stat = path.stat()
    return {"realpath": str(path), "device": stat.st_dev, "inode": stat.st_ino}


def _canonical_line(row: dict[str, Any]) -> bytes:
    return (json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str, allow_nan=False) + "\n").encode("utf-8")


def _table_rows(conn: sqlite3.Connection, table: str, cutoff: str):
    if table not in PRUNABLE_TICK_TABLES:
        raise ValueError("Unsupported history table")
    return conn.execute(
        f"SELECT * FROM {table} WHERE {_TS_COLUMN} IS NOT NULL AND {_TS_COLUMN} < ? ORDER BY rowid",
        (cutoff,),
    )


def _current_rowset(conn: sqlite3.Connection, table: str, cutoff: str) -> tuple[int, str]:
    digest, count = hashlib.sha256(), 0
    for row in _table_rows(conn, table, cutoff):
        digest.update(_canonical_line(dict(row)))
        count += 1
    return count, digest.hexdigest()


def snapshot_history_cutoff_utc(retain_days: int) -> str:
    """ISO cutoff shared by export and prune (rows with ``generated_at`` < cutoff are eligible)."""
    from datetime import timedelta

    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=int(retain_days))
    return cutoff_dt.replace(microsecond=0).isoformat()


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _exports_root(exports_dir: str | os.PathLike[str] | None = None) -> Path:
    return Path(exports_dir) if exports_dir else DEFAULT_EXPORTS_DIR


def export_tick_tables_before_cutoff(
    *,
    db_path: str,
    cutoff_utc: str,
    output_dir: str | os.PathLike[str] | None = None,
    retain_days: int | None = None,
) -> dict[str, Any]:
    """Export rows with ``generated_at`` strictly before ``cutoff_utc`` to JSONL + manifest."""
    if not os.path.isfile(db_path):
        raise FileNotFoundError(f"Database not found: {db_path}")

    source_identity = _database_identity(db_path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f") + "_" + uuid.uuid4().hex[:8]
    out_dir = _exports_root(output_dir) / f"tick_archive_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=False)

    conn = open_readonly_database(db_path)
    table_meta: dict[str, dict[str, Any]] = {}
    try:
        conn.execute("BEGIN")
        for table in sorted(PRUNABLE_TICK_TABLES):
            out_path = out_dir / f"{table}.jsonl"
            count = 0
            with open(out_path, "xb") as fh:
                for row in _table_rows(conn, table, cutoff_utc):
                    fh.write(_canonical_line(dict(row)))
                    count += 1
            checksum = _sha256_file(str(out_path))
            table_meta[table] = {
                "rows": count,
                "file": out_path.name,
                "sha256": checksum,
            }
        if _database_identity(db_path) != source_identity:
            raise RuntimeError("Source database identity changed during archive export")
    finally:
        conn.close()

    created_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "archive_type": "tick_tables",
        "created_at": created_at,
        "db_path": db_path,
        "source_identity": source_identity,
        "row_encoding": "canonical_json_sorted_keys_utf8_v1",
        "time_window": {
            "before_utc": cutoff_utc,
            "retain_days": retain_days,
        },
        "tables": table_meta,
    }
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    manifest["checksum"] = hashlib.sha256(manifest_bytes).hexdigest()
    manifest_path = out_dir / "manifest.json"
    with open(manifest_path, "x", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)

    return {
        "ok": True,
        "export_dir": str(out_dir),
        "manifest_path": str(manifest_path),
        "cutoff_utc": cutoff_utc,
        "tables": {k: v["rows"] for k, v in table_meta.items()},
    }


def _manifest_is_valid(manifest_path: Path) -> bool:
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return False

    if not isinstance(manifest, dict) or manifest.get("archive_type") != "tick_tables":
        return False
    expected_manifest_checksum = manifest.get("checksum")
    unsigned = {key: value for key, value in manifest.items() if key != "checksum"}
    actual_manifest_checksum = hashlib.sha256(json.dumps(unsigned, indent=2, sort_keys=True).encode("utf-8")).hexdigest()
    if expected_manifest_checksum != actual_manifest_checksum:
        return False

    tables = manifest.get("tables") or {}
    if not isinstance(tables, dict) or set(tables) != PRUNABLE_TICK_TABLES:
        return False

    export_dir = manifest_path.parent
    for table, meta in tables.items():
        if not isinstance(meta, dict):
            return False
        rel = meta.get("file")
        expected = meta.get("sha256")
        if rel != f"{table}.jsonl" or not expected:
            return False
        file_path = export_dir / rel
        if not file_path.is_file():
            return False
        try:
            if _sha256_file(str(file_path)) != expected:
                return False
            count = 0
            with file_path.open(encoding="utf-8") as handle:
                for line in handle:
                    if not isinstance(json.loads(line), dict):
                        return False
                    count += 1
            if type(meta.get("rows")) is not int or meta["rows"] != count:
                return False
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False
    return True


def _parse_cutoff_utc(value: str) -> datetime | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _manifest_covers_cutoff(manifest_before_utc: str, cutoff_utc: str) -> bool:
    """Return True when archive window starts at or after the prune cutoff (covering semantics)."""
    manifest_dt = _parse_cutoff_utc(manifest_before_utc)
    cutoff_dt = _parse_cutoff_utc(cutoff_utc)
    if manifest_dt is None or cutoff_dt is None:
        return str(manifest_before_utc) == str(cutoff_utc)
    if manifest_dt.tzinfo is None:
        manifest_dt = manifest_dt.replace(tzinfo=timezone.utc)
    if cutoff_dt.tzinfo is None:
        cutoff_dt = cutoff_dt.replace(tzinfo=timezone.utc)
    return manifest_dt >= cutoff_dt


def verified_archive_exists_for_cutoff(
    cutoff_utc: str,
    *,
    exports_dir: str | os.PathLike[str] | None = None,
    db_path: str | None = None,
    connection: sqlite3.Connection | None = None,
    tables: frozenset[str] | None = None,
) -> bool:
    """Require this database's exact current deletion rowset in a valid archive.

    A path/cutoff/checksum alone cannot authorize deletion. Callers that delete
    must pass their existing BEGIN IMMEDIATE connection so backfills cannot race
    between verification and DELETE. Old manifests remain reportable but cannot
    authorize pruning without this source/rowset proof.
    """
    requested = PRUNABLE_TICK_TABLES if tables is None else tables
    if not db_path or not requested or not set(requested).issubset(PRUNABLE_TICK_TABLES):
        return False
    root = _exports_root(exports_dir)
    if not root.is_dir():
        return False

    conn = connection
    owns_connection = conn is None
    try:
        identity = _database_identity(db_path)
        conn = conn or open_readonly_database(db_path)
        actual_path = conn.execute("PRAGMA database_list").fetchone()[2]
        if Path(actual_path).resolve() != Path(db_path).resolve():
            return False
        if owns_connection:
            conn.execute("BEGIN")
        current = {table: _current_rowset(conn, table, cutoff_utc) for table in requested}
        for manifest_path in sorted(root.glob("tick_archive_*/manifest.json"), reverse=True):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if not isinstance(manifest, dict) or manifest.get("schema_version") != ARCHIVE_SCHEMA_VERSION:
                    continue
                if manifest.get("source_identity") != identity:
                    continue
                if manifest.get("row_encoding") != "canonical_json_sorted_keys_utf8_v1":
                    continue
                window = manifest.get("time_window")
                if not isinstance(window, dict):
                    continue
                before = window.get("before_utc")
                if not isinstance(before, str):
                    continue
                if not _manifest_covers_cutoff(before, cutoff_utc) or not _manifest_is_valid(manifest_path):
                    continue
                matches = True
                for table in requested:
                    digest, count = hashlib.sha256(), 0
                    with (manifest_path.parent / f"{table}.jsonl").open(encoding="utf-8") as handle:
                        for line in handle:
                            row = json.loads(line)
                            timestamp = row.get(_TS_COLUMN)
                            if timestamp is not None and str(timestamp) < cutoff_utc:
                                digest.update(_canonical_line(row))
                                count += 1
                    if (count, digest.hexdigest()) != current[table]:
                        matches = False
                        break
                if matches:
                    return True
            except (OSError, ValueError, TypeError, UnicodeError):
                continue
        return False
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return False
    finally:
        if owns_connection and conn is not None:
            conn.close()


def list_archive_stats(exports_dir: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Summarize archives, including invalid evidence, without trusting metadata."""
    root = _exports_root(exports_dir)
    archives: list[dict[str, Any]] = []
    if root.is_dir():
        for manifest_path in sorted(root.glob("tick_archive_*/manifest.json"), reverse=True):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if not isinstance(manifest, dict):
                continue
            valid = _manifest_is_valid(manifest_path)
            tables = manifest.get("tables")
            tables = tables if isinstance(tables, dict) else {}
            window = manifest.get("time_window")
            window = window if isinstance(window, dict) else {}
            counts = {}
            for table in sorted(PRUNABLE_TICK_TABLES):
                meta = tables.get(table)
                count = meta.get("rows") if isinstance(meta, dict) else None
                counts[table] = count if type(count) is int and count >= 0 else 0
            archives.append({
                "path": str(manifest_path.parent),
                "created_at": manifest.get("created_at"),
                "before_utc": window.get("before_utc"),
                "valid": valid,
                "row_counts": counts,
            })
    return {
        "exports_dir": str(root), "archive_count": len(archives),
        "latest": archives[0] if archives else None, "archives": archives[:10],
    }
