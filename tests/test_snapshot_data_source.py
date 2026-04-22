"""Unit tests for the snapshot-age / data-source chip fields (Q5)."""

from __future__ import annotations

import re

import pytest


ISO_UTC_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def test_iso_now_is_well_formed_utc():
    from backtester.dashboard_runtime import _iso_now

    value = _iso_now()
    assert isinstance(value, str)
    assert ISO_UTC_RE.match(value), f"generated_at must be ISO 8601 UTC, got: {value}"


def test_data_source_defaults_to_live(monkeypatch):
    from backtester.dashboard_runtime import _resolve_data_source

    for var in ("GOLF_DATA_SOURCE", "GOLF_USE_FIXTURES", "GOLF_REPLAY_MODE"):
        monkeypatch.delenv(var, raising=False)
    assert _resolve_data_source() == "live"


@pytest.mark.parametrize("value", ["live", "replay", "fixture"])
def test_data_source_respects_explicit_override(monkeypatch, value):
    from backtester.dashboard_runtime import _resolve_data_source

    for var in ("GOLF_USE_FIXTURES", "GOLF_REPLAY_MODE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GOLF_DATA_SOURCE", value.upper())  # case-insensitive
    assert _resolve_data_source() == value


def test_data_source_fixture_env_marker(monkeypatch):
    from backtester.dashboard_runtime import _resolve_data_source

    monkeypatch.delenv("GOLF_DATA_SOURCE", raising=False)
    monkeypatch.delenv("GOLF_REPLAY_MODE", raising=False)
    monkeypatch.setenv("GOLF_USE_FIXTURES", "1")
    assert _resolve_data_source() == "fixture"


def test_data_source_replay_env_marker(monkeypatch):
    from backtester.dashboard_runtime import _resolve_data_source

    monkeypatch.delenv("GOLF_DATA_SOURCE", raising=False)
    monkeypatch.delenv("GOLF_USE_FIXTURES", raising=False)
    monkeypatch.setenv("GOLF_REPLAY_MODE", "true")
    assert _resolve_data_source() == "replay"


def test_data_source_unknown_value_falls_back_to_env_flags(monkeypatch):
    from backtester.dashboard_runtime import _resolve_data_source

    monkeypatch.setenv("GOLF_DATA_SOURCE", "bogus")
    monkeypatch.delenv("GOLF_USE_FIXTURES", raising=False)
    monkeypatch.delenv("GOLF_REPLAY_MODE", raising=False)
    assert _resolve_data_source() == "live"


def test_snapshot_payload_contract_includes_timestamp_and_source():
    """Snapshot payloads written for the frontend must expose the two chip fields.

    This is a structural/contract test: it constructs a payload via the same
    fields the runtime uses, then asserts the keys exist and are well-formed.
    """
    from backtester.dashboard_runtime import _iso_now, _resolve_data_source

    payload = {
        "snapshot_id": "test",
        "generated_at": _iso_now(),
        "data_source": _resolve_data_source(),
    }
    assert "generated_at" in payload
    assert ISO_UTC_RE.match(payload["generated_at"])
    assert payload["data_source"] in {"live", "replay", "fixture"}
