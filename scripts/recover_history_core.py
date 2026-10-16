#!/usr/bin/env python3
"""Salvage only whitelisted raw rows from a DISPOSABLE SQLite copy.

SQLite's .recover output is untrusted SQL. Nothing it emits is executed. A
bounded scanner discards other tables and a literal-only parser converts core
INSERTs to provenance records. All rows remain salvaged_unverified and excluded
from primary performance. This module imports no application/model code.
"""

from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import tempfile
import time

TABLES = ("tournaments", "picks", "pick_outcomes", "results", "pick_ledger", "prediction_log")
_IDENTIFIER = r"(?:'(?P<single>(?:[^']|'')*)'|\"(?P<double>(?:[^\"]|\"\")*)\"|`(?P<backtick>(?:[^`]|``)*)`|\[(?P<bracket>[^\]]*)\]|(?P<bare>[A-Za-z_][A-Za-z0-9_]*))"
_PREFIX = re.compile(r"\A\s*INSERT(?:\s+OR\s+IGNORE)?\s+INTO\s+" + _IDENTIFIER + r"\s*\(", re.I)
_SPECIAL = re.compile(rb"['\"`;\[]|--|/\*")
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _table(match):
    values = match.groupdict()
    if values["single"] is not None:
        return values["single"].replace("''", "'")
    if values["double"] is not None:
        return values["double"].replace('""', '"')
    if values["backtick"] is not None:
        return values["backtick"].replace("``", "`")
    return values["bracket"] if values["bracket"] is not None else values["bare"]


class CoreStatementScanner:
    """Split SQL without retaining unknown-table payloads or unbounded statements."""

    def __init__(self, max_statement_bytes=8 << 20, tables=TABLES):
        self.max_statement_bytes = max_statement_bytes
        self.tables = tables
        self.pending = b""
        self.quote = None
        self.comment = None
        self.prefix = bytearray()
        self.body = None
        self.discard = False
        self.counts = Counter()
        self.trigger_active = False

    def _add(self, data):
        if self.discard:
            return
        if self.body is not None:
            if len(self.body) + len(data) > self.max_statement_bytes:
                self.counts["oversized_core_statements"] += 1
                self.body = None
                self.discard = True
            else:
                self.body.extend(data)
            return
        retained = min(512 - len(self.prefix), len(data))
        self.prefix.extend(data[:retained])
        try:
            match = _PREFIX.match(self.prefix.decode("ascii"))
        except UnicodeDecodeError:
            match = None
        prefix_text = self.prefix.decode("ascii", errors="ignore")
        if re.match(r"\A\s*CREATE(?:\s+TEMP(?:ORARY)?)?\s+TRIGGER\b", prefix_text, re.I):
            self.trigger_active = True
        if self.trigger_active:
            return
        if match:
            if self.tables is None or _table(match) in self.tables:
                self.body = self.prefix
                self.prefix = bytearray()
                self._add(data[retained:])
            else:
                self.prefix.clear()
                self.discard = True
        elif len(self.prefix) >= 512:
            self.prefix.clear()
            self.discard = True

    def _finish(self):
        if self.trigger_active and re.fullmatch(rb"\s*END\s*;\s*", bytes(self.prefix), re.I):
            self.trigger_active = False
        statement = bytes(self.body) if self.body is not None else None
        self.counts["candidate_core_statements" if statement is not None else "discarded_statements"] += 1
        self.prefix = bytearray()
        self.body = None
        self.discard = False
        return statement

    def feed(self, chunk, *, final=False):
        data = self.pending + chunk
        self.pending = b""
        i = 0
        while i < len(data):
            if self.comment:
                marker = b"\n" if self.comment == "line" else b"*/"
                j = data.find(marker, i)
                if j < 0:
                    end = len(data) if final or self.comment == "line" else max(i, len(data) - 1)
                    self._add(data[i:end])
                    i = end
                    break
                end = j + len(marker)
                self._add(data[i:end])
                i = end
                self.comment = None
                continue
            if self.quote:
                q = self.quote
                j = data.find(q, i)
                if j < 0:
                    self._add(data[i:])
                    i = len(data)
                    break
                if j + 1 == len(data) and not final and q != b"]":
                    self._add(data[i:j])
                    i = j
                    break
                if q != b"]" and data[j + 1 : j + 2] == q:
                    self._add(data[i : j + 2])
                    i = j + 2
                else:
                    self._add(data[i : j + 1])
                    i = j + 1
                    self.quote = None
                continue
            match = _SPECIAL.search(data, i)
            if not match:
                end = len(data) if final else max(i, len(data) - 1)
                self._add(data[i:end])
                i = end
                break
            token = match.group()
            self._add(data[i : match.end()])
            i = match.end()
            if token in (b"'", b'"', b"`", b"["):
                self.quote = b"]" if token == b"[" else token
            elif token == b"--":
                self.comment = "line"
            elif token == b"/*":
                self.comment = "block"
            elif token == b";":
                statement = self._finish()
                if statement is not None:
                    yield statement
        self.pending = data[i:]
        if final:
            if self.body is not None:
                self.counts["incomplete_core_statements"] += 1
            self.pending = b""
            self.prefix.clear()
            self.body = None


def _split_list(text):
    values = []
    start = 0
    quote = None
    depth = 0
    i = 0
    while i < len(text):
        c = text[i]
        if quote:
            if c == quote:
                if quote != "]" and i + 1 < len(text) and text[i + 1] == quote:
                    i += 2
                    continue
                quote = None
        elif c in "'\"`[":
            quote = "]" if c == "[" else c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("unexpected_parenthesis")
        elif c == "," and depth == 0:
            values.append(text[start:i].strip())
            start = i + 1
        i += 1
    if quote or depth:
        raise ValueError("unterminated_literal")
    values.append(text[start:].strip())
    return values


def _identifier(text):
    match = re.fullmatch(_IDENTIFIER, text)
    if not match:
        raise ValueError("unsupported_identifier")
    return _table(match)


def _literal(text):
    if text.upper() == "NULL":
        return None
    if re.fullmatch(r"'(?:[^']|'')*'", text, re.S):
        return text[1:-1].replace("''", "'")
    match = re.fullmatch(r"[xX]'([0-9a-fA-F]*)'", text)
    if match:
        try:
            value = bytes.fromhex(match.group(1))
        except ValueError as exc:
            raise ValueError("invalid_blob") from exc
        return {"$sqlite_blob_base64": base64.b64encode(value).decode()}
    match = re.fullmatch(r"CAST\s*\(\s*[xX]'([0-9a-fA-F]*)'\s+AS\s+TEXT\s*\)", text, re.I)
    if match:
        try:
            value = bytes.fromhex(match.group(1))
        except ValueError as exc:
            raise ValueError("invalid_text_bytes") from exc
        # A marker preserves non-UTF8 SQLite TEXT without silently replacing bytes.
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return {"$sqlite_text_bytes_base64": base64.b64encode(value).decode()}
    if _NUMBER.fullmatch(text):
        if not any(c in text for c in ".eE"):
            return int(text)
        value = float(text)
        return value if math.isfinite(value) else {"$sqlite_nonfinite_float": repr(value)}
    raise ValueError("unsupported_literal_expression")


def parse_core_insert(statement, *, approved_tables=TABLES):
    """Parse explicit-column INSERT literals; never evaluate expressions or SQL."""
    try:
        sql = statement.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("invalid_utf8_sql") from exc
    match = _PREFIX.match(sql)
    if not match or (approved_tables is not None and _table(match) not in approved_tables):
        raise ValueError("unapproved_table_or_statement")
    rest = sql[match.end() :]
    # Column identifiers cannot contain unquoted closing parentheses. Use the
    # same quote-aware scanner as values to locate the end of the column list.
    quote = None
    i = 0
    while i < len(rest):
        c = rest[i]
        if quote:
            if c == quote:
                if quote != "]" and rest[i + 1 : i + 2] == quote:
                    i += 2
                    continue
                quote = None
        elif c in "'\"`[":
            quote = "]" if c == "[" else c
        elif c == ")":
            break
        i += 1
    if i == len(rest):
        raise ValueError("missing_column_terminator")
    columns = [_identifier(s) for s in _split_list(rest[:i])]
    if len(columns) > 512 or len(set(columns)) != len(columns):
        raise ValueError("duplicate_or_excessive_columns")
    values_match = re.fullmatch(r"\s*VALUES\s*\((.*)\)\s*;\s*", rest[i + 1 :], re.I | re.S)
    if not values_match:
        raise ValueError("unsupported_insert_shape")
    values = [_literal(s) for s in _split_list(values_match.group(1))]
    if len(values) != len(columns):
        raise ValueError("column_value_count_mismatch")
    return _table(match), dict(zip(columns, values))


def recover_core(
    copy,
    output,
    provenance,
    *,
    sqlite_cli="/usr/bin/sqlite3",
    max_seconds=600,
    max_output_bytes=500 << 20,
    min_free_bytes=6 << 30,
):
    """Run one bounded salvage from an exact disposable copy into an exclusive vault."""
    started = time.monotonic()
    copy, output = Path(copy).resolve(), Path(output).resolve()
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    partial = output.with_name(output.name + ".partial")
    if output.exists() or partial.exists():
        raise FileExistsError(output)
    if not provenance.get("disposable_copy") or copy != Path(provenance["disposable_copy"]).resolve():
        raise ValueError("A matching explicit disposable_copy provenance path is required")
    wal_path = copy.with_name(copy.name + "-wal")
    if wal_path.exists() and wal_path.stat().st_size:
        raise ValueError("Immutable salvage requires an empty or absent disposable WAL")
    expected = provenance["member_sha256"]
    before = copy.stat()
    if file_sha256(copy) != expected:
        raise ValueError("Disposable copy hash does not match source member")
    if shutil.disk_usage(output.parent).free < min_free_bytes:
        raise RuntimeError("Free disk is below reserve")
    cli_version = subprocess.run(
        [sqlite_cli, "--version"], capture_output=True, text=True, timeout=5, check=True
    ).stdout.strip()
    source = {
        **provenance,
        "immutable_base_only": True,
        "wal_applied": False,
        "recovery_read_mode": "mode=ro&immutable=1",
        "sqlite_cli_version": cli_version,
        "recovery_method": "sqlite_cli_recover_literal_only_v1",
        "recovery_status": "salvaged_unverified",
        "primary_performance_eligible": False,
    }
    source_id = digest(source)
    report = {
        "format_version": 1,
        "source_id": source_id,
        "source": source,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "tables": {},
        "primary_performance_eligible": False,
        "models_changed": False,
        "originals_changed": False,
        "recovered_sql_executed": False,
        "limits": {
            "max_seconds": max_seconds,
            "max_core_output_bytes": max_output_bytes,
            "min_free_bytes": min_free_bytes,
        },
    }
    scanner = CoreStatementScanner()
    counts = Counter()
    errors = Counter()
    total_bytes = 0
    stderr_hash = hashlib.sha256()
    stderr_bytes = 0
    stop_reason = None
    with tempfile.TemporaryDirectory(prefix="core-recover-tmp-", dir=output.parent) as temp_dir:
        env = {**os.environ, "SQLITE_TMPDIR": temp_dir, "TMPDIR": temp_dir}
        process = subprocess.Popen(
            [sqlite_cli, "-readonly", "-batch", copy.as_uri() + "?mode=ro&immutable=1", ".recover --ignore-freelist"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        with partial.open("xb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as stream:
            os.chmod(partial, 0o600)

            def write(record, *, bounded=True):
                nonlocal total_bytes
                line = canonical_bytes(record) + b"\n"
                if bounded and total_bytes + len(line) > max_output_bytes:
                    raise RuntimeError("core_output_limit")
                stream.write(line)
                total_bytes += len(line)

            write({"type": "source_begin", "source_id": source_id, "source": source})
            for table in TABLES:
                write({"type": "table_begin", "source_id": source_id, "table": table})
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            try:
                while selector.get_map():
                    if time.monotonic() - started > max_seconds:
                        raise RuntimeError("time_limit")
                    if shutil.disk_usage(output.parent).free < min_free_bytes:
                        raise RuntimeError("disk_reserve_limit")
                    for key, _ in selector.select(timeout=0.5):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        if key.data == "stderr":
                            stderr_hash.update(chunk)
                            stderr_bytes += len(chunk)
                            continue
                        for statement in scanner.feed(chunk):
                            try:
                                table, row = parse_core_insert(statement)
                            except ValueError as exc:
                                errors[str(exc)] += 1
                                continue
                            ordinal = counts[table] + 1
                            write(
                                {
                                    "type": "row",
                                    "source_id": source_id,
                                    "table": table,
                                    "ordinal": ordinal,
                                    "row": row,
                                    "row_sha256": digest(row),
                                    "input_sql_sha256": hashlib.sha256(statement).hexdigest(),
                                    "provenance_status": "salvaged_unverified",
                                    "primary_performance_eligible": False,
                                }
                            )
                            counts[table] = ordinal
                list(scanner.feed(b"", final=True))
                exit_code = process.wait(timeout=5)
                if exit_code != 0:
                    stop_reason = "sqlite_recover_nonzero_exit"
            except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
                stop_reason = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
                process.kill()
                process.wait(timeout=10)
                exit_code = process.returncode
            finally:
                selector.close()
                process.stdout.close()
                process.stderr.close()
            for table in TABLES:
                state = "partial_salvage" if stop_reason else "salvaged_unverified"
                info = {"rows": counts[table], "state": state, "primary_performance_eligible": False}
                if stop_reason:
                    info["error"] = stop_reason
                report["tables"][table] = info
                write({"type": "table_end", "source_id": source_id, "table": table, **info}, bounded=False)
            write(
                {
                    "type": "source_end",
                    "source_id": source_id,
                    "source_metadata_unchanged": (before.st_size, before.st_mtime_ns)
                    == (copy.stat().st_size, copy.stat().st_mtime_ns),
                    "recovery_status": "partial_salvage" if stop_reason else "salvaged_unverified",
                    "primary_performance_eligible": False,
                },
                bounded=False,
            )
        report.update(
            {
                "rows": sum(counts.values()),
                "uncompressed_core_bytes": total_bytes,
                "compressed_bytes": partial.stat().st_size,
                "sha256": file_sha256(partial),
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "exit_code": exit_code,
                "stop_reason": stop_reason,
                "parse_errors": dict(errors),
                "scanner_counts": dict(scanner.counts),
                "stderr_bytes": stderr_bytes,
                "stderr_sha256": stderr_hash.hexdigest(),
                "stderr_raw_retained": False,
            }
        )
    report["copy_sha256_after"] = file_sha256(copy)
    report["copy_unchanged"] = report["copy_sha256_after"] == expected
    if not report["copy_unchanged"]:
        raise RuntimeError("Disposable source changed; partial artifact retained for investigation")
    os.link(partial, output)
    partial.unlink()
    manifest = output.with_name(output.name + ".manifest.json")
    with manifest.open("x") as f:
        os.chmod(manifest, 0o600)
        json.dump(report, f, indent=2)
        f.write("\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--copy", required=True, type=Path)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--max-seconds", type=int, default=600)
    parser.add_argument("--max-output-bytes", type=int, default=500 << 20)
    parser.add_argument("--min-free-bytes", type=int, default=6 << 30)
    args = parser.parse_args()
    report = recover_core(
        args.copy,
        args.out,
        json.loads(args.provenance.read_text()),
        max_seconds=args.max_seconds,
        max_output_bytes=args.max_output_bytes,
        min_free_bytes=args.min_free_bytes,
    )
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "rows",
                    "tables",
                    "stop_reason",
                    "parse_errors",
                    "copy_unchanged",
                    "sha256",
                    "elapsed_seconds",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
