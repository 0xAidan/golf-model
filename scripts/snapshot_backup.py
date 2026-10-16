#!/usr/bin/env python3
"""Append a verified SQLite backup without importing or modifying the application."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
import uuid

MIB = 1024 * 1024
CHUNK = MIB


class BackupError(RuntimeError):
    """A safe, operator-readable backup failure."""


def _gzip_bound(size: int) -> int:
    # Gzip can expand incompressible input. Reserve stored-block overhead plus
    # a full MiB margin instead of relying on previous compression ratios.
    return size + (size // 16384 + 1) * 5 + MIB


class _Budget:
    def __init__(self, directory: Path, *, reserve_bytes: int, timeout_seconds: float):
        self.directory = directory
        self.reserve_bytes = reserve_bytes
        self.deadline = time.monotonic() + timeout_seconds

    def check(self, needed_bytes: int = 0):
        if time.monotonic() >= self.deadline:
            raise BackupError("Backup time limit exceeded.")
        if shutil.disk_usage(self.directory).free < self.reserve_bytes + needed_bytes:
            raise BackupError("Backup refused: insufficient free space for the remaining footprint and reserve.")


def _verify_database(connection: sqlite3.Connection, budget: _Budget):
    def interrupt_if_expired():
        return int(time.monotonic() >= budget.deadline)

    connection.set_progress_handler(interrupt_if_expired, 10000)
    for pragma in ("quick_check", "integrity_check"):
        budget.check()
        if connection.execute(f"PRAGMA {pragma}").fetchone() != ("ok",):
            raise BackupError("Destination database failed integrity verification.")
    connection.set_progress_handler(None, 0)


def _compress_and_verify(source: Path, destination: Path, budget: _Budget) -> tuple[str, str, int]:
    source_hash = hashlib.sha256()
    size = source.stat().st_size
    consumed = 0
    with source.open("rb") as raw, destination.open("xb") as compressed:
        os.fchmod(compressed.fileno(), 0o600)
        with gzip.GzipFile(filename="", mode="wb", fileobj=compressed, compresslevel=6, mtime=0) as gz:
            while chunk := raw.read(CHUNK):
                budget.check(_gzip_bound(size - consumed))
                source_hash.update(chunk)
                gz.write(chunk)
                consumed += len(chunk)
        compressed.flush()
        os.fsync(compressed.fileno())

    restored_hash = hashlib.sha256()
    restored_bytes = 0
    with gzip.open(destination, "rb") as restored:
        while chunk := restored.read(CHUNK):
            budget.check()
            restored_hash.update(chunk)
            restored_bytes += len(chunk)
    if restored_bytes != size or restored_hash.digest() != source_hash.digest():
        raise BackupError("Compressed backup failed round-trip verification.")

    compressed_hash = hashlib.sha256()
    with destination.open("rb") as compressed:
        while chunk := compressed.read(CHUNK):
            budget.check()
            compressed_hash.update(chunk)
    return source_hash.hexdigest(), compressed_hash.hexdigest(), size


def _publish_new(source: Path, destination: Path):
    # Same-filesystem hard-link publication is atomic and fails if the final
    # filename already exists. os.replace would silently overwrite evidence.
    os.link(source, destination)


def create_snapshot_backup(
    source: Path,
    output_dir: Path,
    *,
    reserve_mib: int = 512,
    min_free_mib: int = 5120,
    timeout_seconds: float = 600,
) -> dict:
    """Copy via SQLite's backup API, validate a private copy, then append files.

    The live source is opened read-only with WAL honored. Only this invocation's
    private temporary directory is cleaned. Published files and older backups
    are never deleted, rotated, replaced, restored, or migrated.
    """
    source, output_dir = Path(source), Path(output_dir)
    if not source.is_absolute() or not output_dir.is_absolute():
        raise BackupError("Source and output paths must be absolute.")
    if reserve_mib < 0 or min_free_mib < 0 or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise BackupError("Invalid reserve, free-space floor, or time limit.")
    if not source.is_file():
        raise BackupError("Source database is unavailable; no database was created.")
    if not output_dir.is_dir():
        raise BackupError("Backup output directory must already exist.")

    budget = _Budget(output_dir, reserve_bytes=reserve_mib * MIB, timeout_seconds=timeout_seconds)
    budget.check()
    if shutil.disk_usage(output_dir).free < min_free_mib * MIB:
        raise BackupError("Backup refused: free space is below the initial hard floor.")
    created_at = datetime.now(timezone.utc)
    name = f"golf_model_{created_at:%Y%m%d_%H%M%S_%f}_{uuid.uuid4().hex[:12]}.db.gz"
    target = output_dir / name
    sidecar = output_dir / f"{name}.integrity.json"
    source_connection = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=min(5.0, timeout_seconds))
    try:
        source_connection.execute("PRAGMA query_only=ON")
        page_size = int(source_connection.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(source_connection.execute("PRAGMA page_count").fetchone()[0])
        size_estimate = page_size * page_count
        budget.check(size_estimate + _gzip_bound(size_estimate))

        with tempfile.TemporaryDirectory(prefix=".golf_snapshot_", dir=output_dir) as workspace:
            temporary = Path(workspace)
            copy_path = temporary / "snapshot.sqlite"
            destination = sqlite3.connect(copy_path)
            try:
                def progress(_status, remaining, total):
                    budget.check(remaining * page_size + _gzip_bound(total * page_size))

                source_connection.backup(destination, pages=1024, progress=progress, sleep=0.05)
                # This is the private destination only. Make it standalone even
                # if the source's copied page header originally used WAL mode.
                destination.execute("PRAGMA journal_mode=DELETE")
                _verify_database(destination, budget)
            finally:
                destination.close()
            source_connection.close()
            source_connection = None

            gzip_path = temporary / "snapshot.db.gz"
            raw_hash, gzip_hash, raw_size = _compress_and_verify(copy_path, gzip_path, budget)
            checked_at = datetime.now(timezone.utc).isoformat()
            manifest = {
                "ok": True,
                "quick_check": "ok",
                "integrity_check": "ok",
                "path": str(target),
                "checked_at": checked_at,
                "written_at": checked_at,
                "uncompressed_bytes": raw_size,
                "compressed_bytes": gzip_path.stat().st_size,
                "sha256": gzip_hash,
                "sqlite_sha256": raw_hash,
                "source_path": str(source),
                "source_read_only": True,
                "method": "sqlite_backup_api",
                "compression_round_trip_verified": True,
                "created_at": created_at.isoformat(),
            }
            manifest_path = temporary / "integrity.json"
            with manifest_path.open("x", encoding="utf-8") as handle:
                os.fchmod(handle.fileno(), 0o600)
                json.dump(manifest, handle, indent=2, allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            budget.check()
            _publish_new(gzip_path, target)
            # If this second publication fails, retain the complete verified
            # gzip; never delete an already-published backup to hide a failure.
            _publish_new(manifest_path, sidecar)
            directory_fd = os.open(output_dir, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return manifest
    finally:
        if source_connection is not None:
            source_connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reserve-mib", type=int, default=512)
    parser.add_argument("--min-free-mib", type=int, default=5120)
    parser.add_argument("--timeout-seconds", type=float, default=600)
    args = parser.parse_args()
    try:
        report = create_snapshot_backup(
            args.source, args.output_dir, reserve_mib=args.reserve_mib,
            min_free_mib=args.min_free_mib, timeout_seconds=args.timeout_seconds,
        )
    except Exception as exc:
        reason = str(exc) if isinstance(exc, BackupError) else f"Backup failed ({type(exc).__name__})."
        print(json.dumps({"ok": False, "reason": reason}), file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
