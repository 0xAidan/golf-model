"""Lean nightly backup: every table except the journal, plus the journal's new rows."""

import gzip
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("lean_backup", ROOT / "scripts/lean_backup.py")
lean_backup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lean_backup)


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "golf.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE picks (id INTEGER PRIMARY KEY, player TEXT, odds TEXT);
        CREATE INDEX idx_picks_player ON picks(player);
        CREATE TABLE results (id INTEGER PRIMARY KEY, finish TEXT);
        CREATE TABLE prediction_history_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, source_table TEXT, payload_json TEXT);
    """)
    conn.executemany("INSERT INTO picks (player, odds) VALUES (?, ?)", [("a", "+110"), ("b", "-120")])
    conn.execute("INSERT INTO results (finish) VALUES ('T3')")
    conn.executemany("INSERT INTO prediction_history_versions (source_table, payload_json) VALUES ('metrics', ?)",
                     [(json.dumps({"n": n}),) for n in range(5)])
    conn.commit()
    conn.close()
    return path


def _open_lean(output_dir, manifest):
    raw = output_dir / "restored.db"
    raw.write_bytes(gzip.decompress((output_dir / manifest["archive"]).read_bytes()))
    return sqlite3.connect(raw)


def test_copies_every_table_except_the_journal_and_verifies_it(source, tmp_path):
    out = tmp_path / "lean"
    manifest = lean_backup.run(source, out, min_free_mib=0, journal_base_id=2)

    assert manifest["integrity_check"] == "ok"
    assert manifest["table_counts"] == {"picks": 2, "results": 1}
    assert manifest["excluded_tables"] == ["prediction_history_versions"]
    conn = _open_lean(out, manifest)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables == {"picks", "results", "_lean_backup_schema"}
    assert conn.execute("SELECT player, odds FROM picks ORDER BY id").fetchall() == [("a", "+110"), ("b", "-120")]
    assert conn.execute("SELECT name FROM _lean_backup_schema WHERE type='index'").fetchall() == [("idx_picks_player",)]
    conn.close()
    assert (out / f"{manifest['archive']}.manifest.json").is_file()
    assert not list(out.glob("*.partial")) and not list(out.glob("golf_lean_*/"))


def test_journal_delta_holds_only_rows_after_the_base_and_advances(source, tmp_path):
    out = tmp_path / "lean"
    first = lean_backup.run(source, out, min_free_mib=0, journal_base_id=2)

    delta = first["journal_delta"]
    assert (delta["from_id"], delta["to_id"], delta["rows"]) == (3, 5, 3)
    lines = [json.loads(line) for line in gzip.open(out / delta["file"], "rt")]
    assert [line["id"] for line in lines] == [3, 4, 5]
    assert json.loads((out / "journal_state.json").read_text())["last_exported_id"] == 5

    second = lean_backup.run(source, out, min_free_mib=0)     # nothing new: no delta, state unchanged
    assert second["journal_delta"] is None and second["journal_covered_through_id"] == 5

    conn = sqlite3.connect(source)
    conn.execute("INSERT INTO prediction_history_versions (source_table, payload_json) VALUES ('picks', '{}')")
    conn.commit()
    conn.close()
    third = lean_backup.run(source, out, min_free_mib=0)
    assert (third["journal_delta"]["from_id"], third["journal_delta"]["rows"]) == (6, 1)


def test_source_is_untouched_and_nothing_is_ever_removed(source, tmp_path):
    out = tmp_path / "lean"
    before = source.read_bytes()
    lean_backup.run(source, out, min_free_mib=0, journal_base_id=0)
    lean_backup.run(source, out, min_free_mib=0)
    assert source.read_bytes() == before
    assert len(list(out.glob("golf_lean_*.db.gz"))) >= 1
    assert len(list(out.glob("journal_delta_*.jsonl.gz"))) == 1


def test_refuses_on_low_disk_and_on_a_first_run_without_a_base(source, tmp_path):
    with pytest.raises(lean_backup.LeanBackupError, match="floor"):
        lean_backup.run(source, tmp_path / "a", min_free_mib=10**9, journal_base_id=0)
    with pytest.raises(lean_backup.LeanBackupError, match="journal-base-id"):
        lean_backup.run(source, tmp_path / "b", min_free_mib=0)
    assert not list((tmp_path / "b").glob("golf_lean_*.db.gz"))
