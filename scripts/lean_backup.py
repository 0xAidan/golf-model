#!/usr/bin/env python3
"""Nightly lean backup: every table except the history journal, plus the journal's new rows.

The history journal (``prediction_history_versions``) is append-only and makes
up most of the database file, so copying it in full every night is slow and
large. This writes two things instead:

- ``golf_lean_<timestamp>.db.gz``: a consistent copy of every other table
  (picks, outcomes, ledger, results, metrics, runs, ticks, ...), checked with
  ``integrity_check`` before it is compressed.
- ``journal_delta_<from>_<to>.jsonl.gz``: the journal rows added since the last
  run, so a full backup plus the deltas reproduces the journal.

The source database is opened read-only. Nothing is ever deleted: old lean
backups are left in place for a human or an off-box sync to rotate.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

JOURNAL_TABLE = "prediction_history_versions"
MIB = 1024 * 1024


class LeanBackupError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(MIB), b""):
            digest.update(block)
    return digest.hexdigest()


def _gzip_file(source: Path, destination: Path) -> None:
    with open(source, "rb") as raw, open(destination, "wb") as out:
        with gzip.GzipFile(filename="", mode="wb", fileobj=out, compresslevel=6, mtime=0) as packed:
            shutil.copyfileobj(raw, packed, MIB)


def copy_tables(source: Path, target: Path, exclude: set[str]) -> dict:
    """Copy every table not in ``exclude`` from one consistent read of the source."""
    conn = sqlite3.connect(target, uri=False, isolation_level=None)
    try:
        conn.execute(f"ATTACH DATABASE '{source.resolve().as_uri()}?mode=ro' AS src")
        conn.execute("BEGIN")  # one read transaction on src: every table comes from the same moment
        tables = conn.execute(
            "SELECT name, sql FROM src.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        counts: dict[str, int] = {}
        for name, sql in tables:
            if name in exclude or not sql:
                continue
            conn.execute(sql)
            conn.execute(f'INSERT INTO main."{name}" SELECT * FROM src."{name}"')
            counts[name] = conn.execute(f'SELECT COUNT(*) FROM main."{name}"').fetchone()[0]
        # Keep index, trigger and view definitions so a restore can rebuild them without the app.
        conn.execute("CREATE TABLE _lean_backup_schema (type TEXT, name TEXT, tbl_name TEXT, sql TEXT)")
        conn.execute(
            """INSERT INTO _lean_backup_schema
               SELECT type, name, tbl_name, sql FROM src.sqlite_master
               WHERE type IN ('index','trigger','view') AND sql IS NOT NULL"""
        )
        journal_max = None
        if conn.execute("SELECT 1 FROM src.sqlite_master WHERE type='table' AND name=?", (JOURNAL_TABLE,)).fetchone():
            journal_max = conn.execute(f"SELECT MAX(id) FROM src.{JOURNAL_TABLE}").fetchone()[0]
        conn.execute("COMMIT")
        conn.execute("DETACH DATABASE src")
        check = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise LeanBackupError(f"lean copy failed integrity_check: {check}")
        return {"table_counts": counts, "journal_max_id": journal_max, "excluded": sorted(exclude)}
    finally:
        conn.close()


def export_journal_delta(source: Path, output_dir: Path, after_id: int, up_to_id: int | None) -> dict | None:
    """Write journal rows with after_id < id <= up_to_id as gzipped JSON lines."""
    if up_to_id is None or up_to_id <= after_id:
        return None
    conn = sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True, timeout=30)
    try:
        cursor = conn.execute(
            f"SELECT * FROM {JOURNAL_TABLE} WHERE id > ? AND id <= ? ORDER BY id", (after_id, up_to_id))
        columns = [column[0] for column in cursor.description]
        target = output_dir / f"journal_delta_{after_id + 1}_{up_to_id}.jsonl.gz"
        partial = target.with_suffix(".partial")
        rows = 0
        with gzip.open(partial, "wt", encoding="utf-8") as handle:
            for row in cursor:
                handle.write(json.dumps(dict(zip(columns, row)), separators=(",", ":")) + "\n")
                rows += 1
        os.replace(partial, target)
        return {"file": target.name, "rows": rows, "from_id": after_id + 1, "to_id": up_to_id,
                "sha256": _sha256(target), "bytes": target.stat().st_size}
    finally:
        conn.close()


def run(source: Path, output_dir: Path, *, min_free_mib: int = 5120, journal_base_id: int | None = None) -> dict:
    started = time.monotonic()
    if not source.is_file():
        raise LeanBackupError(f"source database not found: {source}")
    output_dir.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(output_dir).free
    if free < min_free_mib * MIB:
        raise LeanBackupError(f"refused: {free // MIB} MiB free is under the {min_free_mib} MiB floor")

    state_path = output_dir / "journal_state.json"
    state = json.loads(state_path.read_text()) if state_path.is_file() else {}
    last_id = state.get("last_exported_id")
    if last_id is None:
        if journal_base_id is None:
            raise LeanBackupError(
                "first run needs --journal-base-id: the highest journal id already held in a full backup")
        last_id = int(journal_base_id)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    with tempfile.TemporaryDirectory(prefix="golf_lean_", dir=output_dir) as work:
        raw_copy = Path(work) / "lean.db"
        info = copy_tables(source, raw_copy, {JOURNAL_TABLE})
        raw_bytes, raw_sha = raw_copy.stat().st_size, _sha256(raw_copy)
        final = output_dir / f"golf_lean_{stamp}.db.gz"
        partial = final.with_suffix(".partial")
        _gzip_file(raw_copy, partial)
        with gzip.open(partial, "rb") as packed:
            digest = hashlib.sha256()
            for block in iter(lambda: packed.read(MIB), b""):
                digest.update(block)
        if digest.hexdigest() != raw_sha:
            partial.unlink(missing_ok=True)
            raise LeanBackupError("compressed copy does not hash back to the verified copy")
        os.replace(partial, final)

    delta = export_journal_delta(source, output_dir, last_id, info["journal_max_id"])
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(source), "archive": final.name,
        "archive_bytes": final.stat().st_size, "archive_sha256": _sha256(final),
        "raw_bytes": raw_bytes, "raw_sha256": raw_sha, "integrity_check": "ok",
        "excluded_tables": info["excluded"], "table_counts": info["table_counts"],
        "journal_max_id_at_backup": info["journal_max_id"], "journal_delta": delta,
        "journal_covered_through_id": info["journal_max_id"] if delta else last_id,
        "restore": "gunzip the archive and open it with sqlite3; index definitions are in _lean_backup_schema; "
                   "the journal comes from the last full backup plus every journal_delta file",
        "elapsed_seconds": round(time.monotonic() - started, 1),
    }
    (output_dir / f"{final.name}.manifest.json").write_text(json.dumps(manifest, indent=1))
    if delta:
        state_path.write_text(json.dumps({"last_exported_id": delta["to_id"], "updated_at": manifest["created_at_utc"]}))
    elif not state_path.is_file():
        state_path.write_text(json.dumps({"last_exported_id": last_id, "updated_at": manifest["created_at_utc"]}))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=Path("/opt/golf-model/data/golf.db"))
    parser.add_argument("--output-dir", type=Path, default=Path("/opt/golf-model/backups/lean"))
    parser.add_argument("--min-free-mib", type=int, default=5120)
    parser.add_argument("--journal-base-id", type=int, default=None,
                        help="first run only: highest journal id already in a full backup")
    args = parser.parse_args()
    try:
        manifest = run(args.source, args.output_dir, min_free_mib=args.min_free_mib,
                       journal_base_id=args.journal_base_id)
    except LeanBackupError as exc:
        print(f"lean backup failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({k: manifest[k] for k in (
        "archive", "archive_bytes", "raw_bytes", "integrity_check", "journal_max_id_at_backup",
        "journal_delta", "elapsed_seconds")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
