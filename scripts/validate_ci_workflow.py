#!/usr/bin/env python3
"""Validate CI workflow YAML syntax and expected job presence.

Fails loudly when GitHub would create zero jobs (invalid `run:` heredoc)
or when required jobs disappear from the manifest.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "PyYAML is required for workflow validation. Install requirements.txt."
    ) from exc

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path(__file__).resolve().parent / "ci" / "expected_jobs.json"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def find_forbidden_run_patterns(text: str, patterns: list[str]) -> list[str]:
    hits: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.MULTILINE):
            line_no = text.count("\n", 0, match.start()) + 1
            hits.append(f"line {line_no}: {match.group(0).strip()}")
    return hits


def validate_workflow(workflow_path: Path, manifest: dict) -> list[str]:
    errors: list[str] = []
    if not workflow_path.is_file():
        return [f"missing workflow file: {workflow_path}"]

    text = workflow_path.read_text(encoding="utf-8")
    errors.extend(
        f"invalid run heredoc ({hit})"
        for hit in find_forbidden_run_patterns(
            text, manifest.get("forbidden_run_patterns", [])
        )
    )

    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        errors.append(f"YAML parse error: {exc}")
        return errors

    if not isinstance(doc, dict):
        errors.append("workflow root must be a mapping")
        return errors

    jobs = doc.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        errors.append("workflow has no jobs; GitHub would create zero checks")
        return errors

    required = manifest.get("required_jobs", [])
    missing = [name for name in required if name not in jobs]
    if missing:
        errors.append(f"missing required jobs: {', '.join(missing)}")

    for name, job in jobs.items():
        if not isinstance(job, dict):
            errors.append(f"job {name!r} is not a mapping")
            continue
        steps = job.get("steps")
        if steps is None:
            continue
        if not isinstance(steps, list) or not steps:
            errors.append(f"job {name!r} has no steps")

    return errors


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    manifest = load_manifest()
    rel = manifest.get("workflow", ".github/workflows/ci.yml")
    workflow_path = REPO_ROOT / rel
    if args:
        workflow_path = Path(args[0]).resolve()

    errors = validate_workflow(workflow_path, manifest)
    if errors:
        print("Workflow validation FAILED:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(
        f"Workflow validation OK: {workflow_path} "
        f"({len(manifest.get('required_jobs', []))} required jobs present)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
