"""Configuration helpers (profiles.yaml, CLI overrides)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILES_PATH = PROJECT_ROOT / "profiles.yaml"


@dataclass
class ProfileConfig:
    """Represents a resolved run configuration profile."""

    name: str
    values: Dict[str, Any] = field(default_factory=dict)
    description: Optional[str] = None


class ProfileNotFoundError(RuntimeError):
    pass


def _load_profiles_file(path: Path = DEFAULT_PROFILES_PATH) -> Dict[str, ProfileConfig]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    profiles_section = raw.get("profiles", raw)
    profiles: Dict[str, ProfileConfig] = {}
    for name, body in profiles_section.items():
        if not isinstance(body, dict):
            continue
        description = body.get("description")
        values = {k: v for k, v in body.items() if k != "description"}
        profiles[name] = ProfileConfig(name=name, values=values, description=description)
    return profiles


def list_profiles(path: Path = DEFAULT_PROFILES_PATH) -> Dict[str, ProfileConfig]:
    """Return all available profiles (if the file exists)."""
    return _load_profiles_file(path)


def resolve_profile(
    profile_name: str,
    overrides: Optional[Dict[str, Any]] = None,
    path: Path = DEFAULT_PROFILES_PATH,
) -> Dict[str, Any]:
    """Return a dict merged from the profile plus explicit overrides."""
    profiles = _load_profiles_file(path)
    profile = profiles.get(profile_name)
    if not profile:
        raise ProfileNotFoundError(
            f"Profile '{profile_name}' not found in {path}. "
            "Create it or choose another profile."
        )

    resolved = dict(profile.values)
    if overrides:
        for key, value in overrides.items():
            if value is not None:
                resolved[key] = value
    return resolved


def serialize_overrides(overrides: Dict[str, Any]) -> str:
    """Return a JSON string for logging debug purposes."""
    return json.dumps(overrides, sort_keys=True, default=str)
