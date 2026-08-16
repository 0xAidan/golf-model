from __future__ import annotations

import importlib.util
from pathlib import Path


def _load():
    path = Path(__file__).resolve().parents[1] / "scripts" / "external_uptime_watchdog.py"
    spec = importlib.util.spec_from_file_location("external_uptime_watchdog", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_evaluate_ok(monkeypatch) -> None:
    mod = _load()
    monkeypatch.setattr(
        mod,
        "_get",
        lambda url, timeout_seconds: {"ok": True, "status": 200, "error": None, "body_prefix": "ok"},
    )
    result = mod.evaluate(site_url="https://golf.shermandavison.com/", timeout_seconds=1)
    assert result["ok"] is True


def test_evaluate_fails_when_health_down(monkeypatch) -> None:
    mod = _load()

    def _get(url, timeout_seconds):
        if url.endswith("/api/ops/health"):
            return {"ok": False, "status": 502, "error": "bad gateway", "body_prefix": ""}
        return {"ok": True, "status": 200, "error": None, "body_prefix": "html"}

    monkeypatch.setattr(mod, "_get", _get)
    result = mod.evaluate(site_url="https://golf.shermandavison.com/", timeout_seconds=1)
    assert result["ok"] is False
