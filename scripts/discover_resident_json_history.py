#!/usr/bin/env python3
"""Bounded resident-only JSON forecast discovery from existing filename lists."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.discover_local_history import Collector, EXCLUDED, NAME_HINT, SECRET_HINT
from scripts.discover_resident_markdown_history import GOLF_CONTEXT

MAX_FILE = 2 * 1024 * 1024
MAX_COPIED = 20 * 1024 * 1024
RESERVE = 1024**3
PLAYER_KEYS = {"player", "player_key", "player_display", "player_name", "name", "pick", "pick_key", "golfer", "dg_id"}
FORECAST_KEYS = {
    "model_prob",
    "model_win_prob",
    "win_prob",
    "win_probability",
    "probability",
    "composite",
    "odds",
    "market_odds",
    "ev_prob",
    "ev",
}
ARRAY_KEYS = {
    "rankings",
    "pre_tournament_rankings",
    "frozen_pre_teeoff_rankings",
    "live_rankings",
    "predictions",
    "picks",
    "bets",
    "top_picks",
    "matchups",
    "matchup_bets",
    "matchup_bets_all_books",
    "market_rows",
    "value_bets",
}


def forecast_arrays(payload):
    arrays, event_evidence = [], False

    def walk(obj, pointer="", parent="", depth=0):
        nonlocal event_evidence
        if depth > 12:
            return
        if isinstance(obj, dict):
            if any(k in obj for k in ("event_name", "tournament_name", "event_id", "tournament_id", "tournament")):
                event_evidence = True
            for key, value in obj.items():
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                walk(value, pointer + "/" + escaped, str(key), depth + 1)
        elif isinstance(obj, list):
            candidates = [r for r in obj if isinstance(r, dict)]
            supported = any(PLAYER_KEYS.intersection(r) and FORECAST_KEYS.intersection(r) for r in candidates)
            if supported and (parent in ARRAY_KEYS or "/value_bets/" in pointer):
                arrays.append({"json_pointer": pointer, "rows": len(obj)})
            else:
                for i, item in enumerate(obj):
                    if isinstance(item, (dict, list)):
                        walk(item, pointer + "/" + str(i), parent, depth + 1)

    walk(payload)
    return arrays if event_evidence else []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paths-json", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=90)
    parser.add_argument("--roots", action="append", choices=("Documents", "Downloads", "Desktop", "Projects"))
    args = parser.parse_args()
    seconds = max(1, min(90, args.seconds))
    started = time.monotonic()
    deadline = started + seconds
    if args.output.exists():
        raise FileExistsError("Choose a new additive generation")
    collector = Collector(args.output)
    paths = set()
    inputs = []
    for path in args.paths_json:
        raw = path.read_bytes()
        items = json.loads(gzip.decompress(raw) if path.name.endswith(".gz") else raw)
        paths.update(items)
        inputs.append({"path": str(path), "listed_paths": len(items), "sha256": hashlib.sha256(raw).hexdigest()})
    selected_roots = args.roots or ["Documents", "Downloads", "Desktop", "Projects"]
    roots = [Path.home() / p for p in selected_roots]
    candidates = sorted(
        p for p in paths if p.lower().endswith(".json") and any(Path(p).is_relative_to(r) for r in roots)
    )
    counts = Counter()
    by_root = defaultdict(Counter)
    errors = []
    matches = []
    copied = 0
    last = time.monotonic()

    def count(key, path):
        counts[key] += 1
        by_root[Path(path).relative_to(Path.home()).parts[0]][key] += 1

    def timeout(_signum, _frame):
        raise TimeoutError("resident JSON read timed out")

    signal.signal(signal.SIGALRM, timeout)
    for text in candidates:
        if time.monotonic() >= deadline - 2:
            counts["deadline_reached"] = 1
            break
        count("listed_json_considered", text)
        if (
            SECRET_HINT.search(text)
            or any(f"/{p}/" in text for p in EXCLUDED)
            or any(s in text for s in ("/golf-model-preservation/", "/golf-model-reconciliation/", ".app/"))
        ):
            count("excluded_path", text)
            continue
        fd = None
        signal.setitimer(signal.ITIMER_REAL, min(2, max(0.05, deadline - time.monotonic() - 1)))
        try:
            p = Path(text)
            s = p.lstat()
            if not stat.S_ISREG(s.st_mode):
                count("skipped_nonregular_or_symlink", text)
                continue
            if s.st_size > MAX_FILE:
                count("skipped_over_2MiB", text)
                continue
            if getattr(s, "st_flags", 0) & 0x40000000 or (s.st_size and not s.st_blocks):
                count("skipped_dataless_without_read", text)
                continue
            fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_NONBLOCK)
            before = os.fstat(fd)
            if getattr(before, "st_flags", 0) & 0x40000000 or (before.st_size and not before.st_blocks):
                count("skipped_dataless_after_open", text)
                continue
            data = b""
            while len(data) <= MAX_FILE:
                chunk = os.read(fd, min(65536, MAX_FILE + 1 - len(data)))
                if not chunk:
                    break
                data += chunk
            after = os.fstat(fd)
            if (
                len(data) != before.st_size
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
            ):
                count("skipped_changed_during_read", text)
                continue
            count("resident_content_read", text)
            counts["resident_bytes_read"] += len(data)
            content = data.decode("utf-8", errors="replace")
            if not (GOLF_CONTEXT.search(content) or NAME_HINT.search(content)):
                count("resident_negative_content", text)
                continue
            try:
                payload = json.loads(data)
            except (ValueError, UnicodeError):
                count("resident_invalid_json", text)
                continue
            arrays = forecast_arrays(payload)
            if not arrays:
                count("resident_negative_content", text)
                continue
            sha = hashlib.sha256(data).hexdigest()
            row = {"source_path": text, "sha256": sha, "bytes": len(data), "forecast_arrays": arrays}
            if (
                copied + len(data) > MAX_COPIED
                or shutil.disk_usage(args.output).free < RESERVE + len(data) * 2 + 1024 * 1024
            ):
                count("matched_but_copy_cap_or_reserve_blocked", text)
                row["copied"] = False
                matches.append(row)
                continue
            collector.structured(
                data,
                text,
                mtime_ns=before.st_mtime_ns,
                discovery_method="resident_json_content_search",
                read_verified_resident=True,
                content_classification="saved_golf_forecast_arrays_publication_unverified",
                matched_forecast_arrays=arrays,
            )
            copied += len(data)
            row["copied"] = True
            matches.append(row)
            count("golf_forecast_json_preserved", text)
        except (OSError, ValueError, TimeoutError) as exc:
            count("metadata_or_read_error", text)
            errors.append({"source": text, "error": str(exc)})
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            if fd is not None:
                os.close(fd)
            if time.monotonic() - last >= 35:
                print(
                    json.dumps({"elapsed_seconds": round(time.monotonic() - started, 1), "counts": counts}), flush=True
                )
                last = time.monotonic()
    collector.save([])
    report = {
        "schema_version": 1,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only_resident_json_no_hydration_or_new_listings",
        "inputs": inputs,
        "candidate_json_files": len(candidates),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "max_seconds": seconds,
        "selected_roots": selected_roots,
        "logical_copy_cap_bytes": MAX_COPIED,
        "logical_bytes_copied": copied,
        "counts": dict(counts),
        "by_home_root": {k: dict(v) for k, v in sorted(by_root.items())},
        "matches": matches,
        "errors": errors,
        "free_bytes_after": shutil.disk_usage(args.output).free,
        "limitations": [
            "Only listed resident regular non-symlink JSON <=2MiB in Documents/Downloads/Desktop/Projects was eligible.",
            "Dependencies, secret paths, chat stores and recovery outputs excluded. No cloud downloads or new filesystem listings.",
            "Only golf-context saved forecast arrays with event evidence were copied; unknown/root-array schemas may remain unindexed.",
            "The retained filename listings were bounded/partial, so this is not exhaustive filesystem coverage.",
        ],
    }
    (args.output / "resident-json-scan-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
