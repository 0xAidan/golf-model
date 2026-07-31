"""Regression test for the operator-baseline schema guard."""

from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_operator_baseline_schema_check_passes() -> None:
    """The committed baseline declares every required, captured metric."""
    result = subprocess.run(
        ["node", "frontend/scripts/capture-operator-baseline.mjs", "--check-schema"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
