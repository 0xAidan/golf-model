import gzip
import hashlib
import io
import json
import sqlite3
import tarfile

import pytest

from scripts.build_history_evidence_vault import archive_records, database_records, event_candidate, write_vault


def make_db(path, name):
    with sqlite3.connect(path) as conn:
        conn.executescript("CREATE TABLE tournaments(id INTEGER,event_id TEXT,year INTEGER,name TEXT); CREATE TABLE picks(id INTEGER,tournament_id INTEGER,player_key TEXT); CREATE TABLE secrets(password TEXT); INSERT INTO secrets VALUES('not-exportable');")
        conn.execute("INSERT INTO tournaments VALUES(2,'26',2026,?)", (name,))
        conn.execute("INSERT INTO picks VALUES(1,2,'player-a')")


def test_no_source_mutation_or_secret_table_export(tmp_path):
    source = tmp_path / "source.db"
    make_db(source, "U.S. Open")
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    records = list(database_records(source))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert all(r.get("table") != "secrets" for r in records)
    assert "not-exportable" not in json.dumps(records)
    assert any(r["type"] == "table_end" and r["state"] == "missing" for r in records)


def test_reused_ids_and_exact_duplicates_are_preserved(tmp_path):
    first, second = tmp_path / "first.db", tmp_path / "second.db"
    make_db(first, "U.S. Open")
    make_db(second, "Presidents Cup")
    out = tmp_path / "vault.jsonl.gz"
    summary = write_vault([database_records(first), database_records(second)], out)
    assert summary["row_counts"]["tournaments"] == 2
    assert len(summary["sources"]) == 2
    assert all(x["source_row_id"] == 2 for x in summary["tournament_candidates"])
    assert summary["raw_rows_merged"] is False
    with gzip.open(out) as file:
        picks = [json.loads(line) for line in file if b'"table":"picks"' in line and b'"type":"row"' in line]
    assert len(picks) == 2 and picks[0]["row"] == picks[1]["row"]
    assert picks[0]["source_id"] != picks[1]["source_id"]


def test_exclusive_output_never_overwrites(tmp_path):
    out = tmp_path / "vault.gz"
    out.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        write_vault([], out)
    assert out.read_bytes() == b"existing"


def test_nested_export_stream_retains_member_provenance(tmp_path):
    archive = tmp_path / "exports.tar.gz"
    raw = b'{"id":1,"tournament_id":2,"player_key":"a"}\n'
    nested = gzip.compress(raw)
    with tarfile.open(archive, "w:gz") as tar:
        item = tarfile.TarInfo("data/exports/tournament_2/pick_ledger.jsonl.gz")
        item.size = len(nested)
        tar.addfile(item, io.BytesIO(nested))
    records = list(archive_records(archive, archive_sha256="verified-archive-hash"))
    row = next(r for r in records if r["type"] == "row")
    assert row["row"]["tournament_id"] == 2
    assert row["member_path"].endswith("pick_ledger.jsonl.gz")
    assert row["input_line_sha256"] == hashlib.sha256(raw).hexdigest()
    assert records[0]["source"]["archive_sha256"] == "verified-archive-hash"


def test_missing_identity_never_auto_matches():
    result = event_candidate({"id": 2, "event_id": "26", "year": 2026, "name": "U.S. Open"})
    assert result["match_status"] == "needs_identity_review"
    assert result["missing_fields"] == ["tour"]
    assert result["merged"] is False
