"""Preservation must include committed WAL rows and never mutate source payloads."""

import gzip
import json
import sqlite3
import io
import tarfile
import hashlib
import pytest

from scripts import collect_prediction_database_vault as vault


def test_preservation_includes_wal_and_retains_fixture_rows(tmp_path):
    source = tmp_path / "source.sqlite"
    writer = sqlite3.connect(source)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE tournaments(id INTEGER PRIMARY KEY, name TEXT, event_id TEXT)")
    writer.execute("INSERT INTO tournaments VALUES(1,'Real Open','13')")
    writer.execute("CREATE TABLE market_prediction_rows(id INTEGER PRIMARY KEY, event_id TEXT, model_prob REAL, generated_at TEXT)")
    writer.execute("INSERT INTO market_prediction_rows VALUES(1,'13',0.6,'2026-01-01T01:00:00Z')")
    writer.execute("INSERT INTO market_prediction_rows VALUES(2,'999',0.9,'2026-01-02T01:00:00Z')")
    writer.execute("CREATE TABLE private_settings(secret TEXT)")
    writer.execute("INSERT INTO private_settings VALUES('never logically export')")
    writer.commit()
    original_hash = vault.sha256(source)
    result = vault.collect(source, tmp_path / "preserved")
    assert result["state"] == "complete"
    assert result["quick_check"] == ["ok"]
    assert result["preservation"]["readback_verified"] is True
    assert result["logical"]["tables"]["market_prediction_rows"]["rows"] == 2
    assert result["logical"]["tables"]["market_prediction_rows"]["fixture_signal_rows"] == 1
    assert "private_settings" in result["logical"]["non_whitelisted_tables"]
    rows = [json.loads(line) for line in gzip.open(result["logical"]["path"], "rt")]
    data = [row for row in rows if row["type"] == "row"]
    assert all(row["table"] != "private_settings" for row in data)
    assert any(row["row"].get("event_id") == "999" and row["fixture_signals"] for row in data)
    assert all(row["performance_eligible"] is False for row in data)
    assert vault.sha256(source) == original_hash
    assert not (tmp_path / "preserved" / vault.Path(result["logical"]["path"]).parent.name / "consistent-snapshot.sqlite").exists()
    writer.close()


def test_wal_change_creates_a_new_source_generation(tmp_path):
    source = tmp_path / "source.sqlite"
    writer = sqlite3.connect(source)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE picks(id INTEGER PRIMARY KEY, player_key TEXT)")
    writer.execute("INSERT INTO picks VALUES(1,'one')")
    writer.commit()
    first = vault.collect(source, tmp_path / "out")
    writer.execute("INSERT INTO picks VALUES(2,'two')")
    writer.commit()
    second = vault.collect(source, tmp_path / "out")
    assert first["source_id"] != second["source_id"]
    assert first["logical"]["tables"]["picks"]["rows"] == 1
    assert second["logical"]["tables"]["picks"]["rows"] == 2
    writer.close()


def test_placeholder_is_not_opened_or_counted_as_recovered(monkeypatch, tmp_path):
    source = tmp_path / "cloud.sqlite"
    source.write_bytes(b"not resident database bytes")
    original_metadata = vault.metadata

    def placeholder_metadata(path):
        result = original_metadata(path)
        if str(path) == str(source):
            result["cloud_placeholder"] = True
        return result

    monkeypatch.setattr(vault, "metadata", placeholder_metadata)
    monkeypatch.setattr(vault, "snapshot_source", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not open placeholder")))
    result = vault.collect(source, tmp_path / "out")
    assert result["state"] == "cloud_placeholder"
    assert "logical" not in result and "preservation" not in result


def test_tick_archive_preserves_nested_gzip_member_hash_and_source_pointer(tmp_path):
    source = tmp_path / "exports.tar.gz"
    row = {"id": 1, "event_id": "480", "model_prob": 0.61, "payload_json": '{"rankings":[{"player":"A"}]}'}
    line = json.dumps(row).encode() + b"\n"
    payload = gzip.compress(line, mtime=0)
    member_name = "data/exports/tick_archive_20260506/market_prediction_rows.jsonl.gz"
    with tarfile.open(source, "w:gz") as archive:
        member = tarfile.TarInfo(member_name)
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
        secret = tarfile.TarInfo("data/exports/tick/private_settings.jsonl")
        secret.size = len(line)
        archive.addfile(secret, io.BytesIO(line))
    result = vault.collect_archive(source, tmp_path / "preserved")
    assert result["state"] == "complete" and result["rows"] == 1
    assert result["members"][0]["member_sha256"] == hashlib.sha256(payload).hexdigest()
    rows = [json.loads(line) for line in gzip.open(result["logical"]["path"], "rt")]
    saved = next(item for item in rows if item["type"] == "row")
    assert saved["archive_member"] == member_name
    assert saved["input_line_sha256"] == hashlib.sha256(line).hexdigest()
    assert saved["row"] == row


def test_immutable_opt_in_requires_empty_wal_before_creating_destination(tmp_path):
    source = tmp_path / "source.sqlite"
    source.write_bytes(b"do not open source")
    source.with_name(source.name + "-wal").write_bytes(b"committed frames must not be ignored")
    destination = tmp_path / "snapshot.sqlite"
    with pytest.raises(ValueError, match="absent or zero-byte WAL"):
        vault.snapshot_source(source, destination, immutable_empty_wal=True)
    assert not destination.exists()
    assert source.read_bytes() == b"do not open source"


def test_immutable_empty_wal_preserves_resident_base_without_reading_shm(tmp_path):
    source = tmp_path / "source.sqlite"
    with sqlite3.connect(source) as writer:
        writer.execute("CREATE TABLE picks(id INTEGER PRIMARY KEY, player_key TEXT)")
        writer.execute("INSERT INTO picks VALUES(1,'original')")
    source.with_name(source.name + "-wal").write_bytes(b"")
    shm = source.with_name(source.name + "-shm")
    shm.write_bytes(b"invalid shared-memory bytes must not be consulted")
    original = source.read_bytes()
    result = vault.collect(source, tmp_path / "vault", immutable_empty_wal=True, keep_uncompressed=True)
    assert result["state"] == "complete" and result["quick_check"] == ["ok"]
    assert result["logical"]["tables"]["picks"]["rows"] == 1
    assert source.read_bytes() == original
    assert shm.read_bytes() == b"invalid shared-memory bytes must not be consulted"
