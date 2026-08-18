"""CI workflow must stay syntactically valid and list expected jobs."""

from __future__ import annotations

from pathlib import Path

import yaml

from scripts.validate_ci_workflow import (
    find_forbidden_run_patterns,
    load_manifest,
    validate_workflow,
)

REPO = Path(__file__).resolve().parents[1]
CI_YML = REPO / ".github/workflows" / "ci.yml"


def test_forbidden_heredoc_pattern_detects_invalid_run_form():
    sample = "      - run: python - <<'PY'\n          print(1)\n          PY\n"
    hits = find_forbidden_run_patterns(
        sample,
        [
            r"^\s*-\s*run:\s*python3?\s+-\s*<<",
            r"^\s*run:\s*python3?\s+-\s*<<",
        ],
    )
    assert hits, "validator must reject bare heredoc on run:"


def test_invalid_heredoc_sample_fails_validation(tmp_path: Path):
    manifest = load_manifest()
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
name: Bad
on: push
jobs:
  backend-smoke:
    runs-on: ubuntu-latest
    steps:
      - run: python - <<'PY'
          print(1)
          PY
""".strip()
        + "\n",
        encoding="utf-8",
    )
    errors = validate_workflow(bad, manifest)
    assert any("invalid run heredoc" in err for err in errors)


def test_ci_workflow_parses_and_has_required_jobs():
    manifest = load_manifest()
    errors = validate_workflow(CI_YML, manifest)
    assert errors == [], errors

    doc = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    jobs = doc["jobs"]
    for name in manifest["required_jobs"]:
        assert name in jobs

    first_job = next(iter(jobs))
    assert first_job == "validate-workflow"


def test_ci_workflow_has_no_bare_python_heredoc_run():
    text = CI_YML.read_text(encoding="utf-8")
    hits = find_forbidden_run_patterns(
        text,
        load_manifest()["forbidden_run_patterns"],
    )
    assert hits == [], hits
