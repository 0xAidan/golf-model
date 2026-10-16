import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
spec = importlib.util.spec_from_file_location("summarize_forensic_sql_prefixes", SCRIPT_DIR / "summarize_forensic_sql_prefixes.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_scalar_prefixes_do_not_parse_payloads_and_handle_escaped_names():
    row = (b"INSERT OR IGNORE INTO 'market_prediction_rows'('id','snapshot_id','generated_at','tour','section',"
           b"'event_id','event_name','payload_json') VALUES (1,'snap','2026-05-12','pga','upcoming','33',"
           b"'PGA O''Brien','never evaluated');\n")
    result = module.scalar_prefix(row, 7)
    assert result["event_name"] == "PGA O'Brien"
    assert "payload_json" not in result


def test_multiline_literal_cannot_forge_an_insert_and_samples_have_exact_offsets(tmp_path):
    row = (b"INSERT OR IGNORE INTO 'market_prediction_rows'('id','snapshot_id','generated_at','tour','section',"
           b"'event_id','event_name','payload_json') VALUES (1,'snap','2026-05-12','pga','upcoming','33',"
           b"'PGA Championship','multiline data\nINSERT INTO fake(a) VALUES(9);\nstill just data');\n")
    raw = b"BEGIN;\n" + row + b"COMMIT;\n"
    path = tmp_path / "full-recovery.sql.gz"
    with gzip.open(path, "wb") as handle:
        handle.write(raw)
    (tmp_path / "manifest.json").write_text(json.dumps({
        "sql_gzip": str(path), "sql_sha256": hashlib.sha256(raw).hexdigest(),
        "source_sha256_before": "source", "gzip_sha256": "gzip",
        "insert_counts": {"market_prediction_rows": 1},
    }))
    report = module.summarize(tmp_path)
    assert report["status"] == "analysis_complete"
    assert report["events"][0]["event_name"] == "PGA Championship"
    sample = report["samples"][0]
    assert raw[sample["raw_sql_offset"]:sample["raw_sql_offset"] + sample["raw_sql_bytes"]] == row
    assert sample["raw_sql_sha256"] == hashlib.sha256(row).hexdigest()
    assert not report["payloads_parsed"] and not report["sql_executed"]
