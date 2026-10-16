#!/usr/bin/env python3
"""Train/evaluate the additive shadow challenger without changing live models or data.

Example:
    python3 scripts/train_learning_challenger.py --source data/research/corpus.jsonl.gz \
        --snapshot data/research/live_refresh_snapshot.json --as-of 2026-10-16
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtester.learning_challenger import load_source, save_artifacts, train_and_evaluate


def source_freshness(output: Path, forward: dict) -> dict:
    pointer = output / "latest.json"
    previous = json.loads(pointer.read_text()) if pointer.is_file() else {}
    fallback = f"{previous.get('run_id')}/forward-model.json"
    path = output / previous.get("forward_model", fallback)
    prior = json.loads(path.read_text()) if path.is_file() and not (path.parent / "INVALIDATED.json").exists() else None
    if prior is not None:
        added = sorted(set(forward["training_event_ids"]) - set(prior.get("training_event_ids", [])))
        state = "new_completed_events" if added else "no_new_completed_events"
    else:
        added, state = [], "integrity_repair_refit" if previous.get("state") == "invalidated" else "first_recorded_forward_refit"
    return {"state": state, "new_completed_events": len(added), "event_ids": added,
            "latest_completed": forward["trained_through"], "previous_run_id": previous.get("run_id"),
            "message": ("This refit repairs data identity; it does not establish fresh completed-event learning."
                        if state == "integrity_repair_refit" else
                        "No new completed events; this refresh does not establish fresh learning."
                        if state == "no_new_completed_events" else None)}


def current_field_input(tables: dict, snapshot: dict, as_of: str) -> dict:
    """Resolve a dated tour/year field; recurring event IDs cannot choose a future venue."""
    from src.models.learning_challenger import day

    section = snapshot.get("upcoming_tournament") or snapshot.get("live_tournament") or {}
    event_id = str(section.get("source_event_id") or section.get("event_id") or "")
    eligibility = section.get("eligibility")
    eligibility = eligibility if isinstance(eligibility, dict) else {}
    explicit_tour = str(section.get("tour") or "").strip().lower()
    observed_tour = str(eligibility.get("observed_tour") or "").strip().lower()
    scope = explicit_tour or observed_tour or None
    stamp = snapshot.get("generated_at")
    captured, cutoff = day(stamp), day(as_of)
    base = {"event_id": event_id, "event_name": section.get("event_name"), "as_of": as_of,
            "tour": scope, "year": None, "snapshot_generated_at": stamp, "players": [],
            "state": "withheld", "reason": "unresolved_dated_event_identity"}
    if explicit_tour and observed_tour and explicit_tour != observed_tour:
        return {**base, "reason": "contradictory_tour_identity"}
    if scope != "pga":
        return {**base, "reason": "unsupported_or_missing_tour_identity"}
    if (eligibility.get("verified") is not True or section.get("verification_error")
            or section.get("active") is False):
        return {**base, "reason": "unverified_event_field"}
    failures = eligibility.get("failed_invariants", [])
    if not isinstance(failures, list) or failures:
        return {**base, "reason": "failed_field_invariants"}
    if not event_id or str(eligibility.get("field_event_id") or "").strip() != event_id:
        return {**base, "reason": "unverified_field_event_identity"}
    if not captured or not cutoff or scope != "pga" or not 0 <= (cutoff - captured).days <= 7:
        return base
    explicit_year = section.get("year", section.get("event_year"))
    candidates = []
    for row in tables.get("historical_event_info", []):
        start = day(row.get("start_date"))
        year = int(row.get("year") or 0)
        if (str(row.get("event_id")) != event_id or str(row.get("tour") or "").strip().lower() != scope
                or start is None or start.year != year or not captured - timedelta(days=7) <= start <= captured + timedelta(days=42)):
            continue
        if explicit_year is not None and str(explicit_year) != str(year):
            continue
        candidates.append(row)
    if len(candidates) != 1:
        return base
    event = candidates[0]
    course = str(event.get("course_id") or "")
    course = course if course and not any(separator in course for separator in (";", ",")) else None
    return {**base, "year": int(event["year"]), "calendar_start": str(event["start_date"]),
            "identity_basis": "explicit_year_and_dated_calendar" if explicit_year is not None else "unique_calendar_within_dated_snapshot_window",
            "course_num": course, "players": section.get("rankings", []), "state": "resolved", "reason": None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Read-only SQLite database or .jsonl.gz export")
    parser.add_argument("--snapshot", help="Optional recorded live-refresh snapshot to project the current field")
    parser.add_argument("--as-of", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--output", type=Path, default=Path("output/learning"))
    parser.add_argument("--public-report", type=Path, help="Optional sanitized, read-only product report destination")
    parser.add_argument("--protocol", choices=("legacy", "recovered-v2"), default="legacy")
    parser.add_argument("--seed-cache", type=Path, help="Verified historical-round cache to merge with current weekly SQLite rounds")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / ".training.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"state": "already_running"}))
            return 0
        tables, manifest = load_source(args.source, include_quotes=args.protocol == "legacy")
        if args.seed_cache:
            from backtester.learning_corpus import add_snapshot_references, deduplicate

            seed, historical = load_source(args.seed_cache, include_quotes=False)
            add_snapshot_references(tables, manifest)
            for table in ("rounds", "historical_event_info"):
                seed.setdefault(table, []).extend(tables.get(table, []))
            tables, manifest = deduplicate(seed, historical.get("origins", []) + [manifest])
        elif args.protocol == "recovered-v2":
            from backtester.learning_corpus import add_snapshot_references, deduplicate

            add_snapshot_references(tables, manifest)
            tables, manifest = deduplicate(tables, manifest.get("origins", [manifest]))
        cache = args.seed_cache or (Path(args.source) if str(args.source).endswith(".gz") else None)
        if cache:
            with cache.open("rb") as handle:
                manifest["research_cache"] = {"path": str(cache), "sha256": hashlib.file_digest(handle, "sha256").hexdigest()}
        current = None
        if args.snapshot:
            snapshot = json.loads(Path(args.snapshot).read_text())
            current = current_field_input(tables, snapshot, args.as_of)
        forward = None
        if args.protocol == "recovered-v2":
            from backtester.learning_challenger_v2 import train
            from backtester.learning_corpus import preserve_training_snapshot

            manifest["training_snapshot"] = preserve_training_snapshot(args.output, tables, manifest)
            report, model, predictions, baseline, forward = train(tables, manifest, as_of=args.as_of, current_field=current)
            report["learning"]["source_freshness"] = source_freshness(args.output, forward)
        else:
            report, model, predictions, baseline = train_and_evaluate(tables, manifest, as_of=args.as_of, current_field=current)
        inputs = {"field-projection-input.json": Path(args.snapshot)} if args.snapshot else {}
        if args.protocol == "recovered-v2":
            from backtester.learning_challenger_v2 import PROTOCOL_PATH

            inputs["pinned-protocol-input.json"] = PROTOCOL_PATH
            inputs["training-source.jsonl.gz"] = Path(manifest["training_snapshot"]["path"])
        destination = save_artifacts(args.output, report, model, predictions, baseline, manifest, forward_model=forward, input_files=inputs)
        # Read back the immutable artifact: an idempotent rerun publishes the original report.
        report = json.loads((destination / "report.json").read_text())
        if args.public_report:
            args.public_report.parent.mkdir(parents=True, exist_ok=True)
            temp = args.public_report.with_suffix(".json.tmp")
            temp.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
            temp.replace(args.public_report)
            from src.learning_run_history import publish_run_history

            publish_run_history(args.output, args.public_report.with_name("learning-history.json"),
                                latest_report_sha256=hashlib.sha256(args.public_report.read_bytes()).hexdigest())
        print(json.dumps({"state": report["state"], "artifact_dir": str(destination.resolve()),
                          "candidate_hash": report["candidate"]["hash"], "forward_hash": report.get("forward_candidate", {}).get("hash"),
                          "splits": {k: {field: value for field, value in split.items() if field != "event_ids"} for k, split in report["splits"].items()},
                          "test_log_loss": {k: v.get("pair_log_loss") for k, v in report["comparisons"]["test"].items()},
                          "source_freshness": report["learning"].get("source_freshness"),
                          "current_rankings": len(report["current_rankings"]), "promotion": report["promotion"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
