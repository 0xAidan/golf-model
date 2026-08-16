"""Tests for scripts/disk_watchdog.py evaluate thresholds."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "disk_watchdog.py"
    spec = importlib.util.spec_from_file_location("disk_watchdog", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_evaluate_warn_floor(monkeypatch, tmp_path):
    mod = _load_module()
    monkeypatch.setattr(
        mod,
        "get_disk_state",
        lambda _path: {
            "free_mb": 8000,
            "warn_mb": 10240,
            "hard_mb": 5120,
            "state": "warn",
            "guard_state": "warn",
            "path": str(tmp_path),
        },
    )
    monkeypatch.setattr(mod, "get_app_root", lambda: tmp_path)
    result = mod.evaluate(str(tmp_path))
    assert result["alert"] is True
    assert result["severity"] == "warn"


def test_evaluate_healthy(monkeypatch, tmp_path):
    mod = _load_module()
    monkeypatch.setattr(
        mod,
        "get_disk_state",
        lambda _path: {
            "free_mb": 40000,
            "warn_mb": 10240,
            "hard_mb": 5120,
            "state": "healthy",
            "guard_state": "ok",
            "path": str(tmp_path),
        },
    )
    monkeypatch.setattr(mod, "get_app_root", lambda: tmp_path)
    result = mod.evaluate(str(tmp_path))
    assert result["alert"] is False
    assert result["severity"] == "info"
