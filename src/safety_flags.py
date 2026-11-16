"""Switches for automatic behaviours that are off until evaluation is sound.

These live outside ``src/config.py`` on purpose: that file is hash-pinned as part
of the frozen "original model" comparator (``config/model-baselines``), and these
switches do not change how the model prices anything.

Both default to OFF. Set the environment variable to 1/true/yes/on to enable.
"""

from __future__ import annotations

import os

_ON = frozenset({"1", "true", "yes", "on"})

AUTO_RETUNE_ENV = "AUTO_RETUNE_ENABLED"
ADAPTATION_FREEZE_ENV = "ADAPTATION_FREEZE_ENABLED"


def _enabled(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in _ON


def auto_retune_enabled() -> bool:
    """Automatic weight changes after grading.

    The global retune fits to as few as 10 picks and the per-course update to as
    few as 5, and both ran after every grading sweep. The operator retune
    endpoint and CLI are not affected by this switch.
    """
    return _enabled(AUTO_RETUNE_ENV)


def adaptation_freeze_enabled() -> bool:
    """Market suppression (the "frozen" adaptation state).

    A frozen market places no bets, so its losing streak and rolling ROI can
    never recover: the freeze is permanent. With this off the worst state is
    "cold" (higher EV bar, reduced stake).
    """
    return _enabled(ADAPTATION_FREEZE_ENV)
