#!/usr/bin/env python3
"""Preserve original prediction/ranking databases without restoring or importing them.

Creates a consistent SQLite backup including committed WAL data, hashes and gzip
preserves it, then streams a whitelist of logical sports-history tables. Originals
are opened only with mode=ro/query_only; unavailable cloud placeholders stay explicit.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
import tarfile
import time

TABLES = (
    "tournaments", "picks", "pick_outcomes", "results", "pick_ledger", "prediction_log",
    "metrics", "live_snapshot_history", "market_prediction_rows", "runs",
    "historical_predictions", "historical_event_info", "historical_odds", "historical_matchup_odds",
    "rounds", "pit_rolling_stats", "pit_course_stats", "clv_log",
    "challenger_predictions", "shadow_event_simulations", "matchup_outcome_results",
    "inplay_round_matchup_prices", "inplay_round_matchup_predictions", "pair_matchup_predictions",
    "pre_teeoff_candidates", "pre_teeoff_frozen", "track_configs", "live_model_registry",
    "research_model_registry", "active_strategy", "weight_sets", "course_weight_profiles",
    "calibration_curve", "market_performance", "ai_adjustments", "blend_history",
    "prediction_history_versions",
)
CORE_TABLES = {"tournaments", "picks", "pick_outcomes", "results", "prediction_log"}
DISK_RESERVE_BYTES = 1024 ** 3


class DiskReserveExceeded(RuntimeError):
    """Stop the whole export before consuming the reserved free disk space."""


def ensure_disk_reserve(path):
    if shutil.disk_usage(Path(path).parent).free < DISK_RESERVE_BYTES:
        raise DiskReserveExceeded("Preservation stopped at 1 GiB disk reserve; originals untouched")


def encoded(value):
    if isinstance(value, bytes):
        return {"$sqlite_blob_base64": base64.b64encode(value).decode()}
    if isinstance(value, float) and not math.isfinite(value):
        return {"$sqlite_nonfinite_float": repr(value)}
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def metadata(path):
    path = Path(path)
    if not path.exists():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {"path": str(path.absolute()), "exists": True, "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "blocks": getattr(stat, "st_blocks", None), "flags": hex(getattr(stat, "st_flags", 0)),
            "cloud_placeholder": bool(getattr(stat, "st_flags", 0) & 0x40000000)}


def prior_core_hashes(path):
    hashes = defaultdict(set)
    if path is None:
        return hashes
    with gzip.open(path, "rt") as handle:
        for line in handle:
            item = json.loads(line)
            if item.get("type") == "row" and item.get("table") in CORE_TABLES:
                hashes[item["table"]].add(item["row_sha256"])
    return hashes


def fixture_signals(row):
    signals = []
    for column in ("name", "event_name", "tournament_name", "player_name", "player_display"):
        value = str(row.get(column) or "")
        if re.search(r"\b(test|fixture|dummy|synthetic)\b", value, re.I):
            signals.append(f"{column}:fixture_like_text")
        if value.strip().lower() in {"current event", "next event", "upcoming event", "live event", "test tournament"}:
            signals.append(f"{column}:generic_fixture_event_name")
    if str(row.get("event_id") or "") in {"999", "9999", "test", "fixture"}:
        signals.append("event_id:fixture_like_value")
    return signals


def _progress_deadline(seconds):
    started = time.monotonic()

    def callback(*_args):
        if time.monotonic() - started > seconds:
            raise TimeoutError(f"SQLite snapshot deadline exceeded ({seconds}s)")
    return callback


def snapshot_source(source, destination, *, timeout=300, immutable_empty_wal=False):
    """Exclusive backup destination, WAL-aware consistent read transaction, no source writes."""
    uri = Path(source).absolute().as_uri() + "?mode=ro"
    if immutable_empty_wal:
        wal = Path(str(source) + "-wal")
        if wal.exists() and wal.stat().st_size:
            raise ValueError("Immutable snapshot requires an absent or zero-byte WAL")
        uri += "&immutable=1"
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    origin = sqlite3.connect(uri, uri=True, timeout=3)
    origin.execute("PRAGMA query_only=ON")
    origin.execute("BEGIN")
    target = sqlite3.connect(destination)
    try:
        deadline = _progress_deadline(timeout)

        def progress(*args):
            deadline(*args)
            ensure_disk_reserve(destination)

        origin.backup(target, pages=512, progress=progress, sleep=0.01)
        started = time.monotonic()
        target.set_progress_handler(lambda: int(time.monotonic() - started > 120), 10000)
        check = [r[0] for r in target.execute("PRAGMA quick_check")]
        return check
    finally:
        target.close()
        origin.rollback()
        origin.close()


def gzip_snapshot(snapshot, destination):
    raw_digest = hashlib.sha256()
    with Path(snapshot).open("rb") as source, Path(destination).open("xb") as output:
        with gzip.GzipFile(fileobj=output, mode="wb", compresslevel=3, mtime=0) as compressed:
            for chunk in iter(lambda: source.read(1 << 20), b""):
                ensure_disk_reserve(destination)
                raw_digest.update(chunk)
                compressed.write(chunk)
        output.flush()
        os.fsync(output.fileno())
    # Independently read back the preserved compressed bytes before deleting our temp.
    verified = hashlib.sha256()
    with gzip.open(destination, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            verified.update(chunk)
    if verified.hexdigest() != raw_digest.hexdigest():
        raise ValueError("Compressed preservation snapshot failed read-back hash verification")
    return {"path": str(destination), "bytes": Path(destination).stat().st_size,
            "gzip_sha256": sha256(destination), "sqlite_sha256": raw_digest.hexdigest(), "readback_verified": True}


def logical_vault(snapshot, output, source_id, *, prior=None, table_timeout=180):
    conn = sqlite3.connect(Path(snapshot).absolute().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("BEGIN")
    summaries, core_new, core_match, event_values = {}, Counter(), Counter(), defaultdict(set)
    total_rows = 0
    schema = {r["name"]: r["sql"] for r in conn.execute("SELECT name,sql FROM sqlite_master WHERE type='table'")}
    try:
        with Path(output).open("xb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=3, mtime=0) as compressed:
            compressed.write(canonical({"type": "source_begin", "source_id": source_id, "snapshot_sha256": source_id}) + b"\n")
            for table in TABLES:
                if table not in schema:
                    continue
                started = time.monotonic()
                conn.set_progress_handler(lambda: int(time.monotonic() - started > table_timeout), 10000)
                summary = {"state": "started", "rows": 0, "fixture_signal_rows": 0, "date_ranges": {}, "distinct_events": 0}
                summaries[table] = summary
                compressed.write(canonical({"type": "table_begin", "source_id": source_id, "table": table, "schema_sql": schema[table]}) + b"\n")
                try:
                    for sqlite_row in conn.execute(f'SELECT * FROM "{table}"'):
                        row = {key: encoded(value) for key, value in dict(sqlite_row).items()}
                        row_hash = hashlib.sha256(canonical(row)).hexdigest()
                        signals = fixture_signals(row)
                        summary["rows"] += 1
                        total_rows += 1
                        if total_rows % 1000 == 0:
                            ensure_disk_reserve(output)
                        summary["fixture_signal_rows"] += bool(signals)
                        for column in ("created_at", "generated_at", "date", "event_completed", "timestamp"):
                            value = row.get(column)
                            if isinstance(value, str) and re.match(r"^20\d\d-\d\d-\d\d", value):
                                bounds = summary["date_ranges"].setdefault(column, [value, value])
                                bounds[0], bounds[1] = min(bounds[0], value), max(bounds[1], value)
                        event = (row.get("tour"), row.get("year"), row.get("event_id"), row.get("event_name"))
                        if row.get("event_id") is not None:
                            event_values[table].add(event)
                        if table in CORE_TABLES:
                            (core_match if row_hash in (prior or {}).get(table, set()) else core_new)[table] += 1
                        compressed.write(canonical({"type": "row", "source_id": source_id, "table": table,
                                                    "ordinal": summary["rows"], "row_sha256": row_hash,
                                                    "fixture_signals": signals, "performance_eligible": False,
                                                    "row": row}) + b"\n")
                        if summary["rows"] % 250000 == 0:
                            print(json.dumps({"table": table, "rows_preserved": summary["rows"]}), flush=True)
                    summary["state"] = "complete"
                except sqlite3.Error as exc:
                    summary["state"], summary["error"] = "partial", str(exc)
                summary["distinct_events"] = len(event_values[table])
                summary["elapsed_seconds"] = round(time.monotonic() - started, 2)
                compressed.write(canonical({"type": "table_end", "source_id": source_id, "table": table, **summary}) + b"\n")
            compressed.write(canonical({"type": "source_end", "source_id": source_id, "all_tables_complete": all(r["state"] == "complete" for r in summaries.values())}) + b"\n")
    finally:
        conn.rollback()
        conn.close()
    return {"path": str(output), "bytes": Path(output).stat().st_size, "sha256": sha256(output), "tables": summaries,
            "core_rows_exact_match_prior": dict(core_match), "core_rows_not_exact_match_prior": dict(core_new),
            "event_inventory": {table: [list(event) for event in sorted(events, key=lambda v: repr(v))] for table, events in event_values.items()},
            "non_whitelisted_tables": sorted(set(schema) - set(TABLES) - {"sqlite_sequence"})}


def collect(source, output, *, prior=None, timeout=300, keep_uncompressed=False, immutable_empty_wal=False):
    source = Path(source).absolute()
    before = metadata(source)
    descriptor = {"source": before, "sidecars": [metadata(str(source) + suffix) for suffix in ("-wal", "-shm")],
                  "started_at": datetime.now(timezone.utc).isoformat(), "originals_modified": False}
    identity = hashlib.sha256(canonical({"source": before, "sidecars": descriptor["sidecars"]})).hexdigest()[:16]
    directory = Path(output) / identity
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text())
    if not before["exists"] or before["cloud_placeholder"]:
        descriptor.update({"state": "cloud_placeholder" if before.get("cloud_placeholder") else "missing", "source_id": identity})
    else:
        # Reserve enough space for this task's temporary backup and compressed outputs.
        if shutil.disk_usage(directory).free < before["bytes"] + DISK_RESERVE_BYTES:
            raise DiskReserveExceeded("Insufficient free disk for a separate snapshot; originals untouched")
        snapshot = directory / "consistent-snapshot.sqlite"
        descriptor["snapshot_read_mode"] = "mode=ro&immutable=1; verified empty/absent WAL" if immutable_empty_wal else "mode=ro; WAL-aware read transaction"
        descriptor["quick_check"] = snapshot_source(source, snapshot, timeout=timeout, immutable_empty_wal=immutable_empty_wal)
        descriptor["preservation"] = gzip_snapshot(snapshot, directory / "consistent-snapshot.sqlite.gz")
        descriptor["source_id"] = descriptor["preservation"]["sqlite_sha256"]
        descriptor["logical"] = logical_vault(snapshot, directory / "predictions-and-rankings.jsonl.gz", descriptor["source_id"], prior=prior)
        descriptor["state"] = "complete" if descriptor["quick_check"] == ["ok"] and all(t["state"] == "complete" for t in descriptor["logical"]["tables"].values()) else "partial"
        if not keep_uncompressed and descriptor["preservation"]["readback_verified"]:
            # This exclusively owned temporary file is a verified duplicate of the gzip.
            snapshot.unlink()
            descriptor["temporary_snapshot_removed_after_verified_preservation"] = True
        descriptor["source_after"] = metadata(source)
        descriptor["source_metadata_unchanged"] = before == descriptor["source_after"]
    descriptor["finished_at"] = datetime.now(timezone.utc).isoformat()
    descriptor["limitations"] = [
        "Rows are original forecast observations, not independent bets or validated settlements.",
        "Fixture-like text/IDs are flagged, retained and excluded from performance eligibility pending identity review.",
        "No cross-source integer ID joins or outcome/ranking rewrites were performed.",
        "Non-whitelisted tables remain preserved in the full compressed SQLite snapshot but are not logically exported.",
        "Cloud placeholder metadata does not mean readable content; unavailable bytes are not counted as recovered.",
    ]
    with manifest_path.open("x") as handle:
        json.dump(descriptor, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return descriptor


class _DigestReader:
    def __init__(self, source):
        self.source, self.digest = source, hashlib.sha256()

    def read(self, size=-1):
        value = self.source.read(size)
        self.digest.update(value)
        return value

    def readline(self, size=-1):
        value = self.source.readline(size)
        self.digest.update(value)
        return value


def collect_archive(source, output):
    """Stream whitelisted exported JSONL members; no tar members are extracted."""
    source = Path(source).absolute()
    before = metadata(source)
    if before.get("cloud_placeholder"):
        return {"source": before, "state": "cloud_placeholder", "originals_modified": False}
    archive_hash = sha256(source)
    directory = Path(output) / "archives" / archive_hash[:16]
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text())
    vault_path = directory / "exported-predictions-and-rankings.jsonl.gz"
    members, row_counts, total_rows = [], Counter(), 0
    with tarfile.open(source, "r|gz") as archive, vault_path.open("xb") as raw_output:
        with gzip.GzipFile(fileobj=raw_output, mode="wb", compresslevel=3, mtime=0) as compressed:
            for member in archive:
                if not member.isfile():
                    continue
                name = Path(member.name).name
                table = name.removesuffix(".gz").removesuffix(".jsonl")
                if table not in TABLES or name not in {table + ".jsonl", table + ".jsonl.gz"}:
                    continue
                # Only the existing sports exports subtree is a logical forecast source.
                parts = Path(member.name).parts
                if "exports" not in parts:
                    continue
                descriptor = {"archive_sha256": archive_hash, "archive_member": member.name,
                              "member_bytes": member.size, "member_mtime": member.mtime,
                              "table": table, "rows": 0, "state": "started"}
                row_counts.setdefault(table, 0)
                source_id = hashlib.sha256(canonical(descriptor)).hexdigest()
                descriptor["source_id"] = source_id
                compressed.write(canonical({"type": "source_begin", "source_id": source_id, "source": descriptor}) + b"\n")
                reader = _DigestReader(archive.extractfile(member))
                stream = gzip.GzipFile(fileobj=reader) if name.endswith(".gz") else reader
                try:
                    while True:
                        line = stream.readline()
                        if not line:
                            break
                        if not line.strip():
                            continue
                        row = json.loads(line)
                        if not isinstance(row, dict):
                            raise ValueError("Exported source row is not a JSON object")
                        descriptor["rows"] += 1
                        total_rows += 1
                        if total_rows % 1000 == 0:
                            ensure_disk_reserve(vault_path)
                        row_counts[table] += 1
                        compressed.write(canonical({"type": "row", "source_id": source_id, "table": table,
                                                    "ordinal": descriptor["rows"], "row_sha256": hashlib.sha256(canonical(row)).hexdigest(),
                                                    "input_line_sha256": hashlib.sha256(line).hexdigest(),
                                                    "archive_member": member.name, "fixture_signals": fixture_signals(row),
                                                    "performance_eligible": False, "row": row}) + b"\n")
                        if total_rows % 250000 == 0:
                            print(json.dumps({"archive_rows_preserved": total_rows, "member": member.name}), flush=True)
                    descriptor["state"] = "complete"
                except (OSError, ValueError, EOFError) as exc:
                    descriptor["state"], descriptor["error"] = "partial", str(exc)
                finally:
                    if stream is not reader:
                        stream.close()
                for _ in iter(lambda: reader.read(1 << 20), b""):
                    pass
                descriptor["member_sha256"] = reader.digest.hexdigest()
                compressed.write(canonical({"type": "source_end", "source_id": source_id, **descriptor}) + b"\n")
                members.append(descriptor)
    after = metadata(source)
    manifest = {"source": before, "source_after": after, "source_metadata_unchanged": before == after,
                "source_id": archive_hash, "archive_sha256": archive_hash, "members": members,
                "logical": {"path": str(vault_path), "sha256": sha256(vault_path), "bytes": vault_path.stat().st_size,
                            "tables": {table: {"rows": count, "state": "complete" if all(m["state"] == "complete" for m in members if m["table"] == table) else "partial"} for table, count in row_counts.items()}},
                "rows": total_rows, "state": "complete" if all(m["state"] == "complete" for m in members) else "partial",
                "originals_modified": False, "production_imports": False,
                "limitations": ["Export-generation duplicates remain separate source observations.", "No forecast has been regraded or assumed independently issued."]}
    with manifest_path.open("x") as handle:
        json.dump(manifest, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, action="append", default=[])
    parser.add_argument("--archive", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prior-core-vault", type=Path)
    parser.add_argument("--snapshot-timeout", type=int, default=300)
    parser.add_argument("--keep-uncompressed", action="store_true")
    parser.add_argument("--immutable-empty-wal", action="store_true", help="For an inactive resident source with an absent/zero-byte WAL; avoid opening cloud SHM")
    args = parser.parse_args(argv)
    if not args.source and not args.archive:
        parser.error("At least one --source or --archive is required")
    args.output.mkdir(parents=True, exist_ok=True)
    prior = prior_core_hashes(args.prior_core_vault)
    summaries = []
    for source in args.source:
        print(json.dumps({"collecting_source": str(source)}), flush=True)
        try:
            result = collect(source, args.output, prior=prior, timeout=args.snapshot_timeout, keep_uncompressed=args.keep_uncompressed, immutable_empty_wal=args.immutable_empty_wal)
        except (OSError, sqlite3.Error, ValueError, TimeoutError, DiskReserveExceeded) as exc:
            result = {"source": str(source), "state": "error", "error": str(exc), "originals_modified": False}
        summaries.append(result)
        print(json.dumps({"source": str(source), "state": result["state"], "directory": str(args.output),
                          "rows": {k: v["rows"] for k, v in result.get("logical", {}).get("tables", {}).items()}}), flush=True)
    for source in args.archive:
        print(json.dumps({"collecting_archive": str(source)}), flush=True)
        result = collect_archive(source, args.output)
        summaries.append(result)
        print(json.dumps({"archive": str(source), "state": result["state"], "rows": result.get("rows", 0)}), flush=True)
    summary = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "sources": summaries,
               "prior_core_vault": str(args.prior_core_vault) if args.prior_core_vault else None,
               "originals_modified": False, "production_imports": False}
    path = args.output / f"collection-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"
    with path.open("x") as handle:
        json.dump(summary, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"collection_manifest": str(path), "source_states": [r["state"] for r in summaries]}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
