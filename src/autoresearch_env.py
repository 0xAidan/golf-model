"""Environment flags for autoresearch / edge search (no heavy imports)."""

from __future__ import annotations

import os


def autoresearch_auto_apply_enabled() -> bool:
    """
    When True, research_cycle may update research champion and approve proposals
    when walk-forward rules pass. Default False: evaluations only (report-only;
    operator merges strategy manually).

    Set AUTORESEARCH_AUTO_APPLY=1 to restore previous auto-promotion behavior.
    """
    v = (os.environ.get("AUTORESEARCH_AUTO_APPLY") or "").strip().lower()
    return v in ("1", "true", "yes", "on")
