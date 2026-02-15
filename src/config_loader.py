"""
Config/Profile Loader

Loads run profiles from profiles.yaml.
Allows different configurations for different tournament types.
"""

import os
import logging

logger = logging.getLogger("config_loader")

DEFAULT_PROFILE = {
    "name": "default",
    "tour": "pga",
    "enable_ai": True,
    "enable_backfill": True,
    "backfill_years": [2024, 2025, 2026],
    "output_dir": "output",
}


def load_profiles(path: str = None) -> dict:
    """Load profiles from YAML file. Returns {name: profile_dict}."""
    if path is None:
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "profiles.yaml")

    if not os.path.exists(path):
        return {"default": DEFAULT_PROFILE}

    try:
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        profiles = {}
        for name, config in data.get("profiles", {}).items():
            profile = DEFAULT_PROFILE.copy()
            profile.update(config)
            profile["name"] = name
            profiles[name] = profile
        if not profiles:
            profiles["default"] = DEFAULT_PROFILE
        return profiles
    except ImportError:
        logger.warning("PyYAML not installed. Using default profile.")
        return {"default": DEFAULT_PROFILE}
    except Exception as e:
        logger.warning(f"Could not load profiles: {e}")
        return {"default": DEFAULT_PROFILE}


def get_profile(name: str = "default") -> dict:
    """Get a specific profile by name."""
    profiles = load_profiles()
    return profiles.get(name, DEFAULT_PROFILE)
