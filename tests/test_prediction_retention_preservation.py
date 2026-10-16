"""Regression coverage for preserving original prediction evidence during retention."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from scripts.run_retention_cycle import run_retention_cycle
from src import db
from src.cold_archive import export_tick_tables_before_cutoff, verified_archive_exists_for_cutoff
from src.history_preservation import prediction_history_preservation_enabled

CUTOFF = "2026-01-01T00:00:00+00:00"
OLD = "2020-01-01T00:00:00+00:00"
NEW = "2099-01-01T00:00:00+00:00"


@pytest.fixture
def history_db(tmp_path, monkeypatch):
    path = tmp_path / "history.db"
    with sqlite3.connect(path) as conn:
        for table in ("live_snapshot_history", "market_prediction_rows"):
            conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, generated_at TEXT, payload_json TEXT)")
        conn.execute("CREATE TABLE pick_ledger (id INTEGER PRIMARY KEY, lifecycle TEXT)")
        conn.execute("INSERT INTO pick_ledger VALUES (1, 'generated')")
    monkeypatch.setattr(db, "DB_PATH", str(path))
    monkeypatch.setenv("SNAPSHOT_ARCHIVE_EXPORTS_DIR", str(tmp_path / "exports"))
    monkeypatch.setattr("src.runtime_paths.get_runtime_identity", lambda: {"db_path": str(path)})
    return path


def seed(path, *, timestamp=OLD, payload='{"player":"A","prob":0.5}'):
    with sqlite3.connect(path) as conn:
        for table in ("live_snapshot_history", "market_prediction_rows"):
            conn.execute(f"INSERT INTO {table} (generated_at, payload_json) VALUES (?, ?)", (timestamp, payload))


def row_counts(path):
    with sqlite3.connect(path) as conn:
        return tuple(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("live_snapshot_history", "market_prediction_rows"))


def archive(path, tmp_path, *, cutoff=CUTOFF):
    return export_tick_tables_before_cutoff(db_path=str(path), cutoff_utc=cutoff, output_dir=tmp_path / "exports")


@pytest.mark.parametrize("value", [None, "", "1", "true", "yes", "on", "unexpected", " Falsey "])
def test_preservation_is_the_fail_closed_default(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    else:
        monkeypatch.setenv("PRESERVE_PREDICTION_HISTORY", value)
    assert prediction_history_preservation_enabled()


@pytest.mark.parametrize("value", ["0", "false", "no", "off", " OFF "])
def test_only_explicit_values_disable_preservation(monkeypatch, value):
    monkeypatch.setenv("PRESERVE_PREDICTION_HISTORY", value)
    assert not prediction_history_preservation_enabled()


def test_default_guards_run_before_database_initialization(monkeypatch, tmp_path):
    from src.ops_jobs import remove_stale_db_recovery_copies, run_storage_cleanup
    from src.pick_ledger import prune_generated_pick_ledger
    from src.storage_janitor import sweep_backup_temp_dir, sweep_disposable_storage, sweep_os_tmp_leftovers
    from backtester.dashboard_runtime import _maybe_prune_snapshot_history_tables

    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    def forbidden(*args, **kwargs):
        raise AssertionError("preservation must return before DB initialization or maintenance")
    monkeypatch.setattr(db, "ensure_initialized", forbidden)
    monkeypatch.setattr(db, "get_conn", forbidden)
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "does-not-exist.db"))
    monkeypatch.setenv("STORAGE_BACKUP_TMP_DIR", str(tmp_path / "must-not-be-created"))
    assert db.prune_live_snapshot_history(1) == 0
    assert db.prune_market_prediction_rows(1) == 0
    assert db.prune_snapshot_history_tables(1)["preservation_enabled"]
    assert prune_generated_pick_ledger()["deleted"] == 0
    assert run_storage_cleanup()["preservation_enabled"]
    assert remove_stale_db_recovery_copies(db.DB_PATH) == []
    for sweep in (sweep_backup_temp_dir, sweep_disposable_storage, sweep_os_tmp_leftovers):
        assert sweep()["preservation_enabled"]
    assert run_retention_cycle(retain_days=1)["preservation_enabled"]
    snapshot = {}
    _maybe_prune_snapshot_history_tables(snapshot)
    assert snapshot["diagnostics"]["history_prune"]["preservation_enabled"]
    assert not Path(db.DB_PATH).exists()
    assert not (tmp_path / "must-not-be-created").exists()


def test_default_preserves_rows_even_with_valid_archive(history_db, tmp_path, monkeypatch):
    seed(history_db)
    archive(history_db, tmp_path)
    monkeypatch.setenv("PRESERVE_PREDICTION_HISTORY", "true")
    assert db.prune_snapshot_history_tables(1, cutoff_utc=CUTOFF)["skipped"]
    assert row_counts(history_db) == (1, 1)


def test_empty_archive_cannot_authorize_later_backfill(history_db, tmp_path, monkeypatch):
    archive(history_db, tmp_path)
    seed(history_db)
    monkeypatch.setenv("PRESERVE_PREDICTION_HISTORY", "0")
    assert not verified_archive_exists_for_cutoff(CUTOFF, exports_dir=tmp_path / "exports", db_path=str(history_db))
    result = db.prune_snapshot_history_tables(1, require_archive=False, cutoff_utc=CUTOFF)
    assert result["skipped"] and not result["archive_verified"]
    assert row_counts(history_db) == (1, 1)


def test_nonempty_archive_cannot_authorize_later_backfill(history_db, tmp_path, monkeypatch):
    seed(history_db)
    archive(history_db, tmp_path)
    seed(history_db, payload='{"player":"B"}')
    monkeypatch.setenv("PRESERVE_PREDICTION_HISTORY", "0")
    assert db.prune_snapshot_history_tables(1, cutoff_utc=CUTOFF)["skipped"]
    assert row_counts(history_db) == (2, 2)


def test_wrong_database_with_identical_rows_is_rejected(history_db, tmp_path):
    seed(history_db)
    archive(history_db, tmp_path)
    other = tmp_path / "other.db"
    other.write_bytes(history_db.read_bytes())
    assert not verified_archive_exists_for_cutoff(CUTOFF, exports_dir=tmp_path / "exports", db_path=str(other))
    assert not verified_archive_exists_for_cutoff(CUTOFF, exports_dir=tmp_path / "exports")


def test_same_count_but_changed_payload_is_rejected(history_db, tmp_path):
    seed(history_db)
    archive(history_db, tmp_path)
    with sqlite3.connect(history_db) as conn:
        conn.execute("UPDATE live_snapshot_history SET payload_json = '{\"changed\":true}'")
    assert not verified_archive_exists_for_cutoff(CUTOFF, exports_dir=tmp_path / "exports", db_path=str(history_db))


def test_modified_manifest_is_rejected(history_db, tmp_path):
    seed(history_db)
    result = archive(history_db, tmp_path)
    manifest_path = Path(result["manifest_path"])
    manifest = json.loads(manifest_path.read_text())
    manifest["tables"]["live_snapshot_history"]["file"] = "../../outside.jsonl"
    unsigned = {k: v for k, v in manifest.items() if k != "checksum"}
    manifest["checksum"] = hashlib.sha256(json.dumps(unsigned, indent=2, sort_keys=True).encode()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    assert not verified_archive_exists_for_cutoff(CUTOFF, exports_dir=tmp_path / "exports", db_path=str(history_db))


def test_verification_and_delete_share_write_lock(history_db, tmp_path, monkeypatch):
    seed(history_db)
    seed(history_db, timestamp=NEW)
    archive(history_db, tmp_path)
    monkeypatch.setenv("PRESERVE_PREDICTION_HISTORY", "0")
    original = verified_archive_exists_for_cutoff
    observed = []
    def verify(*args, **kwargs):
        assert kwargs["connection"].in_transaction
        with sqlite3.connect(history_db, timeout=0.01) as second:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                second.execute("INSERT INTO live_snapshot_history (generated_at) VALUES (?)", (OLD,))
        observed.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr("src.cold_archive.verified_archive_exists_for_cutoff", verify)
    result = db.prune_snapshot_history_tables(1, cutoff_utc=CUTOFF)
    assert observed == [True]
    assert not result["skipped"]
    assert result["live_snapshot_history_deleted"] == result["market_prediction_rows_deleted"] == 1
    assert row_counts(history_db) == (1, 1)


def test_dry_run_is_read_only_even_with_valid_archive(history_db, tmp_path, monkeypatch):
    seed(history_db)
    archive(history_db, tmp_path, cutoff="2100-01-01T00:00:00+00:00")
    monkeypatch.setenv("PRESERVE_PREDICTION_HISTORY", "0")
    def forbidden(*args, **kwargs):
        raise AssertionError("dry run cannot initialize, rotate, export, or vacuum")
    monkeypatch.setattr(db, "ensure_initialized", forbidden)
    monkeypatch.setattr(db, "get_conn", forbidden)
    monkeypatch.setattr(db, "reclaim_database_disk", forbidden)
    monkeypatch.setattr("src.output_manager.rotate_research_artifacts", forbidden)
    monkeypatch.setattr("src.cold_archive.export_tick_tables_before_cutoff", forbidden)
    before = hashlib.sha256(history_db.read_bytes()).hexdigest()
    files_before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    result = run_retention_cycle(retain_days=1, dry_run=True, vacuum=True)
    assert result["prune_preview"]["dry_run"]
    assert result["prune_preview"]["rows_pending_delete"] == 2
    assert result["prune_preview"]["archive_verified"]
    assert result["prune_preview"]["live_snapshot_history_deleted"] == 0
    assert row_counts(history_db) == (1, 1)
    assert hashlib.sha256(history_db.read_bytes()).hexdigest() == before
    assert sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")) == files_before


def test_direct_pruners_cannot_bypass_archive_requirement(history_db, monkeypatch):
    seed(history_db)
    monkeypatch.setenv("PRESERVE_PREDICTION_HISTORY", "0")
    monkeypatch.setenv("SNAPSHOT_PRUNE_REQUIRE_ARCHIVE", "0")
    assert db.prune_live_snapshot_history(1) == 0
    assert db.prune_market_prediction_rows(1) == 0
    assert row_counts(history_db) == (1, 1)


def test_generated_ledger_retained_without_its_own_rowset_archive(history_db, monkeypatch):
    from src.pick_ledger import prune_generated_pick_ledger
    monkeypatch.setenv("PRESERVE_PREDICTION_HISTORY", "0")
    assert prune_generated_pick_ledger(dry_run=True)["would_delete"] == 1
    result = prune_generated_pick_ledger()
    assert result["skipped"] and result["deleted"] == 0
    with sqlite3.connect(history_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM pick_ledger").fetchone()[0] == 1


def test_export_never_replaces_an_existing_archive(history_db, tmp_path):
    seed(history_db)
    first = archive(history_db, tmp_path)
    first_path = Path(first["manifest_path"])
    before = first_path.read_bytes()
    second = archive(history_db, tmp_path)
    assert first["export_dir"] != second["export_dir"]
    assert first_path.read_bytes() == before


def test_retention_cycle_refuses_different_runtime_database(history_db, monkeypatch, tmp_path):
    monkeypatch.setenv("PRESERVE_PREDICTION_HISTORY", "0")
    monkeypatch.setattr("src.runtime_paths.get_runtime_identity", lambda: {"db_path": str(tmp_path / "different.db")})
    result = run_retention_cycle(retain_days=1, dry_run=True)
    assert result["skipped"] and "differs" in result["reason"]
    assert not (tmp_path / "different.db").exists()


def test_read_only_preview_includes_uncheckpointed_wal(history_db, tmp_path, monkeypatch):
    monkeypatch.setenv("PRESERVE_PREDICTION_HISTORY", "0")
    writer = sqlite3.connect(history_db)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("INSERT INTO live_snapshot_history (generated_at, payload_json) VALUES (?, '{}')", (OLD,))
        writer.commit()
        archive(history_db, tmp_path)
        wal = Path(str(history_db) + "-wal")
        before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in (history_db, wal)]
        result = db.prune_snapshot_history_tables(1, dry_run=True, cutoff_utc=CUTOFF)
        assert result["rows_pending_delete"] == 1
        assert result["archive_verified"] is True
        assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in (history_db, wal)] == before
    finally:
        writer.close()


def test_atomic_delete_failure_rolls_back_and_reports_zero(history_db, tmp_path, monkeypatch):
    seed(history_db)
    with sqlite3.connect(history_db) as conn:
        conn.execute("""CREATE TRIGGER prevent_market_delete BEFORE DELETE ON market_prediction_rows
                        BEGIN SELECT RAISE(ABORT, 'retain original'); END""")
    archive(history_db, tmp_path)
    monkeypatch.setenv("PRESERVE_PREDICTION_HISTORY", "0")
    result = db.prune_snapshot_history_tables(1, cutoff_utc=CUTOFF)
    assert not result["ok"] and result["skipped"]
    assert result["live_snapshot_history_deleted"] == result["market_prediction_rows_deleted"] == 0
    assert row_counts(history_db) == (1, 1)


def test_missing_database_is_not_initialized_even_after_opt_out(tmp_path, monkeypatch):
    path = tmp_path / "missing.db"
    monkeypatch.setattr(db, "DB_PATH", str(path))
    monkeypatch.setenv("PRESERVE_PREDICTION_HISTORY", "0")
    for preview in (True, False):
        result = db.prune_snapshot_history_tables(1, dry_run=preview)
        assert result["skipped"] and not result["ok"]
        assert not path.exists()



def test_direct_compaction_and_reclaim_preserve_all_source_generations(tmp_path, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    live = tmp_path / "golf.db"
    compacted = tmp_path / "golf.db.vacuum_into"
    before_copy = tmp_path / "golf.db.pre_reclaim"
    for path, payload in ((live, b"original database"), (compacted, b"candidate database"),
                          (before_copy, b"earlier preserved generation")):
        path.write_bytes(payload)
    before = {path.name: path.read_bytes() for path in (live, compacted, before_copy)}
    monkeypatch.setattr(db, "DB_PATH", str(live))
    def forbidden(*args, **kwargs):
        raise AssertionError("default preservation must precede DB or maintenance operations")
    monkeypatch.setattr(db, "get_conn", forbidden)
    monkeypatch.setattr(db, "vacuum_database", forbidden)
    monkeypatch.setattr("src.disk_guard.warn_if_low_disk", forbidden)
    swap = db.swap_compacted_database(str(live), str(compacted))
    reclaim = db.reclaim_database_disk(min_free_mb=1)
    for result in (swap, reclaim):
        assert result["ok"] and result["skipped"] and result["preservation_enabled"]
        assert result["bytes_reclaimed"] == 0
    assert {path.name: path.read_bytes() for path in (live, compacted, before_copy)} == before
    assert {path.name for path in tmp_path.iterdir()} == set(before)
