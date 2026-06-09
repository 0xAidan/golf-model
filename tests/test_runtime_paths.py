"""Tests for canonical runtime path resolution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import runtime_paths


def test_get_data_dir_honors_env(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / "shared-data"
    monkeypatch.setenv("GOLF_DATA_DIR", str(data_dir))
    assert runtime_paths.get_data_dir() == data_dir.resolve()
    assert runtime_paths.get_snapshot_path() == data_dir / "live_refresh_snapshot.json"


def test_db_path_override_wins_over_data_dir(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "custom.db"
    monkeypatch.setenv("GOLF_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GOLF_DB_PATH", str(db_path))
    assert runtime_paths.get_db_path() == db_path.resolve()


def test_detect_split_brain_on_path_mismatch(monkeypatch, tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    heartbeat_path = data_dir / runtime_paths.HEARTBEAT_FILENAME
    heartbeat_path.write_text(
        json.dumps(
            {
                "app_root": "/root/golf-model",
                "data_dir": str(tmp_path / "other-data"),
                "snapshot_path": str(tmp_path / "other-data" / "live_refresh_snapshot.json"),
                "updated_at": "2099-01-01T00:00:00+00:00",
                "running": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GOLF_APP_ROOT", str(tmp_path / "opt"))
    monkeypatch.setenv("GOLF_DATA_DIR", str(data_dir))
    result = runtime_paths.detect_split_brain()
    assert result["split_brain_suspected"] is True
    assert result["reasons"]


def test_live_refresh_worker_owned_defaults_to_production(monkeypatch):
    monkeypatch.delenv("LIVE_REFRESH_WORKER_OWNED", raising=False)
    monkeypatch.setenv("GOLF_APP_ROOT", runtime_paths.CANONICAL_PRODUCTION_APP_ROOT)
    assert runtime_paths.live_refresh_worker_owned() is True

    monkeypatch.setenv("GOLF_APP_ROOT", "/tmp/dev")
    assert runtime_paths.live_refresh_worker_owned() is False
