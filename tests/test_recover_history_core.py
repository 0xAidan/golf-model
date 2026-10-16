import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

import pytest

spec = importlib.util.spec_from_file_location(
    "recover_history_core", Path(__file__).parents[1] / "scripts/recover_history_core.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def scan(sql, chunk_size=7, limit=8192):
    scanner = module.CoreStatementScanner(max_statement_bytes=limit)
    output = []
    for offset in range(0, len(sql), chunk_size):
        output.extend(scanner.feed(sql[offset : offset + chunk_size]))
    output.extend(scanner.feed(b"", final=True))
    return output, scanner.counts


def test_literals_preserve_escaped_multiline_text_blobs_numbers_and_null():
    sql = b"INSERT OR IGNORE INTO 'picks'('id','player','notes','odds','blob','empty') VALUES (7,'O''Brien','line1;\nline2',-1.125e2,X'001AFF',NULL);"
    table, row = module.parse_core_insert(sql)
    assert table == "picks"
    assert row == {
        "id": 7,
        "player": "O'Brien",
        "notes": "line1;\nline2",
        "odds": -112.5,
        "blob": {"$sqlite_blob_base64": "ABr/"},
        "empty": None,
    }


@pytest.mark.parametrize(
    "expression", ["load_extension('/tmp/no')", "(SELECT password FROM config)", "1+2", "random()", "'x'||'y'"]
)
def test_expression_never_evaluates(expression):
    with pytest.raises(ValueError):
        module.parse_core_insert(f"INSERT INTO picks(id) VALUES ({expression});".encode())


@pytest.mark.parametrize("chunk_size", [1, 2, 7, 64, 65536])
def test_scanner_drops_unknown_payloads_triggers_and_pragmas(chunk_size):
    sql = (
        b".dbconfig defensive off\nBEGIN; PRAGMA writable_schema=on;"
        b"CREATE TABLE config(secret TEXT); INSERT INTO config(secret) VALUES ('private; -- INSERT INTO picks(id) VALUES(99);');"
        b"CREATE TRIGGER nope AFTER INSERT ON picks BEGIN SELECT random(); INSERT INTO picks(id) VALUES(777); END;"
        b"INSERT OR IGNORE INTO 'picks'('id','player') VALUES (1,'Test O''Brien; \nvalue');"
        b"INSERT INTO results(id,notes) VALUES(2,'/*not a comment*/'); COMMIT;"
    )
    statements, counts = scan(sql, chunk_size)
    assert len(statements) == 2
    assert [module.parse_core_insert(s)[1]["id"] for s in statements] == [1, 2]
    assert b"private" not in b"".join(statements)
    assert counts["discarded_statements"] >= 4


def test_oversized_core_and_unknown_statements_do_not_grow_buffers():
    scanner = module.CoreStatementScanner(max_statement_bytes=1024)
    rows = []
    for chunk in [
        b"INSERT INTO config(secret) VALUES ('",
        b"x" * 100000,
        b"');",
        b"INSERT INTO picks(id,notes) VALUES (1,'",
        b"y" * 100000,
        b"');",
        b"INSERT INTO picks(id) VALUES (2);",
    ]:
        rows.extend(scanner.feed(chunk))
        assert len(scanner.prefix) <= 512
        assert scanner.body is None or len(scanner.body) <= 1024
    rows.extend(scanner.feed(b"", final=True))
    assert len(rows) == 1
    assert module.parse_core_insert(rows[0])[1] == {"id": 2}
    assert scanner.counts["oversized_core_statements"] == 1


def test_unsupported_shapes_and_duplicate_columns_rejected():
    for sql in [
        b"INSERT INTO config(id) VALUES(1);",
        b"INSERT INTO picks VALUES(1);",
        b"INSERT INTO picks(id,id) VALUES(1,2);",
        b"INSERT INTO picks(id) VALUES(1); DROP TABLE picks;",
        b"INSERT INTO picks(id) VALUES(1),(2);",
    ]:
        with pytest.raises(ValueError):
            module.parse_core_insert(sql)


def test_binary_text_and_nonfinite_markers():
    _, row = module.parse_core_insert(b"INSERT INTO picks(id,name,value) VALUES(1,CAST(X'FF' AS TEXT),9e999);")
    assert row["name"] == {"$sqlite_text_bytes_base64": "/w=="}
    assert row["value"] == {"$sqlite_nonfinite_float": "inf"}


def test_incomplete_insert_is_not_emitted():
    statements, counts = scan(b"INSERT INTO picks(id,name) VALUES(1,'unfinished")
    assert statements == []
    assert counts["incomplete_core_statements"] == 1


@pytest.fixture
def sqlite_recovery_cli():
    cli = shutil.which("sqlite3")
    if (
        not cli
        or ".recover" not in subprocess.run([cli, ":memory:", ".help recover"], capture_output=True, text=True).stdout
    ):
        pytest.skip("SQLite CLI recovery unavailable")
    # Some distribution shells advertise .recover without its required
    # sqlite_dbpage module. Probe that capability independently of our wrapper;
    # never skip an unexpected recovery/parser failure.
    probe = subprocess.run(
        [cli, ":memory:", "SELECT count(*) FROM sqlite_dbpage"],
        capture_output=True, text=True, timeout=5,
    )
    if probe.returncode and "no such table: sqlite_dbpage" in probe.stderr:
        pytest.skip("SQLite CLI lacks the sqlite_dbpage module required by .recover")
    assert probe.returncode == 0, probe.stderr
    return cli


def test_real_cli_salvage_is_exclusive_unverified_and_preserves_copy(tmp_path, sqlite_recovery_cli):
    cli = sqlite_recovery_cli
    source = tmp_path / "disposable.sqlite"
    conn = sqlite3.connect(source)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        "CREATE TABLE picks(id INTEGER PRIMARY KEY, name TEXT); INSERT INTO picks VALUES(1,'Fixture'); CREATE TABLE config(secret TEXT); INSERT INTO config VALUES('DO_NOT_RETAIN');"
    )
    conn.close()
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    output = tmp_path / "core.jsonl.gz"
    provenance = {"disposable_copy": str(source), "member_sha256": before, "member_path": "fixture.sqlite"}
    report = module.recover_core(source, output, provenance, sqlite_cli=cli, max_seconds=10, min_free_bytes=0)
    records = [json.loads(line) for line in gzip.open(output, "rb")]
    rows = [r for r in records if r["type"] == "row"]
    assert len(rows) == 1
    assert rows[0]["row"] == {"id": 1, "name": "Fixture"}
    assert rows[0]["provenance_status"] == "salvaged_unverified"
    assert rows[0]["primary_performance_eligible"] is False
    assert "DO_NOT_RETAIN" not in json.dumps(records)
    assert report["copy_unchanged"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    with pytest.raises(FileExistsError):
        module.recover_core(source, output, provenance, sqlite_cli=cli, min_free_bytes=0)


def test_rejects_nonempty_wal_before_recovery(tmp_path):
    source = tmp_path / "copy.sqlite"
    source.write_bytes(b"fixture")
    source.with_name(source.name + "-wal").write_bytes(b"nonempty")
    provenance = {"disposable_copy": str(source), "member_sha256": module.file_sha256(source)}
    with pytest.raises(ValueError, match="empty or absent"):
        module.recover_core(source, tmp_path / "rows.gz", provenance, min_free_bytes=0)
    assert not (tmp_path / "rows.gz.partial").exists()


def recovery_producer(tmp_path, *, fail=False):
    """A real subprocess emitting fixture SQL, independent of distro extensions."""
    cli = tmp_path / "fixture-recovery"
    cli.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "if '--version' in sys.argv:\n"
        "    print('fixture recovery producer')\n"
        "    sys.exit(0)\n"
        "assert '-readonly' in sys.argv\n"
        "assert any(arg.endswith('?mode=ro&immutable=1') for arg in sys.argv)\n"
        + ("sys.stderr.write('fixture recovery failure')\nsys.exit(1)\n" if fail else
           "sys.stdout.write(\"INSERT INTO picks(id,note) VALUES(1,'\" + 'x' * 30000 + \"');\\n\")\n")
    )
    cli.chmod(0o700)
    return str(cli)


@pytest.mark.parametrize(
    "limit, expected",
    [("time", "time_limit"), ("output", "core_output_limit"), ("process", "sqlite_recover_nonzero_exit")],
)
def test_recovery_limits_stop_and_retain_failure_state(tmp_path, limit, expected):
    cli = recovery_producer(tmp_path, fail=limit == "process")
    source = tmp_path / "copy.sqlite"
    conn = sqlite3.connect(source)
    conn.execute("CREATE TABLE picks(id INTEGER PRIMARY KEY, note TEXT)")
    conn.execute("INSERT INTO picks VALUES(1,?)", ("x" * 30000,))
    conn.commit()
    conn.close()
    provenance = {"disposable_copy": str(source), "member_sha256": module.file_sha256(source)}
    output = tmp_path / "rows.gz"
    report = module.recover_core(
        source,
        output,
        provenance,
        sqlite_cli=cli,
        min_free_bytes=0,
        max_seconds=0 if limit == "time" else 10,
        max_output_bytes=4096 if limit == "output" else 500 << 20,
    )
    assert report["stop_reason"] == expected
    assert report["copy_unchanged"]
    assert report["rows"] == 0
    assert all(t["state"] == "partial_salvage" for t in report["tables"].values())
    assert all(t["primary_performance_eligible"] is False for t in report["tables"].values())
