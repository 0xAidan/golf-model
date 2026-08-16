"""Strict auto-recover refuses anything that is not confirmed corruption."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load(name: str, filename: str):
    path = Path(__file__).resolve().parents[1] / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_evaluate_recover_only_on_corrupt(monkeypatch) -> None:
    mod = _load("db_integrity_watchdog", "db_integrity_watchdog.py")
    monkeypatch.setattr(
        mod,
        "probe_live_database",
        lambda timeout_seconds=8.0: {"ok": False, "state": "busy", "error": "locked"},
    )
    result = mod.evaluate()
    assert result["recover"] is False
    assert result["alert"] is False

    monkeypatch.setattr(
        mod,
        "probe_live_database",
        lambda timeout_seconds=8.0: {
            "ok": False,
            "state": "corrupt",
            "error": "database disk image is malformed",
        },
    )
    result = mod.evaluate()
    assert result["recover"] is True
    assert result["alert"] is True


def test_recover_refuses_non_corrupt(monkeypatch) -> None:
    mod = _load("auto_recover_db", "auto_recover_db.py")
    monkeypatch.setattr(
        mod,
        "probe_live_database",
        lambda timeout_seconds=8.0: {"ok": False, "state": "timeout", "error": "timed out"},
    )
    report = mod.recover(dry_run=True)
    assert report["ok"] is False
    assert "not 'corrupt'" in str(report.get("error"))
