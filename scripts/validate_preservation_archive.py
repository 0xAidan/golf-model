#!/usr/bin/env python3
"""Stream-validate a completed gzip/tar preservation archive without extraction.

Read the entire gzip stream (including CRC/trailer), parse tar headers, and
SHA256-hash both compressed archive bytes and every regular member's payload.
No application imports or SQLite connections. The archive is never modified.
Only run after the producing transfer has exited successfully.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import tarfile
import time

CHUNK = 8 * 1024 * 1024


class HashingReader:
    def __init__(self, source):
        self.source = source
        self.hash = hashlib.sha256()
        self.bytes_read = 0

    def read(self, size=-1):
        data = self.source.read(size)
        self.hash.update(data)
        self.bytes_read += len(data)
        return data


def validate_archive(archive_path, manifest_path, *, transfer_complete=False, progress_seconds=15):
    archive_path, manifest_path = Path(archive_path), Path(manifest_path)
    if archive_path.name.endswith(".partial") and not transfer_complete:
        raise ValueError("A .partial filename requires --transfer-complete, only after transfer exit 0.")
    if manifest_path.exists() or manifest_path.with_name(manifest_path.name + ".partial").exists():
        raise FileExistsError("Manifest or its staging file already exists; choose a new manifest path.")
    members, types = [], Counter()
    payload_bytes = 0
    started = last_progress = time.monotonic()
    with archive_path.open("rb") as source:
        before = os.fstat(source.fileno())
        reader = HashingReader(source)
        with gzip.GzipFile(fileobj=reader, mode="rb") as compressed:
            with tarfile.open(fileobj=compressed, mode="r|", bufsize=1024 * 1024) as archive:
                for member in archive:
                    kind = member.type.decode("ascii", errors="backslashreplace")
                    types[kind] += 1
                    item = {"path": member.name, "type": kind, "size_bytes": member.size}
                    if member.issym() or member.islnk():
                        item["link_target"] = member.linkname
                    if member.isfile():
                        member_hash, member_bytes = hashlib.sha256(), 0
                        # extractfile exposes a bounded stream; it never creates a file.
                        with archive.extractfile(member) as payload:
                            while chunk := payload.read(CHUNK):
                                member_hash.update(chunk)
                                member_bytes += len(chunk)
                                payload_bytes += len(chunk)
                                now = time.monotonic()
                                if progress_seconds > 0 and now - last_progress >= progress_seconds:
                                    print(f"Validated {payload_bytes:,} regular-member bytes; read {reader.bytes_read:,} compressed bytes.", file=sys.stderr, flush=True)
                                    last_progress = now
                        if member_bytes != member.size:
                            raise ValueError(f"Truncated regular tar member: {member.name}")
                        item.update({"sha256": member_hash.hexdigest(), "validated_payload_bytes": member_bytes})
                    members.append(item)
            # Tar iteration may stop before the gzip footer. Drain to actual EOF
            # so trailing gzip members and the final CRC/length are also checked.
            while compressed.read(CHUNK):
                pass
        after = os.fstat(source.fileno())
    path_after = archive_path.stat()
    def fingerprint(stat):
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns
    if fingerprint(before) != fingerprint(after) or fingerprint(before) != fingerprint(path_after):
        raise ValueError("Archive changed or was replaced during validation; no manifest written.")
    if reader.bytes_read != before.st_size:
        raise ValueError("Validation did not consume the complete compressed archive.")
    manifest = {
        "schema_version": 1, "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "archive": archive_path.name, "size_bytes": before.st_size,
        "sha256": reader.hash.hexdigest(), "gzip_full_crc_read_validated": True,
        "tar_headers_validated": True, "member_count": len(members),
        "regular_member_count": sum("sha256" in member for member in members),
        "member_type_counts": dict(types), "declared_member_bytes": sum(m["size_bytes"] for m in members),
        "validated_regular_payload_bytes": payload_bytes, "source_metadata_unchanged": True,
        "elapsed_seconds": round(time.monotonic() - started, 2), "members": members,
        "limitations": ["Byte/format validation does not establish SQLite integrity, factual correctness or historical completeness.",
                        "Symlinks and hardlinks are inventoried but never followed; only regular member payloads receive SHA256.",
                        "No archive member was extracted and the archive was not renamed or modified."],
    }
    staging = manifest_path.with_name(manifest_path.name + ".partial")
    with staging.open("x", encoding="utf-8") as output:
        json.dump(manifest, output, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    # Exclusive link avoids overwriting a manifest created by another process.
    os.link(staging, manifest_path)
    staging.unlink()
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path, help="New exclusive manifest filename.")
    parser.add_argument("--transfer-complete", action="store_true", help="Permit a .partial name only after its transfer exited 0.")
    parser.add_argument("--progress-seconds", type=float, default=15)
    args = parser.parse_args()
    try:
        report = validate_archive(args.archive, args.manifest, transfer_complete=args.transfer_complete,
                                  progress_seconds=args.progress_seconds)
    except (OSError, EOFError, tarfile.TarError, ValueError) as exc:
        print(f"Validation failed; no final manifest created: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps({key: value for key, value in report.items() if key not in {"members", "limitations"}}, indent=2))
    print(f"Manifest: {args.manifest}")


if __name__ == "__main__":
    main()
