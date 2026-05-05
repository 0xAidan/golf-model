"""Cockpit snapshot (/) vs Lab snapshot (lab_*) model variant defaults."""

from src import config
from src.lab_profile import invalidate_lab_profile_cache, resolve_lab_model_variant


def test_cockpit_snapshot_defaults_to_baseline_for_masters_era_split():
    """Operator boards default to baseline; lab_sandbox stays v5 for research."""
    assert config.COCKPIT_SNAPSHOT_MODEL_VARIANT == "baseline"
    invalidate_lab_profile_cache()
    assert resolve_lab_model_variant("lab_sandbox") == "v5"
    assert resolve_lab_model_variant("lab_sandbox") != config.COCKPIT_SNAPSHOT_MODEL_VARIANT
