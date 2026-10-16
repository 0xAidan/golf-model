"""Public, sanitized run history derived from immutable research artifacts."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import re


def _digest(value: object) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) else None


def _finite(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _stamp(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value
    except ValueError:
        return None


def build_run_history(output: Path, *, maximum: int = 100, latest_report_sha256: str | None = None) -> dict:
    runs, excluded = [], Counter()
    for path in sorted(output.glob("*/report.json")):
        if (path.parent / "INVALIDATED.json").exists():
            excluded["invalidated_artifact"] += 1
            continue
        try:
            raw = path.read_bytes()
            report = json.loads(raw)
            candidate = report["candidate"]
            generated = _stamp(report.get("generated_at"))
            model_hash = _digest(candidate.get("hash"))
            if generated is None or model_hash is None:
                raise ValueError("Missing dated model identity")
            test = report.get("comparisons", {}).get("test", {})
            metrics = test.get("candidate", {})
            data = report.get("data", {})
            protocol = _digest(report.get("protocol_hash"))
            cohort = report.get("splits", {}).get("test", {}).get("event_ids", [])
            # No cross-protocol or cross-cohort improvement line. A changing
            # source/evaluator can start a new group while preserving old runs.
            comparison = None
            if protocol and cohort and _digest(data.get("source_sha256")):
                identity = [protocol, data["source_sha256"], sorted(cohort),
                            report.get("baseline", {}).get("hash"), candidate.get("ranking_unit")]
                comparison = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            as_of = report.get("as_of")
            try:
                date.fromisoformat(as_of)
            except (ValueError, TypeError):
                as_of = None
            promotion = report.get("promotion", {})
            runs.append({
                "run_id": path.parent.name if re.fullmatch(r"[0-9]{8}-[0-9a-f]{16}", path.parent.name) else model_hash[:16],
                "generated_at": generated, "as_of": as_of, "schema_version": report.get("schema_version"),
                "model_hash": model_hash, "forward_model_hash": _digest(report.get("forward_candidate", {}).get("hash")),
                "report_sha256": hashlib.sha256(raw).hexdigest(), "protocol_hash": protocol,
                "comparison_group": comparison, "state": "completed" if report.get("state") == "evaluated" else "research",
                "events": _finite(metrics.get("events")), "pair_log_loss": _finite(metrics.get("pair_log_loss")),
                "brier": _finite(metrics.get("brier")), "sg_rmse": _finite(metrics.get("sg_rmse")),
                "simple_prior_log_loss": _finite(test.get("naive", {}).get("pair_log_loss")),
                "promotion_eligible": promotion.get("eligible") is True,
                "promotion_status": "eligible_for_review" if promotion.get("eligible") is True else "research_only",
                "test_status": "exposed_retrospective" if "exposed" in str(report.get("protocol", {}).get("test_status")) else "retrospective",
            })
        except (ValueError, TypeError, KeyError, OSError):
            excluded["unavailable_or_unsupported_artifact"] += 1
    runs.sort(key=lambda row: (row["generated_at"], row["run_id"]))
    weeks = {datetime.fromisoformat(row["generated_at"].replace("Z", "+00:00")).isocalendar()[:2] for row in runs}
    total = len(runs)
    return {
        "schema_version": 1, "state": "available" if runs else "unavailable",
        "basis": "Dated research runs; no run was automatically promoted.",
        "latest_report_sha256": _digest(latest_report_sha256),
        "summary": {"total_runs": total, "displayed_runs": min(total, maximum), "weeks_observed": len(weeks),
                    "comparable_groups": len({r["comparison_group"] for r in runs if r["comparison_group"]}),
                    "truncated": total > maximum, "excluded": dict(excluded)},
        "runs": list(reversed(runs[-maximum:])),
        "notes": ["Compare results only within the same protocol, source corpus and event cohort.",
                  "Several development runs on one date are not evidence of improvement over multiple weeks.",
                  "Invalidated artifacts remain preserved privately and are excluded from this view."],
    }


def publish_run_history(output: Path, destination: Path, *, latest_report_sha256: str | None = None) -> dict:
    report = build_run_history(output, latest_report_sha256=latest_report_sha256)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.replace(destination)
    return report
