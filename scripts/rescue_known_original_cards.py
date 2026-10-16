#!/usr/bin/env python3
"""Observe only inventoried small original card paths after native downloads."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.discover_local_history import Collector


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--outcomes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    deadline = started + 90
    allowed = {
        "/Users/aidannugent/Documents/golf-model/output/archive",
        "/Users/aidannugent/Documents/golf-model/output/md cards",
    }
    inventory = [json.loads(line) for line in args.inventory.read_text().splitlines()]
    native = {r["path"]: r["bytes"] for r in inventory if str(Path(r["path"]).parent) in allowed}
    if len(native) != 75 or sum(native.values()) != 821007:
        raise ValueError("Expected the verified 75 original paths / 821007 bytes")
    prior = json.loads(args.outcomes.read_text())
    scoped = {e["source_path"]: e["requested_bytes"] for e in prior["entries"] if not e["verified_copy_captured"]}
    scoped.update(native)
    if sum(scoped.values()) > 1.5 * 1024 * 1024:
        raise ValueError("Known original scope exceeds the 1.5 MiB cap")
    if args.output.exists():
        raise FileExistsError("Choose a new additive generation")
    collector = Collector(args.output)
    rows = {
        name: {"source_path": name, "expected_bytes": size, "native_folder_original": name in native, "captured": False}
        for name, size in scoped.items()
    }
    errors = []
    last = time.monotonic()

    def alarm(_signal, _frame):
        raise TimeoutError("resident original read timeout")

    signal.signal(signal.SIGALRM, alarm)

    def capture(name):
        row = rows[name]
        if row["captured"]:
            return
        fd = None
        try:
            path = Path(name)
            s = path.lstat()
            row.update(
                last_flags=hex(getattr(s, "st_flags", 0)), allocated_bytes=s.st_blocks * 512, last_bytes=s.st_size
            )
            if not stat.S_ISREG(s.st_mode) or getattr(s, "st_flags", 0) & 0x40000000 or (s.st_size and not s.st_blocks):
                return
            if (
                s.st_size > 1.5 * 1024 * 1024
                or shutil.disk_usage(args.output).free < 1024**3 + s.st_size * 2 + 1024 * 1024
            ):
                return
            signal.setitimer(signal.ITIMER_REAL, min(3, max(0.05, deadline - time.monotonic())))
            fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK)
            before = os.fstat(fd)
            if getattr(before, "st_flags", 0) & 0x40000000 or (before.st_size and not before.st_blocks):
                return
            data = b""
            while len(data) <= 1.5 * 1024 * 1024:
                chunk = os.read(fd, min(65536, int(1.5 * 1024 * 1024) + 1 - len(data)))
                if not chunk:
                    break
                data += chunk
            after = os.fstat(fd)
            if (
                len(data) != before.st_size
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
            ):
                return
            sha = hashlib.sha256(data).hexdigest()
            metadata = {
                "mtime_ns": before.st_mtime_ns,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "discovery_method": "known_originals_native_download_followup",
                "read_verified_resident": True,
            }
            suffix = path.name.lower()
            if suffix.endswith((".md", ".markdown")):
                collector.markdown(data, name, **metadata)
            elif suffix.endswith(".json"):
                collector.structured(data, name, **metadata)
            elif suffix.endswith(".zip"):
                folder = args.output / "containers"
                folder.mkdir(exist_ok=True)
                copy = folder / f"{sha}.zip"
                if not copy.exists():
                    with copy.open("xb") as handle:
                        handle.write(data)
                row["container_copy"] = str(copy)
                try:
                    collector.zip_bytes(data, name)
                except (zipfile.BadZipFile, ValueError, OSError) as exc:
                    errors.append({"source": name, "error": f"Preserved container; member parse: {exc}"})
            else:
                return
            row.update(captured=True, sha256=sha, bytes=len(data), captured_at=metadata["captured_at"])
        except (OSError, ValueError, TimeoutError) as exc:
            errors.append({"source": name, "error": str(exc)})
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if fd is not None:
                os.close(fd)

    while time.monotonic() < deadline - 2:
        for name in rows:
            if time.monotonic() >= deadline - 2:
                break
            capture(name)
        captured = sum(r["captured"] for r in rows.values())
        if captured == len(rows):
            break
        if time.monotonic() - last >= 25:
            print(
                json.dumps(
                    {
                        "elapsed_seconds": round(time.monotonic() - started, 1),
                        "all_captured": captured,
                        "native75_captured": sum(r["captured"] for r in rows.values() if r["native_folder_original"]),
                    }
                ),
                flush=True,
            )
            last = time.monotonic()
        remaining = deadline - time.monotonic() - 2
        if remaining > 0:
            time.sleep(min(5, remaining))
    collector.save([])
    validation = []
    for row in [*collector.entries, *collector.structured_entries]:
        raw = gzip.decompress(Path(row["corpus_path"]).read_bytes())
        if hashlib.sha256(raw).hexdigest() != row["sha256"]:
            validation.append({"source": row["source_path"], "error": "hash mismatch"})
    report = {
        "schema_version": 1,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "max_seconds": 90,
        "known_original_paths": len(rows),
        "known_original_bytes": sum(scoped.values()),
        "native_folder_paths": 75,
        "native_folder_bytes": 821007,
        "native_folder_captured": sum(r["captured"] for r in rows.values() if r["native_folder_original"]),
        "captured_paths": sum(r["captured"] for r in rows.values()),
        "pending_paths": sum(not r["captured"] for r in rows.values()),
        "markdown_source_references": len(collector.entries),
        "structured_source_references": len(collector.structured_entries),
        "validation_errors": validation,
        "errors": errors,
        "free_bytes_after": shutil.disk_usage(args.output).free,
        "entries": list(rows.values()),
        "limits": [
            "Only the already inventoried 75 native folder files plus 79 previously uncaptured exact targets were checked.",
            "No filesystem listing, hydration request, research directory download, original source write or prior manifest mutation.",
        ],
    }
    (args.output / "native-originals-rescue-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "entries"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
