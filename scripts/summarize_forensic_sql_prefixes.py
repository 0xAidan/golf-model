#!/usr/bin/env python3
"""Bounded scalar-prefix analysis of SQLite shell recovery output, without SQL execution."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import time

from recover_history_core import _PREFIX, _table

_TOKEN = re.compile(rb"\s*(NULL|[+-]?[0-9]+(?:\.[0-9]+)?|'(?:[^']|'')*')\s*([,)])", re.I)
_FIELDS = {"market_prediction_rows": 7, "live_snapshot_history": 10,
           "pre_teeoff_candidates": 3, "pre_teeoff_frozen": 3, "runs": 3, "tournaments": 7}


def scalar_prefix(line: bytes, count: int) -> dict:
    """Read only known pre-payload columns; evaluate no expressions or JSON."""
    boundary = line.find(b") VALUES (")
    if boundary < 0:
        raise ValueError("unsupported_column_prefix")
    header = _PREFIX.match(line[:512].decode("ascii", errors="ignore"))
    if not header:
        raise ValueError("unsupported_insert_prefix")
    columns = re.findall(rb"'((?:[^']|'')*)'", line[header.end():boundary])
    if len(columns) < count:
        raise ValueError("short_column_prefix")
    offset = boundary + len(b") VALUES (")
    result = {}
    for column in columns[:count]:
        token = _TOKEN.match(line, offset)
        if not token:
            raise ValueError("nonliteral_or_multiline_scalar_prefix")
        value = token[1]
        if value.upper() == b"NULL":
            decoded = None
        elif value.startswith(b"'"):
            decoded = value[1:-1].replace(b"''", b"'").decode("utf-8", errors="strict")
        else:
            decoded = value.decode("ascii")
        result[column.decode("ascii")] = decoded
        offset = token.end()
    return result


def summarize(directory: Path, *, seconds=120):
    manifest = json.loads((directory / "manifest.json").read_text())
    path = Path(manifest["sql_gzip"])
    started = time.monotonic()
    counts, errors = Counter(), Counter()
    groups = {}
    samples = []
    current = None
    sql_offset = 0
    eof = False
    trigger = False
    with gzip.open(path, "rb") as stream:
        for line_number, line in enumerate(stream, 1):
            if line_number % 1000 == 0 and time.monotonic() - started > seconds:
                break
            offset = sql_offset
            sql_offset += len(line)
            if current is None:
                if re.match(rb"\s*CREATE\s+TRIGGER\b", line, re.I):
                    trigger = True
                if trigger:
                    if re.fullmatch(rb"\s*END\s*;\s*", line, re.I):
                        trigger = False
                    continue
                match = _PREFIX.match(line[:512].decode("ascii", errors="ignore"))
                if not match:
                    continue
                table = _table(match)
                metadata = {}
                if table in _FIELDS:
                    try:
                        metadata = scalar_prefix(line, _FIELDS[table])
                    except (ValueError, UnicodeDecodeError) as exc:
                        errors[str(exc)] += 1
                key = None
                first = False
                if metadata:
                    event_id = metadata.get("source_event_id") or metadata.get("event_id")
                    event_name = metadata.get("source_event_name") or metadata.get("event_name")
                    if table == "tournaments":
                        event_id, event_name = metadata.get("event_id"), metadata.get("name")
                    key = (table, metadata.get("tour"), metadata.get("section"), event_id,
                           event_name, metadata.get("tournament_id"))
                    first = key not in groups
                    if first:
                        groups[key] = {"table": table, "tour": key[1], "section": key[2],
                                       "event_id": event_id, "event_name": event_name,
                                       "source_local_tournament_id": key[5], "rows": 0,
                                       "min_generated_at": None, "max_generated_at": None}
                current = {"table": table, "quote": False, "key": key, "metadata": metadata,
                           "offset": offset, "bytes": 0,
                           "hash": hashlib.sha256() if first and len(samples) < 200 else None}
            current["quote"] ^= bool(line.count(b"'") % 2)
            current["bytes"] += len(line)
            if current["hash"] is not None:
                current["hash"].update(line)
            if current["quote"] or not line.rstrip().endswith(b";"):
                continue
            counts[current["table"]] += 1
            if current["key"] is not None:
                group = groups[current["key"]]
                group["rows"] += 1
                timestamp = current["metadata"].get("generated_at") or current["metadata"].get("created_at")
                if timestamp:
                    group["min_generated_at"] = min(group["min_generated_at"] or timestamp, timestamp)
                    group["max_generated_at"] = max(group["max_generated_at"] or timestamp, timestamp)
            if current["hash"] is not None:
                samples.append({"table": current["table"], "metadata": current["metadata"],
                                "raw_sql_offset": current["offset"], "raw_sql_bytes": current["bytes"],
                                "raw_sql_sha256": current["hash"].hexdigest(), "performance_eligible": False})
            current = None
        else:
            eof = True
    expected = manifest["insert_counts"]
    count_parity = dict(counts) == expected
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "source_sha256": manifest["source_sha256_before"],
              "sql_sha256": manifest["sql_sha256"], "sql_gzip_sha256": manifest["gzip_sha256"],
              "status": "analysis_complete" if eof and count_parity else "partial_analysis",
              "analysis_seconds": round(time.monotonic() - started, 2), "max_seconds": seconds,
              "raw_sql_bytes_analyzed": sql_offset, "raw_sql_eof_reached": eof,
              "insert_count_parity_with_quote_aware_capture": count_parity,
              "insert_counts": dict(counts), "parse_errors": dict(errors),
              "incomplete_final_insert": current is not None, "events": list(groups.values()),
              "samples": samples, "method": "known_schema_scalar_prefixes_and_single_quote_line_framing",
              "recovery_status": "salvaged_unverified", "performance_eligible": False,
              "sql_executed": False, "payloads_parsed": False}
    output = directory / "scalar-event-coverage.json"
    with output.open("x") as handle:
        os.chmod(output, 0o600)
        json.dump(report, handle, indent=2)
    print(json.dumps({"status": report["status"], "seconds": report["analysis_seconds"],
                      "count_parity": count_parity, "events": len(groups), "insert_counts": dict(counts),
                      "parse_errors": dict(errors)}), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    summarize(args.directory)
