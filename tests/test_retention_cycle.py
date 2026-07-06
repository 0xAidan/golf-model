"""Tests for covering-manifest archive gate (D1)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import src.db as db
from src.cold_archive import (
    export_tick_tables_before_cutoff,
    snapshot_history_cutoff_utc,
    verified_archive_exists_for_cutoff,
)


def test_covering_manifest_newer_than_cutoff_passes(tmp_path, tmp_db, monkeypatch) -> None:
    retain_days = 365
    cutoff = snapshot_history_cutoff_utc(retain_days)
    exports_dir = tmp_path / "exports"
    monkeypatch.setenv("SNAPSHOT_ARCHIVE_EXPORTS_DIR", str(exports_dir))

    export_tick_tables_before_cutoff(
        db_path=tmp_db.DB_PATH,
        cutoff_utc=cutoff,
        output_dir=str(exports_dir),
        retain_days=retain_days,
    )

    # Recompute cutoff a few seconds later — string equality would fail; covering should pass.
    later_cutoff = (datetime.now(timezone.utc) - timedelta(days=retain_days)).replace(microsecond=0).isoformat()
    assert verified_archive_exists_for_cutoff(later_cutoff, exports_dir=exports_dir) is True


def test_older_manifest_does_not_cover_cutoff(tmp_path, tmp_db, monkeypatch) -> None:
    retain_days = 365
    older_cutoff = (datetime.now(timezone.utc) - timedelta(days=retain_days, hours=2)).replace(microsecond=0).isoformat()
    exports_dir = tmp_path / "exports"
    monkeypatch.setenv("SNAPSHOT_ARCHIVE_EXPORTS_DIR", str(exports_dir))

    export_tick_tables_before_cutoff(
        db_path=tmp_db.DB_PATH,
        cutoff_utc=older_cutoff,
        output_dir=str(exports_dir),
        retain_days=retain_days,
    )

    newer_cutoff = snapshot_history_cutoff_utc(retain_days)
    assert verified_archive_exists_for_cutoff(newer_cutoff, exports_dir=exports_dir) is False


def test_retention_cycle_dry_run(tmp_path, tmp_db, monkeypatch) -> None:
    from scripts.run_retention_cycle import run_retention_cycle

    monkeypatch.setenv("SNAPSHOT_HISTORY_RETAIN_DAYS", "365")
    monkeypatch.setenv("SNAPSHOT_ARCHIVE_EXPORTS_DIR", str(tmp_path / "exports"))
    monkeypatch.setattr(
        "src.runtime_paths.get_runtime_identity",
        lambda: {"db_path": tmp_db.DB_PATH},
    )

    out = run_retention_cycle(dry_run=True, retain_days=365)
    assert out["dry_run"] is True
    assert "prune_preview" in out
