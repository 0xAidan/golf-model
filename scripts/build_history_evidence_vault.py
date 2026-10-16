#!/usr/bin/env python3
"""Preserve whitelisted historical rows in a new, provenance-scoped JSONL vault.

No application imports, migrations, restoration, grading or model execution.
Remote mode executes this same stdlib-only reader through SSH stdin; it does not
install files on the server. Quarantines use immutable base-file reads only.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shlex
import sqlite3
import subprocess
import sys
import tarfile
import time

TABLES = ("tournaments", "picks", "pick_outcomes", "results", "pick_ledger", "prediction_log")


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


def lossless_value(value):
    if isinstance(value, bytes):
        return {"$sqlite_blob_base64": base64.b64encode(value).decode()}
    if isinstance(value, float) and not math.isfinite(value):
        return {"$sqlite_nonfinite_float": repr(value)}
    return value


def database_records(path, *, immutable=False, location=None, table_timeout=120):
    path = Path(path)
    before = path.stat()
    descriptor = {
        "kind": "sqlite", "location": location or str(path.absolute()),
        "size_bytes": before.st_size, "mtime_ns": before.st_mtime_ns,
        "immutable_base_only": immutable, "wal_applied": not immutable,
        "fingerprint_method": "metadata_sha256_not_full_file_hash",
    }
    source_id = digest(descriptor)
    yield {"type": "source_begin", "source_id": source_id, "source": descriptor}
    conn = sqlite3.connect(path.absolute().as_uri() + "?mode=ro" + ("&immutable=1" if immutable else ""), uri=True, timeout=2.5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("BEGIN")
    try:
        for table in TABLES:
            count = 0
            yield {"type": "table_begin", "source_id": source_id, "table": table}
            try:
                started = time.monotonic()
                conn.set_progress_handler(lambda: int(time.monotonic() - started > table_timeout), 10000)
                columns = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
                if not columns:
                    yield {"type": "table_end", "source_id": source_id, "table": table, "rows": 0, "state": "missing"}
                    continue
                for row in conn.execute(f'SELECT * FROM "{table}"'):
                    count += 1
                    raw = {key: lossless_value(value) for key, value in dict(row).items()}
                    yield {"type": "row", "source_id": source_id, "table": table, "ordinal": count, "row_sha256": digest(raw), "row": raw}
                yield {"type": "table_end", "source_id": source_id, "table": table, "rows": count, "state": "complete"}
            except sqlite3.Error as exc:
                yield {"type": "table_end", "source_id": source_id, "table": table, "rows": count, "state": "partial", "error": str(exc)}
        after = path.stat()
        yield {"type": "source_end", "source_id": source_id,
               "source_metadata_unchanged": (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)}
    finally:
        conn.rollback()
        conn.close()


def archive_records(path, *, archive_sha256):
    """Stream core exports, including nested gzip ledgers, without extracting."""
    before = Path(path).stat()
    announced = set()
    with tarfile.open(path, "r|gz") as archive:
        for member in archive:
            parts = Path(member.name).parts
            if not member.isfile() or len(parts) != 4 or parts[:2] != ("data", "exports") or not parts[2].startswith("tournament_"):
                continue
            filename = parts[-1]
            table = filename.removesuffix(".gz").removesuffix(".jsonl")
            if table not in TABLES or filename not in {table + ".jsonl", table + ".jsonl.gz"}:
                continue
            descriptor = {"kind": "tournament_export", "archive": Path(path).name, "archive_sha256": archive_sha256,
                          "source_folder": "/".join(parts[:3]), "fingerprint_method": "archive_hash_and_source_folder"}
            source_id = digest(descriptor)
            if source_id not in announced:
                yield {"type": "source_begin", "source_id": source_id, "source": descriptor}
                announced.add(source_id)
            yield {"type": "table_begin", "source_id": source_id, "table": table, "member_path": member.name}
            count = 0
            file = archive.extractfile(member)
            stream = gzip.GzipFile(fileobj=file) if filename.endswith(".gz") else file
            try:
                for line in stream:
                    if not line.strip():
                        continue
                    raw = json.loads(line)
                    if not isinstance(raw, dict):
                        raise ValueError("Source row is not a JSON object")
                    count += 1
                    yield {"type": "row", "source_id": source_id, "table": table, "ordinal": count,
                           "member_path": member.name, "input_line_sha256": hashlib.sha256(line).hexdigest(),
                           "row_sha256": digest(raw), "row": raw}
                yield {"type": "table_end", "source_id": source_id, "table": table, "rows": count, "state": "complete"}
            except (ValueError, OSError, EOFError) as exc:
                yield {"type": "table_end", "source_id": source_id, "table": table, "rows": count, "state": "partial", "error": str(exc)}
            finally:
                stream.close()
    after = Path(path).stat()
    unchanged = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    for source_id in sorted(announced):
        yield {"type": "source_end", "source_id": source_id, "source_metadata_unchanged": unchanged}


def remote_records(alias, path, *, table_timeout=120):
    command = " ".join(shlex.quote(p) for p in ("python3", "-", "--emit-db", str(path), "--immutable", "--location", f"ssh:{alias}:{path}", "--table-timeout", str(table_timeout)))
    process = subprocess.Popen(["ssh", "-o", "BatchMode=yes", alias, command], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process.stdin.write(Path(__file__).read_bytes())
    process.stdin.close()
    try:
        with gzip.GzipFile(fileobj=process.stdout) as compressed:
            for line in compressed:
                yield json.loads(line)
        stderr = process.stderr.read().decode(errors="replace")
        if process.wait() != 0:
            raise RuntimeError(f"SSH reader failed for {path}: {stderr[-1000:]}")
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)


def event_candidate(row):
    """No numeric-ID merge and no inferred tour/round/name aliases."""
    fields = {"event_id": str(row.get("event_id") or "").strip(), "year": row.get("year"),
              "tour": str(row.get("tour") or "").strip().lower(),
              "name": re.sub(r"\s+", " ", str(row.get("name") or "").strip().lower())}
    missing = [key for key, value in fields.items() if value in (None, "")]
    return {"fields": fields, "match_status": "needs_identity_review" if missing else "candidate_only",
            "missing_fields": missing, "merged": False}


def write_vault(streams, output, *, max_compressed_bytes=1024**3):
    """Create exclusively; retain every input row, including exact duplicates."""
    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    partial = output.with_name(output.name + ".partial")
    manifest = {"format_version": 1, "created_at_utc": datetime.now(timezone.utc).isoformat(), "vault": output.name,
                "tables_whitelist": TABLES, "sources": {}, "row_counts": Counter(), "tournament_candidates": [],
                "raw_rows_merged": False, "model_changes": False, "production_writes": False,
                "limitations": ["Duplicate/conflicting source rows are retained, not independent wagers.",
                                "Immutable quarantine reads exclude original WAL; sidecars remain preserved separately.",
                                "Only six logical core tables are included; full source archives remain authoritative.",
                                "Candidate event matching is unverified until tour, season, event ID and name are reconciled."]}
    count = 0
    with partial.open("xb") as raw_output:
        with gzip.GzipFile(fileobj=raw_output, mode="wb", compresslevel=3, mtime=0) as compressed:
            for stream in streams:
                for record in stream:
                    if record.get("table") and record["table"] not in TABLES:
                        raise ValueError("Non-whitelisted table rejected")
                    compressed.write(json_bytes(record) + b"\n")
                    kind = record["type"]
                    source_id = record["source_id"]
                    if kind == "source_begin":
                        manifest["sources"][source_id] = {"source": record["source"], "tables": {}, "finished": False}
                    elif kind == "table_begin":
                        manifest["sources"][source_id]["tables"][record["table"]] = {"state": "started", "rows": 0}
                    elif kind == "table_end":
                        manifest["sources"][source_id]["tables"][record["table"]] = {k: v for k, v in record.items() if k not in {"source_id", "type", "table"}}
                    elif kind == "source_end":
                        manifest["sources"][source_id]["finished"] = True
                        manifest["sources"][source_id]["source_metadata_unchanged"] = record["source_metadata_unchanged"]
                    elif kind == "row":
                        count += 1
                        manifest["row_counts"][record["table"]] += 1
                        if record["table"] == "tournaments":
                            manifest["tournament_candidates"].append({"source_id": source_id, "source_row_id": record["row"].get("id"),
                                                                       **event_candidate(record["row"])})
                    if count % 10000 == 0 and raw_output.tell() > max_compressed_bytes:
                        raise RuntimeError("Vault compressed-byte budget exceeded; partial output retained, not finalized")
        raw_output.flush()
        os.fsync(raw_output.fileno())
    if partial.stat().st_size > max_compressed_bytes:
        raise RuntimeError("Vault compressed-byte budget exceeded; partial output retained, not finalized")
    h = hashlib.sha256()
    with partial.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            h.update(block)
    manifest.update({"rows": count, "compressed_bytes": partial.stat().st_size, "sha256": h.hexdigest(),
                     "all_tables_complete": all(t["state"] in {"complete", "missing"} for s in manifest["sources"].values() for t in s["tables"].values())})
    os.link(partial, output)
    partial.unlink()
    manifest_path = output.with_name(output.name + ".manifest.json")
    with manifest_path.open("x") as handle:
        json.dump(manifest, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return manifest


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit-db")
    parser.add_argument("--immutable", action="store_true")
    parser.add_argument("--location")
    parser.add_argument("--table-timeout", type=int, default=120)
    parser.add_argument("--current", type=Path)
    parser.add_argument("--current-manifest", type=Path)
    parser.add_argument("--exports", type=Path)
    parser.add_argument("--exports-manifest", type=Path)
    parser.add_argument("--ssh-alias", default="golf-vps")
    parser.add_argument("--quarantine", action="append", default=[])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.emit_db:
        with gzip.GzipFile(fileobj=sys.stdout.buffer, mode="wb", compresslevel=3, mtime=0) as out:
            for row in database_records(args.emit_db, immutable=args.immutable, location=args.location, table_timeout=args.table_timeout):
                out.write(json_bytes(row) + b"\n")
        return
    if not all((args.current, args.current_manifest, args.exports, args.exports_manifest, args.out)):
        parser.error("--current, --current-manifest, --exports, --exports-manifest and --out are required")
    current_manifest = json.loads(args.current_manifest.read_text())
    exports_manifest = json.loads(args.exports_manifest.read_text())
    if file_sha256(args.current) != current_manifest["sha256"] or file_sha256(args.exports) != exports_manifest["sha256"]:
        raise ValueError("Preserved input checksum mismatch; no vault created")
    streams = [database_records(args.current)]
    streams += [remote_records(args.ssh_alias, path, table_timeout=args.table_timeout) for path in args.quarantine]
    streams.append(archive_records(args.exports, archive_sha256=exports_manifest["sha256"]))
    manifest = write_vault(streams, args.out)
    print(json.dumps({k: v for k, v in manifest.items() if k not in {"sources", "tournament_candidates"}}, indent=2))


if __name__ == "__main__":
    main()
