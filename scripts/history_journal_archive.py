#!/usr/bin/env python3
"""Move old rows of the history journal out of golf.db into compressed archive files.

``prediction_history_versions`` is append-only and was 11.6 GB of a 12.5 GB
database (old before-images of ``metrics`` rows). Nothing here throws history
away: rows leave the live database only after the archive that holds them has
been re-read and matched row for row.

Archive layout (one directory, e.g. data/history_archive/prediction_history_versions):

  phv_<first id>_<last id>.jsonl.zst          one JSON object per row, id order
  phv_<first id>_<last id>.manifest.json      counts, id range, dates, digests

Each JSON line holds every column exactly as stored (``payload_json`` is kept as
the original string, so its bytes and hash are unchanged).

The digest is a sha256 over, per row in id order:
  id, source_table, source_row_id, payload_sha256, reason, preserved_at,
  sha256(payload_json as stored)
joined by tabs, one line per row. The same digest computed from the database
and from the archive file proves they hold identical rows.

Commands:
  export   write rows (after the last archived id, up to --through-id or
           --older-than-days) to a new archive file + manifest
  verify   re-read archive files, recheck every payload hash, and (with --db)
           compare digests against the database rows in the same id range
  prune    delete from the database only the id ranges of archives that verify
           against it right now; then reclaim space with incremental_vacuum
  restore  insert archived rows back into a database (INSERT OR IGNORE)
  cycle    export + verify + prune (used by the monthly timer)

Restoring everything into a scratch database:
  python3 scripts/history_journal_archive.py restore \
      --archive data/history_archive/prediction_history_versions --db /path/restored.db
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Iterator

TABLE = "prediction_history_versions"
COLUMNS = ("id", "source_table", "source_row_id", "payload_sha256", "payload_json", "reason", "preserved_at")
TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_table TEXT NOT NULL,
    source_row_id TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    preserved_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE(source_table, source_row_id, payload_sha256)
)"""
DEFAULT_ARCHIVE = Path(__file__).resolve().parents[1] / "data" / "history_archive" / TABLE
ZSTD_LEVEL = "12"


class ArchiveError(RuntimeError):
    pass


def _ro(db: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=60)
    conn.execute("PRAGMA query_only=1")
    return conn


def _digest_line(row: tuple) -> bytes:
    rid, st, srid, psha, payload, reason, at = row
    actual = hashlib.sha256(payload.encode()).hexdigest()
    return f"{rid}\t{st}\t{srid}\t{psha}\t{reason}\t{at}\t{actual}\n".encode()


def _db_rows(conn: sqlite3.Connection, first_id: int, last_id: int) -> Iterator[tuple]:
    cur = conn.execute(
        f"SELECT {', '.join(COLUMNS)} FROM {TABLE} WHERE id BETWEEN ? AND ? ORDER BY id",
        (first_id, last_id),
    )
    while True:
        batch = cur.fetchmany(5000)
        if not batch:
            return
        yield from batch


def _file_rows(path: Path) -> Iterator[tuple]:
    proc = subprocess.Popen(["zstd", "-dc", "--long=27", str(path)], stdout=subprocess.PIPE)
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            obj = json.loads(line)
            yield tuple(obj[c] for c in COLUMNS)
    finally:
        proc.stdout.close()
        if proc.wait() != 0:
            raise ArchiveError(f"zstd failed reading {path}")


def _manifests(archive: Path) -> list[dict]:
    out = []
    for m in sorted(archive.glob("phv_*.manifest.json")):
        data = json.loads(m.read_text())
        data["_manifest_path"] = str(m)
        out.append(data)
    out.sort(key=lambda d: d["first_id"])
    return out


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_through_id(db: str, *, through_id: int | None, older_than_days: int | None) -> int | None:
    conn = _ro(db)
    try:
        if through_id is not None:
            return through_id
        if older_than_days is None:
            raise ArchiveError("give --through-id or --older-than-days")
        cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=older_than_days)).strftime("%Y-%m-%dT%H:%M:%S")
        # preserved_at grows with id; find the last id preserved before the cutoff.
        row = conn.execute(f"SELECT MAX(id) FROM {TABLE} WHERE preserved_at < ?", (cutoff,)).fetchone()
        found = row[0] if row else None
        newest = conn.execute(f"SELECT MAX(id) FROM {TABLE}").fetchone()[0]
        if found is None or newest is None:
            return None
        # Always leave the newest row in the live table: scripts/lean_backup.py
        # reads MAX(id) of the journal to track its nightly deltas.
        return min(found, newest - 1)
    finally:
        conn.close()


def export(db: str, archive: Path, through_id: int) -> dict | None:
    archive.mkdir(parents=True, exist_ok=True)
    done = _manifests(archive)
    after = max((m["last_id"] for m in done), default=0)
    conn = _ro(db)
    try:
        lo, hi, n = conn.execute(
            f"SELECT MIN(id), MAX(id), COUNT(*) FROM {TABLE} WHERE id > ? AND id <= ?", (after, through_id)
        ).fetchone()
        if not n:
            print(f"export: nothing to archive after id {after} through {through_id}")
            return None
        stem = f"phv_{lo:09d}_{hi:09d}"
        final = archive / f"{stem}.jsonl.zst"
        tmp = archive / f".{stem}.jsonl.zst.partial"
        need = 2 * 1024**3
        if shutil.disk_usage(archive).free < need:
            raise ArchiveError("less than 2 GiB free for the archive file")
        digest = hashlib.sha256()
        rows = 0
        hash_mismatches = 0
        first_at = last_at = None
        with open(tmp, "wb") as out:
            proc = subprocess.Popen(
                ["zstd", "-q", f"-{ZSTD_LEVEL}", "--long=27", "-T2", "-c"], stdin=subprocess.PIPE, stdout=out
            )
            assert proc.stdin is not None
            for row in _db_rows(conn, lo, hi):
                obj = dict(zip(COLUMNS, row))
                proc.stdin.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode() + b"\n")
                digest.update(_digest_line(row))
                if hashlib.sha256(row[4].encode()).hexdigest() != row[3]:
                    hash_mismatches += 1
                rows += 1
                first_at = first_at or row[6]
                last_at = row[6]
            proc.stdin.close()
            if proc.wait() != 0:
                raise ArchiveError("zstd compression failed")
            out.flush()
            os.fsync(out.fileno())
        if rows != n:
            raise ArchiveError(f"row count changed during export ({rows} written, {n} expected)")
        os.replace(tmp, final)
        manifest = {
            "table": TABLE,
            "file": final.name,
            "first_id": lo,
            "last_id": hi,
            "rows": rows,
            "first_preserved_at": first_at,
            "last_preserved_at": last_at,
            "row_digest_sha256": digest.hexdigest(),
            "rows_whose_payload_hash_differs_from_payload_sha256_column": hash_mismatches,
            "file_sha256": _sha256_file(final),
            "file_bytes": final.stat().st_size,
            "source_db": os.path.abspath(db),
            "created_at_utc": _now(),
            "format": "zstd-compressed JSON lines; columns " + ",".join(COLUMNS),
        }
        mpath = archive / f"{stem}.manifest.json"
        mpath.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"export: {rows} rows id {lo}..{hi} -> {final} ({manifest['file_bytes'] / 1e6:.1f} MB)")
        return manifest
    finally:
        conn.close()


def verify_one(manifest: dict, archive: Path, db: str | None) -> dict:
    path = archive / manifest["file"]
    result = {"file": manifest["file"], "ok": False}
    if _sha256_file(path) != manifest["file_sha256"]:
        result["error"] = "archive file checksum does not match manifest"
        return result
    digest = hashlib.sha256()
    rows = 0
    prev = 0
    for row in _file_rows(path):
        if row[0] <= prev:
            result["error"] = f"ids out of order at {row[0]}"
            return result
        prev = row[0]
        digest.update(_digest_line(row))
        rows += 1
    if rows != manifest["rows"] or digest.hexdigest() != manifest["row_digest_sha256"]:
        result["error"] = f"archive contents differ from manifest (rows {rows} vs {manifest['rows']})"
        return result
    result["archive_rows"] = rows
    if db is not None:
        conn = _ro(db)
        try:
            ddig = hashlib.sha256()
            drows = 0
            for row in _db_rows(conn, manifest["first_id"], manifest["last_id"]):
                ddig.update(_digest_line(row))
                drows += 1
        finally:
            conn.close()
        result["db_rows_in_range"] = drows
        if drows == 0:
            result["db_status"] = "range already pruned from this database"
        elif drows != rows or ddig.hexdigest() != manifest["row_digest_sha256"]:
            result["error"] = f"database rows in this id range differ from the archive (db {drows} rows, archive {rows} rows, digests {'match' if ddig.hexdigest() == manifest['row_digest_sha256'] else 'differ'})"
            return result
        else:
            result["db_status"] = "identical"
    result["ok"] = True
    return result


def verify(archive: Path, db: str | None) -> list[dict]:
    results = [verify_one(m, archive, db) for m in _manifests(archive)]
    for r in results:
        print("verify:", json.dumps(r))
    return results


def prune(db: str, archive: Path) -> dict:
    """Delete only id ranges whose archive verifies identical against this database right now."""
    deleted = 0
    for m in _manifests(archive):
        r = verify_one(m, archive, db)
        if not r["ok"]:
            raise ArchiveError(f"not pruning: {r}")
        if r.get("db_status") != "identical":
            continue
        conn = sqlite3.connect(db, timeout=120)
        try:
            lo, hi = m["first_id"], m["last_id"]
            step = 50_000
            for start in range(lo, hi + 1, step):
                with conn:
                    cur = conn.execute(f"DELETE FROM {TABLE} WHERE id BETWEEN ? AND ?", (start, min(hi, start + step - 1)))
                    deleted += cur.rowcount
            mode = conn.execute("PRAGMA auto_vacuum").fetchone()[0]
            if mode == 2:
                conn.execute("PRAGMA incremental_vacuum")
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()
        print(f"prune: removed id {m['first_id']}..{m['last_id']} from {db} (archived in {m['file']})")
    return {"deleted": deleted}


def restore(archive: Path, db: str) -> int:
    conn = sqlite3.connect(db, timeout=120)
    inserted = 0
    try:
        conn.execute(TABLE_SQL)
        for m in _manifests(archive):
            r = verify_one(m, archive, None)
            if not r["ok"]:
                raise ArchiveError(f"archive failed verification, not restoring: {r}")
            batch = []
            for row in _file_rows(archive / m["file"]):
                batch.append(row)
                if len(batch) >= 5000:
                    with conn:
                        inserted += conn.executemany(
                            f"INSERT OR IGNORE INTO {TABLE} ({', '.join(COLUMNS)}) VALUES (?,?,?,?,?,?,?)", batch
                        ).rowcount
                    batch = []
            if batch:
                with conn:
                    inserted += conn.executemany(
                        f"INSERT OR IGNORE INTO {TABLE} ({', '.join(COLUMNS)}) VALUES (?,?,?,?,?,?,?)", batch
                    ).rowcount
    finally:
        conn.close()
    print(f"restore: inserted {inserted} rows into {db}")
    return inserted


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["export", "verify", "prune", "restore", "cycle"])
    ap.add_argument("--db", default=None)
    ap.add_argument("--archive", default=str(DEFAULT_ARCHIVE))
    ap.add_argument("--through-id", type=int, default=None)
    ap.add_argument("--older-than-days", type=int, default=None)
    ap.add_argument("--mirror", default=None, help="also hard-link archive files into this folder (e.g. backups/offbox/history_archive)")
    args = ap.parse_args()
    archive = Path(args.archive)

    try:
        if args.command in {"export", "cycle"}:
            if not args.db:
                raise ArchiveError("--db is required")
            through = resolve_through_id(args.db, through_id=args.through_id, older_than_days=args.older_than_days)
            if through:
                export(args.db, archive, through)
        if args.command == "verify":
            results = verify(archive, args.db)
            return 0 if all(r["ok"] for r in results) else 1
        if args.command in {"prune", "cycle"}:
            if not args.db:
                raise ArchiveError("--db is required")
            prune(args.db, archive)
        if args.command == "restore":
            if not args.db:
                raise ArchiveError("--db is required")
            restore(archive, args.db)
        if args.mirror:
            mirror = Path(args.mirror)
            mirror.mkdir(parents=True, exist_ok=True)
            for f in archive.glob("phv_*"):
                dest = mirror / f.name
                if not dest.exists():
                    try:
                        os.link(f, dest)
                    except OSError:
                        shutil.copy2(f, dest)
    except ArchiveError as exc:
        print(f"history_journal_archive: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
