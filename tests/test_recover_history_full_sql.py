"""Bounded raw forensic output is data, never executable recovery input."""

import gzip
import hashlib
import importlib.util
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
spec = importlib.util.spec_from_file_location("recover_history_full_sql", SCRIPT_DIR / "recover_history_full_sql.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def _source_and_cli(tmp_path, emitted):
    source = tmp_path / "source.sqlite"
    source.write_bytes(b"unchanged disposable bytes")
    cli = tmp_path / "fake-sqlite"
    cli.write_text("#!/usr/bin/env python3\nimport sys\n"
                   "if '--version' in sys.argv: print('fixture sqlite')\n"
                   "elif ':memory:' in sys.argv: print(0)\n"
                   "else:\n" + emitted)
    cli.chmod(0o700)
    return source, cli


def test_full_stream_retains_unknown_tables_and_never_executes_sql(tmp_path):
    sql = (b"PRAGMA writable_schema=on;\nCREATE TABLE settings(secret);\n"
           b"INSERT INTO settings(secret) VALUES('literal; not another statement');\n"
           b"INSERT INTO runs(id,payload) VALUES(1,'PGA Championship 2026-05-14 Aronimink');\n"
           b"INSERT INTO tournaments(id,name) VALUES(9,'PGA Championship');\nCOMMIT;\n")
    source, cli = _source_and_cli(tmp_path, f" sys.stdout.buffer.write({sql!r})\n")
    report = module.recover(source, tmp_path / "vault", hashlib.sha256(source.read_bytes()).hexdigest(),
                            reserve=0, cli=str(cli))
    with gzip.open(report["sql_gzip"], "rb") as handle:
        assert handle.read() == sql
    assert report["insert_counts"] == {"settings": 1, "runs": 1, "tournaments": 1}
    assert report["source_unchanged"] and report["gzip_readback_verified"]
    assert not report["sql_executed"] and report["freelist_included"]
    assert report["status"] == "salvaged_unverified"
    assert report["lead_rows_retained"] == 2


def test_compressed_cap_keeps_a_valid_partial_gzip_and_manifest(tmp_path):
    source, cli = _source_and_cli(tmp_path, " import os\n for i in range(500): sys.stdout.buffer.write(os.urandom(65536))\n")
    report = module.recover(source, tmp_path / "vault", hashlib.sha256(source.read_bytes()).hexdigest(),
                            reserve=0, max_bytes=1 << 20, cli=str(cli))
    assert report["status"] == "partial_salvage"
    assert report["stop_reason"] == "compressed_output_limit"
    assert 0 < report["gzip_bytes"] <= 1 << 20
    assert report["source_unchanged"] and report["gzip_readback_verified"]
    assert (tmp_path / "vault" / "manifest.json").is_file()
