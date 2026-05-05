"""Lab profile resolution from profiles.yaml (parallel snapshot lane)."""

from src.lab_profile import invalidate_lab_profile_cache, resolve_lab_model_variant


def test_lab_sandbox_model_variant_is_v5():
    invalidate_lab_profile_cache()
    assert resolve_lab_model_variant("lab_sandbox") == "v5"


def test_resolve_lab_unknown_profile_falls_back_to_default():
    invalidate_lab_profile_cache()
    assert resolve_lab_model_variant("nonexistent_profile_xyz") in {"v5", "baseline"}
