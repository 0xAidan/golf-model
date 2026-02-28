"""
Feature flags loaded from YAML.

All new code paths (dynamic blend, exposure, Kelly, CLV, etc.) must check
flags here so features can be toggled or killed without code deploy.
"""

import os
import logging

logger = logging.getLogger(__name__)

_FLAGS: dict[str, bool] = {}
_LOADED = False


def _load_flags() -> dict[str, bool]:
    global _LOADED, _FLAGS
    if _LOADED:
        return _FLAGS
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "feature_flags.yaml")
    if os.path.exists(path):
        try:
            import yaml
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            _FLAGS = {k: bool(v) for k, v in data.items() if isinstance(v, (bool, int))}
        except Exception as e:
            logger.warning("Could not load feature_flags.yaml: %s", e)
    _LOADED = True
    return _FLAGS


def is_enabled(flag_name: str) -> bool:
    """Return True if the feature flag is enabled, False otherwise."""
    flags = _load_flags()
    return flags.get(flag_name, False)


def get_all() -> dict[str, bool]:
    """Return current flag state (for debugging)."""
    return _load_flags().copy()
