"""Tests for port 8000 audit helper."""

from __future__ import annotations

from scripts.port_8000_audit import ListenerInfo, audit_port_8000


def test_audit_passes_with_no_listeners(monkeypatch):
    from scripts import port_8000_audit as mod

    monkeypatch.setattr(mod, "_listener_pids", lambda: [])
    report = mod.audit_port_8000(expected_app_root="/opt/golf-model")
    assert report["ok"] is True
    assert report["listener_count"] == 0


def test_audit_classifies_wrong_root_listener(monkeypatch):
    from scripts import port_8000_audit as mod

    monkeypatch.setattr(mod, "_listener_pids", lambda: [999])
    monkeypatch.setattr(
        mod,
        "classify_listener",
        lambda pid, expected_app_root: ListenerInfo(
            pid=pid,
            cwd="/root/golf-model",
            cmdline="python3 app.py",
            ppid=1,
            systemd_unit=None,
            ok=False,
            reason="wrong root",
        ),
    )
    report = mod.audit_port_8000(expected_app_root="/opt/golf-model")
    assert report["ok"] is False
    assert report["listener_count"] == 1


def test_audit_passes_expected_listener(monkeypatch):
    from scripts import port_8000_audit as mod

    monkeypatch.setattr(mod, "_listener_pids", lambda: [1234])
    monkeypatch.setattr(
        mod,
        "classify_listener",
        lambda pid, expected_app_root: ListenerInfo(
            pid=pid,
            cwd="/opt/golf-model",
            cmdline="python start.py dashboard",
            ppid=1,
            systemd_unit="golf-dashboard.service",
            ok=True,
            reason="expected",
        ),
    )
    report = mod.audit_port_8000(expected_app_root="/opt/golf-model")
    assert report["ok"] is True
