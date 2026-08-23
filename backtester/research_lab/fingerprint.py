"""Evaluator fingerprint: sha256 over frozen-evaluator source files.

Stamped into every autoresearch ledger row so "same version number, changed
behavior" is detectable. The version constants (CHECKPOINT_SCRIPT_EVALUATOR_VERSION,
EVAL_CONTRACT_VERSION_WALK_FORWARD) are bumped by humans alongside fingerprint-
changing PRs; a mismatch between consecutive ledger rows with an unchanged
version is drift/tampering and invalidates comparisons.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Files whose behavior defines the evaluator. Order matters for stability.
EVALUATOR_SOURCE_FILES: tuple[str, ...] = (
    "backtester/strategy.py",
    "backtester/pit_models.py",
    "backtester/weighted_walkforward.py",
    "backtester/checkpoint_replay.py",
    "backtester/research_lab/canonical.py",
)


def compute_evaluator_fingerprint(
    root: Path | None = None,
    files: tuple[str, ...] | None = None,
) -> str:
    """Deterministic sha256 over the concatenated bytes of evaluator sources."""
    base = root if root is not None else ROOT
    names = files if files is not None else EVALUATOR_SOURCE_FILES
    digest = hashlib.sha256()
    for name in names:
        path = base / name
        try:
            digest.update(path.name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        except FileNotFoundError:
            # Missing file changes the fingerprint rather than raising, so CI
            # environments that prune files still produce stable values.
            digest.update(b"<missing>")
            digest.update(b"\0")
    return digest.hexdigest()[:32]


def evaluator_identity(
    root: Path | None = None,
    files: tuple[str, ...] | None = None,
) -> dict[str, str]:
    """Return {"evaluator_fingerprint": ...} for stamping into ledger rows/metadata."""
    return {"evaluator_fingerprint": compute_evaluator_fingerprint(root, files)}
