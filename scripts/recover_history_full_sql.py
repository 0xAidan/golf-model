#!/usr/bin/env python3
"""Bounded private raw SQL salvage; never execute recovered SQL or change its source."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import selectors
import shutil
import subprocess
import time
import zlib

from recover_history_core import CoreStatementScanner, _PREFIX, _table, file_sha256, parse_core_insert


def utc():
    return datetime.now(timezone.utc).isoformat()


def recover(source: Path, output: Path, expected_hash: str, *, max_bytes=512 << 20,
            reserve=1 << 30, seconds=600, cli="/usr/bin/sqlite3"):
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    os.chmod(output, 0o700)
    source = source.resolve()
    before = source.stat()
    wal = source.with_name(source.name + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise ValueError("Nonempty WAL; immutable base-only recovery refused")
    print(json.dumps({"phase": "hash_before", "source_bytes": before.st_size}), flush=True)
    source_hash = file_sha256(source)
    if source_hash != expected_hash:
        raise ValueError("Source hash mismatch")
    print(json.dumps({"phase": "source_verified", "sha256": source_hash}), flush=True)
    if shutil.disk_usage(output).free < reserve + (64 << 20):
        raise RuntimeError("Insufficient disk reserve")
    version = subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    subprocess.run([cli, ":memory:", "SELECT count(*) FROM sqlite_dbpage;"], capture_output=True, timeout=5, check=True)
    temporary = output / "sqlite-tmp"
    temporary.mkdir(mode=0o700)

    def child_limits():
        resource.setrlimit(resource.RLIMIT_FSIZE, (max_bytes, max_bytes))
        resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds + 1))

    command = [cli, "-readonly", "-batch", source.as_uri() + "?mode=ro&immutable=1", ".recover"]
    started = time.monotonic()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env={**os.environ, "SQLITE_TMPDIR": str(temporary), "TMPDIR": str(temporary)},
                               preexec_fn=child_limits)
    path = output / "full-recovery.sql.gz"
    compressor = zlib.compressobj(6, zlib.DEFLATED, 31)
    scanner = CoreStatementScanner(max_statement_bytes=16 << 20, tables=None)
    counts, parse_errors = Counter(), Counter()
    raw_hash, stderr_hash = hashlib.sha256(), hashlib.sha256()
    raw_bytes = compressed_bytes = stderr_bytes = 0
    last_update = started
    reason = None
    leads = []
    tournaments = []
    retained_lead_bytes = 0
    candidate_tables = {"runs", "live_snapshot_history", "market_prediction_rows", "pre_teeoff_frozen",
                        "pre_teeoff_candidate", "pre_teeoff_candidates", "predictions", "picks", "prediction_log"}
    lead_re = re.compile(rb"PGA Championship|Aronimink|2026-05-", re.I)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, "stdout")
    selector.register(process.stderr, selectors.EVENT_READ, "stderr")

    def inspect(chunk, *, final=False):
        nonlocal retained_lead_bytes
        for statement in scanner.feed(chunk, final=final):
            match = _PREFIX.match(statement[:512].decode("ascii", errors="ignore"))
            if not match:
                parse_errors["unrecognized_insert_prefix"] += 1
                continue
            table = _table(match)
            counts[table] += 1
            retain_candidate = (table in candidate_tables and len(leads) < 1000
                                and retained_lead_bytes < (8 << 20) and lead_re.search(statement))
            if table == "tournaments" or retain_candidate:
                try:
                    _, row = parse_core_insert(statement, approved_tables=None)
                    row_bytes = len(statement)
                    if table == "tournaments" and len(tournaments) < 1000 and row_bytes < (64 << 10):
                        tournaments.append(row)
                    if retained_lead_bytes + row_bytes > (8 << 20):
                        parse_errors["lead_retention_byte_limit"] += 1
                        continue
                    if len(leads) < 1000 and (table == "tournaments" or lead_re.search(statement)):
                        leads.append({"table": table, "table_ordinal": counts[table],
                                      "sql_sha256": hashlib.sha256(statement).hexdigest(), "row": row})
                        retained_lead_bytes += row_bytes
                except ValueError as exc:
                    parse_errors[str(exc)] += 1

    with path.open("xb") as sink:
        os.chmod(path, 0o600)
        try:
            while selector.get_map():
                elapsed = time.monotonic() - started
                if elapsed > seconds:
                    reason = "time_limit"
                    break
                if shutil.disk_usage(output).free < reserve + (1 << 20):
                    reason = "disk_reserve_limit"
                    break
                if elapsed - (last_update - started) >= 30:
                    print(json.dumps({"phase": "recover", "seconds": round(elapsed), "raw_bytes": raw_bytes,
                                      "compressed_bytes": compressed_bytes, "insert_rows": sum(counts.values()),
                                      "tables": len(counts), "lead_rows": len(leads)}), flush=True)
                    last_update = time.monotonic()
                for key, _ in selector.select(timeout=0.25):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if key.data == "stderr":
                        stderr_hash.update(chunk)
                        stderr_bytes += len(chunk)
                        continue
                    proposed = compressor.copy()
                    encoded = proposed.compress(chunk)
                    if compressed_bytes + len(encoded) > max_bytes - (256 << 10):
                        reason = "compressed_output_limit"
                        break
                    sink.write(encoded)
                    compressed_bytes += len(encoded)
                    compressor = proposed
                    raw_hash.update(chunk)
                    raw_bytes += len(chunk)
                    inspect(chunk)
                if reason:
                    break
        finally:
            if process.poll() is None:
                process.kill()
            exit_code = process.wait(timeout=10)
            selector.close()
            process.stdout.close()
            process.stderr.close()
            sink.write(compressor.flush(zlib.Z_FINISH))
        inspect(b"", final=True)
    if exit_code != 0 and reason is None:
        reason = "sqlite_recover_nonzero_exit"
    print(json.dumps({"phase": "hash_after", "seconds": round(time.monotonic() - started)}), flush=True)
    after_hash = file_sha256(source)
    after = source.stat()
    verified = hashlib.sha256()
    with gzip.open(path, "rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            verified.update(block)
    report = {"schema_version": 1, "created_at": utc(), "source": str(source),
              "source_bytes": before.st_size, "source_sha256_before": source_hash,
              "source_sha256_after": after_hash, "source_unchanged": source_hash == after_hash and
              (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
              "wal_applied": False, "wal_empty_or_absent": True, "command": command,
              "sqlite_version": version, "freelist_included": True,
              "sql_executed": False, "imported": False, "performance_eligible": False,
              "status": "partial_salvage" if reason else "salvaged_unverified", "stop_reason": reason,
              "sqlite_exit_code": exit_code, "elapsed_seconds": round(time.monotonic() - started, 2),
              "limits": {"compressed_bytes": max_bytes, "min_free_bytes": reserve, "recovery_seconds": seconds},
              "sql_gzip": str(path), "gzip_bytes": path.stat().st_size, "gzip_sha256": file_sha256(path),
              "sql_bytes": raw_bytes, "sql_sha256": raw_hash.hexdigest(),
              "gzip_readback_verified": verified.hexdigest() == raw_hash.hexdigest(),
              "insert_counts": dict(counts), "scanner_counts": dict(scanner.counts),
              "parse_errors": dict(parse_errors), "stderr_bytes": stderr_bytes,
              "stderr_sha256": stderr_hash.hexdigest(), "tournaments": tournaments,
              "lead_rows_retained": len(leads), "lead_rows_limit": 1000,
              "lead_sql_byte_limit": 8 << 20}
    for name, value in [("manifest.json", report), ("event-leads.json", leads)]:
        with (output / name).open("x", encoding="utf-8") as handle:
            os.chmod(output / name, 0o600)
            json.dump(value, handle, indent=2, ensure_ascii=False)
    print(json.dumps({"phase": "complete", "status": report["status"], "stop_reason": reason,
                      "source_unchanged": report["source_unchanged"], "gzip_readback_verified": report["gzip_readback_verified"],
                      "gzip_bytes": report["gzip_bytes"], "insert_counts": dict(counts)}), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    arguments = parser.parse_args()
    recover(arguments.source, arguments.output, arguments.expected_sha256)
