#!/usr/bin/env python3
"""Build a slim copy of golf.db without journal rows that are already archived.

Used once on 2026-11-19 to move ~21.9M old ``prediction_history_versions`` rows
out of the live database. The source file is opened read-only and never
modified; the caller keeps it as the pre-archive copy.

Everything else is copied exactly: every table (all rows), index, view and
trigger from sqlite_master, sqlite_sequence (so AUTOINCREMENT ids continue where
they left off), user_version, application_id and page size. The new file uses
auto_vacuum=INCREMENTAL so later monthly archive runs can give space back
without a full VACUUM.

  python3 scripts/build_compact_db.py --source data/golf.db \
      --dest data/golf.db.compact --journal-keep-after-id 21858941
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time

JOURNAL = "prediction_history_versions"


def q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def build(source: str, dest: str, keep_after_id: int) -> dict:
    if os.path.exists(dest):
        raise SystemExit(f"{dest} already exists; remove it first")
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    page_size = src.execute("PRAGMA page_size").fetchone()[0]
    user_version = src.execute("PRAGMA user_version").fetchone()[0]
    app_id = src.execute("PRAGMA application_id").fetchone()[0]
    objects = src.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY rowid"
    ).fetchall()
    src.close()

    dst = sqlite3.connect(dest, isolation_level=None)
    dst.execute(f"PRAGMA page_size={int(page_size)}")
    dst.execute("PRAGMA auto_vacuum=INCREMENTAL")
    dst.execute("PRAGMA journal_mode=OFF")
    dst.execute("PRAGMA synchronous=OFF")
    dst.execute(f"ATTACH DATABASE 'file:{source}?mode=ro' AS src")
    started = time.time()
    counts: dict[str, dict] = {}

    dst.execute("BEGIN")
    tables = [o for o in objects if o[0] == "table" and not o[1].startswith("sqlite_")]
    for _, name, _, sql in tables:
        dst.execute(sql)
    for _, name, _, _ in tables:
        cols = [r[1] for r in dst.execute(f"PRAGMA main.table_xinfo({q(name)})") if r[6] in (0, 1)]
        col_list = ", ".join(q(c) for c in cols)
        where = f" WHERE id > {int(keep_after_id)}" if name == JOURNAL else ""
        dst.execute(f"INSERT INTO main.{q(name)} ({col_list}) SELECT {col_list} FROM src.{q(name)}{where}")
        expected = dst.execute(f"SELECT COUNT(*) FROM src.{q(name)}{where}").fetchone()[0]
        got = dst.execute(f"SELECT COUNT(*) FROM main.{q(name)}").fetchone()[0]
        counts[name] = {"expected": expected, "copied": got}
        if expected != got:
            raise SystemExit(f"row count mismatch in {name}: {got} vs {expected}")
    has_seq = dst.execute("SELECT 1 FROM main.sqlite_master WHERE name='sqlite_sequence'").fetchone()
    if has_seq:
        dst.execute("DELETE FROM main.sqlite_sequence")
        dst.execute("INSERT INTO main.sqlite_sequence (name, seq) SELECT name, seq FROM src.sqlite_sequence")
    for kind in ("index", "view", "trigger"):
        for t, name, _, sql in objects:
            if t == kind:
                dst.execute(sql)
    dst.execute("COMMIT")
    dst.execute(f"PRAGMA user_version={int(user_version)}")
    dst.execute(f"PRAGMA application_id={int(app_id)}")

    src_schema = sorted(dst.execute("SELECT type, name, tbl_name, sql FROM src.sqlite_master WHERE name NOT LIKE 'sqlite_autoindex%'").fetchall())
    dst_schema = sorted(dst.execute("SELECT type, name, tbl_name, sql FROM main.sqlite_master WHERE name NOT LIKE 'sqlite_autoindex%'").fetchall())
    if src_schema != dst_schema:
        raise SystemExit("schema differs between source and compact copy")
    seq_src = sorted(dst.execute("SELECT name, seq FROM src.sqlite_sequence").fetchall())
    seq_dst = sorted(dst.execute("SELECT name, seq FROM main.sqlite_sequence").fetchall())
    if seq_src != seq_dst:
        raise SystemExit("sqlite_sequence differs")
    dst.execute("DETACH DATABASE src")
    check = dst.execute("PRAGMA integrity_check").fetchone()[0]
    if check != "ok":
        raise SystemExit(f"integrity_check failed on compact copy: {check}")
    dst.execute("PRAGMA journal_mode=WAL")
    dst.close()
    os.chmod(dest, 0o644)
    report = {
        "source": source,
        "dest": dest,
        "journal_rows_kept_after_id": keep_after_id,
        "tables": len(counts),
        "rows_copied": sum(v["copied"] for v in counts.values()),
        "journal_rows_kept": counts.get(JOURNAL, {}).get("copied"),
        "integrity_check": check,
        "schema_identical": True,
        "sqlite_sequence_identical": True,
        "dest_bytes": os.path.getsize(dest),
        "seconds": round(time.time() - started, 1),
        "per_table": counts,
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--dest", required=True)
    ap.add_argument("--journal-keep-after-id", type=int, required=True)
    ap.add_argument("--report", default=None)
    args = ap.parse_args()
    report = build(args.source, args.dest, args.journal_keep_after_id)
    text = json.dumps(report, indent=2)
    if args.report:
        with open(args.report, "w") as fh:
            fh.write(text + "\n")
    summary = {k: v for k, v in report.items() if k != "per_table"}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
