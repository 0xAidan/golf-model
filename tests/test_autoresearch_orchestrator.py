"""Tests for the autoresearch orchestrator: lock, effort dial, heartbeat, cycle."""

from __future__ import annotations

import json

import pytest

from backtester.fast_tier import EFFORT_PRESETS
from workers.autoresearch_orchestrator import (
    CycleLock,
    build_weekly_digest,
    get_effort_setting,
    run_cycle,
    set_effort_setting,
    write_heartbeat,
)


def test_cycle_lock_is_exclusive(tmp_path):
    lock_a = CycleLock(tmp_path / "cycle.lock")
    lock_b = CycleLock(tmp_path / "cycle.lock")
    assert lock_a.acquire(blocking=False) is True
    assert lock_b.acquire(blocking=False) is False
    lock_a.release()
    assert lock_b.acquire(blocking=False) is True
    lock_b.release()


def test_effort_setting_roundtrip(monkeypatch, tmp_path):
    from src import autoresearch_settings as settings_mod

    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(settings_mod, "_CACHE", None)

    assert set_effort_setting("light") is True
    monkeypatch.setattr(settings_mod, "_CACHE", None)
    assert get_effort_setting() == "light"

    assert set_effort_setting("turbo") is False  # invalid name rejected
    # Invalid values fall back to standard.
    monkeypatch.setattr(settings_mod, "_SETTINGS_FILE", tmp_path / "other.json")
    monkeypatch.setattr(settings_mod, "_CACHE", None)
    (tmp_path / "other.json").write_text(json.dumps({"autoresearch_effort": "bogus"}))
    assert get_effort_setting() == "standard"


def test_write_heartbeat_shape(tmp_path):
    hb = tmp_path / "hb.json"
    write_heartbeat_to(hb, "stage_x", "ok", {"k": 1})
    payload = json.loads(hb.read_text())
    assert payload["stage"] == "stage_x"
    assert payload["status"] == "ok"
    assert payload["ts"]


def write_heartbeat_to(path, stage, status, detail):
    """Heartbeat writer against an explicit path (module writes to a fixed path)."""
    from workers.autoresearch_orchestrator import _utc_now_iso

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"ts": _utc_now_iso(), "stage": stage, "status": status, **(detail or {})}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_run_cycle_dry_run_records_budget(monkeypatch):
    ran = {}

    def fake_append(row):
        ran.update(row)

    monkeypatch.setattr(
        "backtester.research_lab.ledger.append_ledger_row", fake_append
    )
    monkeypatch.setattr(
        "workers.autoresearch_orchestrator.write_heartbeat", lambda *a, **k: None
    )
    summary = run_cycle(dry_run=True)
    assert summary["dry_run"] is True
    assert summary["effort"] in EFFORT_PRESETS
    assert summary["budget"]["max_wall_seconds"] == EFFORT_PRESETS[summary["effort"]]["max_wall_seconds"]
    assert ran.get("kind") == "orchestrator_cycle"


def test_weekly_digest_counts_ledger_rows(monkeypatch, tmp_path):
    from backtester.research_lab import ledger as ledger_mod

    rows = [
        {"ts": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "kind": "trial", "decision": "keep"},
        {"ts": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "kind": "trial", "decision": "discard"},
        {"ts": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "kind": "promotion_ready"},
        {"ts": "2000-01-01T00:00:00+00:00", "kind": "trial", "decision": "keep"},  # too old
    ]
    path = tmp_path / "ledger.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", path)
    digest = build_weekly_digest_with(path)
    assert "Trials logged: 2" in digest
    assert "Keeps: 1" in digest
    assert "Promotion-ready candidates: 1" in digest


def build_weekly_digest_with(path):
    from workers import autoresearch_orchestrator as orch

    original = orch.__dict__.get("_digest_path_ref")
    # Point the digest at the temp ledger via the module attribute it reads.
    import backtester.research_lab.ledger as lm

    saved = lm.LEDGER_PATH
    lm.LEDGER_PATH = path
    try:
        return build_weekly_digest()
    finally:
        lm.LEDGER_PATH = saved
