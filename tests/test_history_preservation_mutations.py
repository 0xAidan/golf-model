"""Original forecast files, backup generations and outcome versions survive maintenance."""

import gzip
import json
import os
import time

from src import backup, output_manager
from src.history_preservation import preserve_pick_outcome_versions
from src.official_pick_record import dedupe_picks_by_grading_identity


def test_original_backups_and_orphan_wal_are_retained_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    monkeypatch.setattr(backup, "BACKUP_DIR", str(tmp_path))
    files = [tmp_path / "golf_model_20260101_120000.db", tmp_path / "golf_model_20260201_120000.db", tmp_path / "golf_model_20250101_120000.db-wal"]
    for path in files:
        path.write_bytes(path.name.encode())
    originals = {path.name: path.read_bytes() for path in files}
    assert backup.prune_old_backups(1) == []
    assert backup.sweep_orphan_sidecars() == []
    assert {path.name: path.read_bytes() for path in files} == originals


def test_new_backups_remain_functional_without_rotating_old_generations(tmp_db, tmp_path, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    monkeypatch.setattr(backup, "BACKUP_DIR", str(tmp_path))
    first = backup.create_backup(keep=1)
    second = backup.create_backup(keep=1, compress=True)
    assert first != second
    assert os.path.isfile(first) and os.path.isfile(second)
    assert backup.verify_backup_integrity(first)["ok"]
    assert backup.verify_backup_integrity(second)["ok"]


def test_archive_card_never_overwrites_different_original_and_reuses_identical_copy(tmp_path, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    source = tmp_path / "event_20260101.md"
    source.write_text("new original prediction")
    archive = tmp_path / "archive"
    archive.mkdir()
    older = archive / source.name
    older.write_text("earlier original prediction")
    assert output_manager.archive_previous(str(tmp_path), "event") == 1
    assert source.read_text() == "new original prediction"
    assert older.read_text() == "earlier original prediction"
    assert {p.read_text() for p in archive.glob("*.md")} == {"new original prediction", "earlier original prediction"}
    output_manager.archive_previous(str(tmp_path), "event")
    assert len(list(archive.glob("*.md"))) == 2


def test_research_rotation_preserves_sources_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    research = tmp_path / "research"
    research.mkdir()
    source = research / "study.json"
    source.write_text('{"original":1}')
    stale = time.time() - 120 * 86400
    os.utime(source, (stale, stale))
    result = output_manager.rotate_research_artifacts(research_dir=research, archive_dir=tmp_path / "archive")
    assert result["skipped"] and result["preservation_enabled"]
    assert source.read_text() == '{"original":1}'


def test_explicit_rotation_keeps_distinct_nested_versions_with_same_basename(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESERVE_PREDICTION_HISTORY", "0")
    research = tmp_path / "research"
    stale = time.time() - 120 * 86400
    for directory, text in [("first", "first original"), ("second", "second original")]:
        source = research / directory / "ledger.jsonl"
        source.parent.mkdir(parents=True)
        source.write_text(text)
        os.utime(source, (stale, stale))
    archive = tmp_path / "archive"
    result = output_manager.rotate_research_artifacts(research_dir=research, archive_dir=archive)
    assert result["archived_count"] == 2
    texts = []
    for path in archive.rglob("*.gz"):
        with gzip.open(path, "rt") as handle:
            texts.append(handle.read())
    assert set(texts) == {"first original", "second original"}


def _originals(tmp_db):
    tournament = tmp_db.get_or_create_tournament("Original Open", year=2026, event_id="13")
    conn = tmp_db.get_conn()
    conn.execute("DROP INDEX idx_picks_unique")
    ids = []
    for odds in ("+500", "+600"):
        cursor = conn.execute("""INSERT INTO picks
            (tournament_id,model_variant,source,bet_type,market_type,player_key,player_display,opponent_key,market_odds,model_prob,ev)
            VALUES (?,'baseline','cockpit','outright','outright','rory_mcilroy','Rory McIlroy','',?,0.2,0.2)""", (tournament, odds))
        ids.append(cursor.lastrowid)
        conn.execute("INSERT INTO pick_outcomes(pick_id,hit,profit,stake,outcome_locked) VALUES(?,0,-1,1,0)", (cursor.lastrowid,))
    conn.commit()
    return tournament, conn, ids


def test_startup_and_grading_dedupe_cannot_erase_original_picks_or_outcomes(tmp_db, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    _, conn, ids = _originals(tmp_db)
    before_picks = [dict(r) for r in conn.execute("SELECT * FROM picks ORDER BY id")]
    before_outcomes = [dict(r) for r in conn.execute("SELECT * FROM pick_outcomes ORDER BY id")]
    tmp_db._migrate_picks_unique_index(conn)
    assert dedupe_picks_by_grading_identity(conn) == {"removed": 0, "kept": 2}
    assert [dict(r) for r in conn.execute("SELECT * FROM picks ORDER BY id")] == before_picks
    assert [dict(r) for r in conn.execute("SELECT * FROM pick_outcomes ORDER BY id")] == before_outcomes
    assert len(ids) == 2
    conn.close()


def test_regrading_preserves_original_outcome_versions_without_blocking_updates(tmp_db, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tournament, conn, ids = _originals(tmp_db)
    assert preserve_pick_outcome_versions(conn, tournament, reason="first regrade") == 2
    conn.execute("UPDATE pick_outcomes SET hit=1,profit=5 WHERE pick_id=?", (ids[0],))
    assert preserve_pick_outcome_versions(conn, tournament, reason="second regrade") == 1
    payloads = [json.loads(r[0]) for r in conn.execute("SELECT payload_json FROM prediction_history_versions ORDER BY id")]
    assert {p["profit"] for p in payloads if p["pick_id"] == ids[0]} == {-1.0, 5.0}
    assert conn.execute("SELECT profit FROM pick_outcomes WHERE pick_id=?", (ids[0],)).fetchone()[0] == 5
    assert preserve_pick_outcome_versions(conn, tournament, reason="same version") == 0
    conn.close()


def test_same_day_new_forecast_and_provenance_writes_never_replace_original(tmp_path, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    for filename in ("original_20261015.md", "original_provenance_20261015.json"):
        source = tmp_path / filename
        first = output_manager.write_versioned_output(source, "first original")
        second = output_manager.write_versioned_output(source, "second original")
        assert first != second
        assert source.read_text() == "first original"
        assert source.with_name(os.path.basename(second)).read_text() == "second original"


def test_actual_regrading_journals_before_images(tmp_db, monkeypatch):
    monkeypatch.delenv("PRESERVE_PREDICTION_HISTORY", raising=False)
    tournament, conn, ids = _originals(tmp_db)
    conn.execute("INSERT INTO results(tournament_id,player_key,finish_position,finish_text,made_cut) VALUES(?,'rory_mcilroy',1,'1',1)", (tournament,))
    conn.commit()
    conn.close()
    from src.learning import score_picks_for_tournament

    score_picks_for_tournament(tournament, force_audit=True, audit_reason="explicit correction with original version retained")
    conn = tmp_db.get_conn()
    try:
        originals = [json.loads(r[0]) for r in conn.execute("SELECT payload_json FROM prediction_history_versions")]
        assert {row["pick_id"] for row in originals} == set(ids)
        assert all(row["profit"] == -1 for row in originals)
        assert all(row[0] > 0 for row in conn.execute("SELECT profit FROM pick_outcomes"))
    finally:
        conn.close()
