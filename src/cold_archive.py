"""Cold archive export and verification for prunable tick tables."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
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

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = _exports_root(output_dir) / f"tick_archive_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    table_meta: dict[str, dict[str, Any]] = {}
    try:
        for table in sorted(PRUNABLE_TICK_TABLES):
            rows = conn.execute(
                f"""
                SELECT * FROM {table}
                WHERE {_TS_COLUMN} IS NOT NULL AND {_TS_COLUMN} < ?
                """,
                (cutoff_utc,),
            ).fetchall()
            out_path = out_dir / f"{table}.jsonl"
            with open(out_path, "w", encoding="utf-8") as fh:
                for row in rows:
                    fh.write(json.dumps(dict(row), default=str) + "\n")
            checksum = _sha256_file(str(out_path))
            table_meta[table] = {
                "rows": len(rows),
                "file": out_path.name,
                "sha256": checksum,
            }
    finally:
        conn.close()

    created_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "archive_type": "tick_tables",
        "created_at": created_at,
        "db_path": db_path,
        "time_window": {
            "before_utc": cutoff_utc,
            "retain_days": retain_days,
        },
        "tables": table_meta,
    }
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    manifest["checksum"] = hashlib.sha256(manifest_bytes).hexdigest()
    manifest_path = out_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as fh:
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

    if manifest.get("archive_type") != "tick_tables":
        return False

    tables = manifest.get("tables") or {}
    if not PRUNABLE_TICK_TABLES.issubset(set(tables)):
        return False

    export_dir = manifest_path.parent
    for table, meta in tables.items():
        rel = meta.get("file")
        expected = meta.get("sha256")
        if not rel or not expected:
            return False
        file_path = export_dir / rel
        if not file_path.is_file():
            return False
        if _sha256_file(str(file_path)) != expected:
            return False
    return True


def verified_archive_exists_for_cutoff(
    cutoff_utc: str,
    *,
    exports_dir: str | os.PathLike[str] | None = None,
) -> bool:
    """Return True when a checksum-valid manifest covers ``before_utc == cutoff_utc``."""
    root = _exports_root(exports_dir)
    if not root.is_dir():
        return False

    target = str(cutoff_utc)
    for manifest_path in sorted(root.glob("tick_archive_*/manifest.json"), reverse=True):
        try:
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        window = manifest.get("time_window") or {}
        before = str(window.get("before_utc") or "")
        if before != target:
            continue
        if _manifest_is_valid(manifest_path):
            return True
    return False


def list_archive_stats(exports_dir: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Summarize cold archives under ``data/exports/`` for data-health."""
    root = _exports_root(exports_dir)
    archives: list[dict[str, Any]] = []
    if root.is_dir():
        for manifest_path in sorted(root.glob("tick_archive_*/manifest.json"), reverse=True):
            try:
                with open(manifest_path, encoding="utf-8") as fh:
                    manifest = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            valid = _manifest_is_valid(manifest_path)
            tables = manifest.get("tables") or {}
            archives.append({
                "path": str(manifest_path.parent),
                "created_at": manifest.get("created_at"),
                "before_utc": (manifest.get("time_window") or {}).get("before_utc"),
                "valid": valid,
                "row_counts": {k: int((tables.get(k) or {}).get("rows", 0)) for k in PRUNABLE_TICK_TABLES},
            })

    return {
        "exports_dir": str(root),
        "archive_count": len(archives),
        "latest": archives[0] if archives else None,
        "archives": archives[:10],
    }
