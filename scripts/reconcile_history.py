#!/usr/bin/env python3
"""Create a new reconciliation generation from read-only core vaults."""
import argparse
import csv
import gzip
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.history_reconciliation import canonical, digest, file_hash, load_vault, reconcile, write_store  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--vault", action="append", required=True)
    p.add_argument("--calendar", required=True)
    p.add_argument("--cards")
    p.add_argument("--lineage", help="Compact ledger provenance; candidates never become pick foreign keys")
    p.add_argument("--artifact", action="append", default=[], help="Additional original artifact to hash, not read as rows")
    p.add_argument("--output", required=True, help="New directory; existing paths are refused")
    p.add_argument("--as-of", default="2026-10-14")
    args = p.parse_args()
    output = Path(args.output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    input_paths = [Path(x) for x in args.vault] + [Path(args.calendar)] + ([Path(args.cards)] if args.cards else []) + ([Path(args.lineage)] if args.lineage else []) + [Path(x) for x in args.artifact]
    artifacts = [{"name": str(path), "sha256": file_hash(path), "bytes": path.stat().st_size} for path in input_paths]
    vault = {"sources": {}, "streams": {}, "rows": []}
    for name in args.vault:
        part = load_vault(name)
        if set(vault["sources"]) & set(part["sources"]):
            raise ValueError("Duplicate source generation across input vaults")
        vault["sources"].update(part["sources"])
        vault["streams"].update(part["streams"])
        vault["rows"].extend(part["rows"])
    calendar = json.loads(Path(args.calendar).read_text())["entries"]
    cards = [json.loads(line) for line in Path(args.cards).read_text().splitlines()] if args.cards else []
    lineage = []
    if args.lineage:
        with gzip.open(args.lineage, "rt") as f:
            lineage = [json.loads(line) for line in f]
    decisions, report, links = reconcile(vault, calendar, cutoff=args.as_of, cards=cards, lineage=lineage)
    from src.selection_evidence import MIN_TRAIN_EVENTS, MIN_VALIDATION_EVENTS, MIN_VALIDATION_DECISIONS, PROTOCOL_ID, evaluate_selection
    evaluations, rules = [], []
    lane_names = {"cockpit": "dashboard", "lab_sandbox": "lab"}
    scopes = sorted({(d["lane"], d["market"], str(d.get("model_variant") or "unknown")) for d in decisions})
    for lane, market, variant in scopes:
        scoped = [d for d in decisions if (d["lane"], d["market"], str(d.get("model_variant") or "unknown")) == (lane, market, variant)]
        evaluation = evaluate_selection(scoped, cutoff=args.as_of)
        evaluations.append({"lane": lane, "market": market, "model_variant": variant, "evaluation": evaluation})
        for c in evaluation["comparisons"]:
            sufficient = c["comparison_state"] == "retrospective_only"
            rules.append({"id": c["rule"], "label": c["label"], "lane": lane_names.get(lane, lane), "market": market,
                          "model_variant": variant, "earlier_events": c["earlier_events"]["events"],
                          "eligible_decisions": evaluation["cohort"]["eligible_decisions"], "eligible_events": evaluation["cohort"]["eligible_events"],
                          "later_events": c["later_events"]["events"], "later_decisions": c["later_events"]["decisions"],
                          "later_roi": c["later_events"]["unit_roi"] if sufficient else None,
                          "roi_interval": c["bounds"].get("unit_roi_95") if sufficient else None, "sufficient": sufficient})
    report["selection"] = {"status": "retrospective_only" if any(r["sufficient"] for r in rules) else "insufficient",
                           "message": "No rule promoted. Each market, lane and model version is evaluated separately. More independently recorded events are needed before changing pick selection.",
                           "protocol_id": PROTOCOL_ID, "minimum_earlier_events": MIN_TRAIN_EVENTS,
                           "minimum_later_events": MIN_VALIDATION_EVENTS, "minimum_later_decisions": MIN_VALIDATION_DECISIONS, "rules": rules}
    (output / "selection-evaluation.json").write_text(json.dumps(evaluations, indent=2) + "\n")
    for artifact in artifacts:
        if file_hash(artifact["name"]) != artifact["sha256"]:
            raise ValueError("An input changed while reconciling")
    code = {}
    code_dir = output / "implementation"
    code_dir.mkdir()
    repo_root = Path(__file__).resolve().parents[1]
    for name in ("scripts/reconcile_history.py", "src/history_reconciliation.py", "src/selection_evidence.py"):
        source_code = (repo_root / name).read_bytes()
        (code_dir / Path(name).name).write_bytes(source_code)
        code[name] = file_hash(repo_root / name)
    report["provenance"] = {"source_manifest_sha256": digest(artifacts), "calendar_sha256": file_hash(args.calendar), "implementation_sha256": digest(code)}
    report["provenance"]["report_id"] = digest(report)
    write_store(output / "reconciliation.sqlite", vault, decisions, links, artifacts)
    with (output / "decisions.jsonl").open("x") as f:
        for row in decisions:
            f.write(canonical(row) + "\n")
    fields = ["decision_id", "event_name", "event_start", "event_end", "market", "lane", "player_display", "opponent_display",
              "book", "odds", "probability", "ev", "model_variant", "model_config_hash", "recorded_at", "recorded_times",
              "status", "settlement", "profit", "stake", "issues", "chronology", "included_in_paper_record",
              "eligible_for_retrospective_selection", "observation_count", "source_count"]
    with (output / "season-2026-decisions.csv").open("x", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for d in decisions:
            row = {key: canonical(d[key]) if isinstance(d[key], (list, dict)) else d[key] for key in fields}
            row["lane"] = lane_names.get(row["lane"], row["lane"])
            # Text cells cannot execute spreadsheet formulas. Numeric odds remain numeric.
            for key, value in row.items():
                if isinstance(value, str) and value[:1] in {"=", "+", "-", "@", "\t", "\r"}:
                    row[key] = "'" + value
            writer.writerow(row)
    (output / "season-2026.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "manifest.json").write_text(json.dumps({"inputs": artifacts, "implementation": code, "report": report["provenance"], "counts": report["coverage"], "original_inputs_unchanged": True}, indent=2) + "\n")
    print(json.dumps({"output": str(output), "coverage": report["coverage"]}, indent=2))


if __name__ == "__main__":
    main()
