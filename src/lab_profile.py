"""Resolve lab sandbox profile keys from ``profiles.yaml`` (operator parallel snapshot lane)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from src import config

_PROFILES_PATH = Path(__file__).resolve().parent.parent / "profiles.yaml"


@lru_cache(maxsize=1)
def _load_profiles_raw() -> dict[str, Any]:
    if not _PROFILES_PATH.is_file():
        return {}
    try:
        with open(_PROFILES_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def get_profile(name: str) -> dict[str, Any]:
    """Return a profile dict from ``profiles:`` root, or empty dict."""
    root = _load_profiles_raw()
    profiles = root.get("profiles") if isinstance(root.get("profiles"), dict) else {}
    key = (name or "").strip() or "lab_sandbox"
    prof = profiles.get(key)
    return dict(prof) if isinstance(prof, dict) else {}


def resolve_lab_model_variant(profile_name: str) -> str:
    """
    Model variant used for parallel lab snapshot recompute.

    Only values in ``config.ALLOWED_MODEL_VARIANTS`` are returned; otherwise
    ``DEFAULT_MODEL_VARIANT``.
    """
    prof = get_profile(profile_name)
    raw = str(prof.get("model_variant") or config.DEFAULT_MODEL_VARIANT).strip().lower()
    if raw in config.ALLOWED_MODEL_VARIANTS:
        return raw
    return str(config.DEFAULT_MODEL_VARIANT).strip().lower() or "v5"


def invalidate_lab_profile_cache() -> None:
    """Test helper."""
    _load_profiles_raw.cache_clear()
