#!/usr/bin/env python3
"""One exact-file cloud request batch with bounded resident-only preservation."""

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
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.discover_local_history import Collector


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outcomes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    deadline = started + 120
    prior = json.loads(args.outcomes.read_text())
    targets = [e for e in prior["entries"] if not e["verified_copy_captured"]]
    if len(targets) != 79 or any(
        not e["source_path"].startswith("/Users/aidannugent/Documents/golf-model/") for e in targets
    ):
        raise ValueError("Expected exactly the 79 previously uncaptured original paths")
    if args.output.exists():
        raise FileExistsError("Choose a new additive rescue generation")
    collector = Collector(args.output)
    rows = {
        e["source_path"]: {"source_path": e["source_path"], "expected_bytes": e["requested_bytes"], "captured": False}
        for e in targets
    }
    errors, captured = [], {}

    def timeout(_signal, _frame):
        raise TimeoutError("resident original read timed out")

    signal.signal(signal.SIGALRM, timeout)

    def check_and_capture(name):
        row = rows[name]
        if row["captured"]:
            return
        fd = None
        try:
            p = Path(name)
            info = p.lstat()
            row.update(
                last_flags=hex(getattr(info, "st_flags", 0)),
                last_bytes=info.st_size,
                allocated_bytes=info.st_blocks * 512,
                last_checked_at_utc=datetime.now(timezone.utc).isoformat(),
            )
            if (
                not stat.S_ISREG(info.st_mode)
                or getattr(info, "st_flags", 0) & 0x40000000
                or (info.st_size and not info.st_blocks)
            ):
                row["availability"] = "dataless_or_not_regular"
                return
            if (
                info.st_size > 4 * 1024 * 1024
                or shutil.disk_usage(args.output).free < 1024**3 + info.st_size * 2 + 1024 * 1024
            ):
                row["availability"] = "resident_but_size_or_reserve_blocked"
                return
            signal.setitimer(signal.ITIMER_REAL, min(3, max(0.05, deadline - time.monotonic())))
            fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK)
            before = os.fstat(fd)
            if getattr(before, "st_flags", 0) & 0x40000000 or (before.st_size and not before.st_blocks):
                row["availability"] = "dataless_after_open"
                return
            chunks, length = [], 0
            while length <= 4 * 1024 * 1024:
                chunk = os.read(fd, min(65536, 4 * 1024 * 1024 + 1 - length))
                if not chunk:
                    break
                chunks.append(chunk)
                length += len(chunk)
            after = os.fstat(fd)
            data = b"".join(chunks)
            if (
                len(data) != before.st_size
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
            ):
                row["availability"] = "changed_during_read"
                return
            sha = hashlib.sha256(data).hexdigest()
            metadata = {
                "mtime_ns": before.st_mtime_ns,
                "discovery_method": "targeted_late_cloud_rescue",
                "read_verified_resident": True,
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }
            if p.name.lower().endswith((".md", ".markdown")):
                collector.markdown(data, name, **metadata)
            elif p.name.lower().endswith(".json"):
                collector.structured(data, name, **metadata)
            elif p.name.lower().endswith(".zip"):
                folder = args.output / "containers"
                folder.mkdir(exist_ok=True)
                destination = folder / f"{sha}.zip"
                if not destination.exists():
                    with destination.open("xb") as handle:
                        handle.write(data)
                row["container_copy"] = str(destination)
                collector.zip_bytes(data, name)
            else:
                row["availability"] = "unsupported_target_extension"
                return
            row.update(
                captured=True,
                availability="verified_bytes_captured",
                sha256=sha,
                bytes=len(data),
                captured_at=metadata["captured_at"],
            )
            captured[name] = row
        except (OSError, ValueError, TimeoutError) as exc:
            row["last_error"] = str(exc)
            errors.append({"source": name, "error": str(exc)})
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if fd is not None:
                os.close(fd)

    for name in rows:
        check_and_capture(name)
    requests_started = time.monotonic()
    for i, name in enumerate(rows):
        if rows[name]["captured"]:
            rows[name]["request_state"] = "already_resident_captured"
            continue
        if time.monotonic() >= deadline - 15:
            rows[name]["request_state"] = "not_requested_before_deadline"
            continue
        command = ["brctl", "download", name]
        rows[name]["command"] = command
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, timeout=min(1, max(0.1, deadline - time.monotonic() - 15))
            )
            rows[name].update(
                request_state="accepted" if result.returncode == 0 else "error",
                exit_code=result.returncode,
                stdout=result.stdout[:1000],
                stderr=result.stderr[:1000],
            )
        except subprocess.TimeoutExpired:
            rows[name]["request_state"] = "request_timeout"
        if i and i % 20 == 0:
            print(
                json.dumps(
                    {
                        "elapsed_seconds": round(time.monotonic() - started, 1),
                        "requests_processed": i + 1,
                        "targets_captured": len(captured),
                    }
                ),
                flush=True,
            )
    last_progress = time.monotonic()
    while time.monotonic() < deadline - 2:
        for name in rows:
            if time.monotonic() >= deadline - 2:
                break
            check_and_capture(name)
        if len(captured) == len(rows):
            break
        if time.monotonic() - last_progress >= 25:
            print(
                json.dumps(
                    {
                        "elapsed_seconds": round(time.monotonic() - started, 1),
                        "targets_captured": len(captured),
                        "pending": len(rows) - len(captured),
                    }
                ),
                flush=True,
            )
            last_progress = time.monotonic()
        remaining = deadline - time.monotonic() - 2
        if remaining > 0:
            time.sleep(min(5, remaining))
    collector.save([])
    payloads = [*collector.entries, *collector.structured_entries]
    verification = []
    for source in payloads:
        data = gzip.decompress(Path(source["corpus_path"]).read_bytes())
        if hashlib.sha256(data).hexdigest() != source["sha256"]:
            verification.append({"source": source["source_path"], "error": "copied_payload_hash_mismatch"})
    report = {
        "schema_version": 1,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_outcomes": str(args.outcomes),
        "input_outcomes_sha256": hashlib.sha256(args.outcomes.read_bytes()).hexdigest(),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "max_seconds": 120,
        "targeted_original_paths": len(rows),
        "logical_bytes_targeted": sum(r["expected_bytes"] for r in rows.values()),
        "captured_target_paths": len(captured),
        "pending_target_paths": len(rows) - len(captured),
        "total_original_93_paths_captured": prior["verified_target_source_copies"] + len(captured),
        "markdown_source_references": len(collector.entries),
        "structured_source_references": len(collector.structured_entries),
        "verification_errors": verification,
        "read_errors": errors,
        "free_bytes_after": shutil.disk_usage(args.output).free,
        "entries": list(rows.values()),
        "limits": [
            "Only the exact 79 previously uncaptured original paths were requested. No directory/research download.",
            "Accepted brctl requests are not retrieval proof. Only verified resident bytes count as captured.",
            "All previous manifests and original source files remain unchanged.",
        ],
    }
    (args.output / "late-cloud-rescue-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "entries"}, indent=2), flush=True)


if __name__ == "__main__":
    main()
