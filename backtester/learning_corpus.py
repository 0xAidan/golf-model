"""Verified, provenance-preserving research corpus. No recovered forensic SQL is admitted."""
from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path

from backtester.learning_challenger import canonical_hash, load_source
from src.models.learning_challenger import SG_COMPONENTS, day, finite, provider_player_key

TABLES = {"rounds", "historical_event_info"}
TABLE_MARKERS = tuple(token for table in sorted(TABLES) for token in (
    f'"table":"{table}"'.encode(), f'"table": "{table}"'.encode()
))


class HashReader:
    def __init__(self, handle):
        self.handle, self.digest = handle, hashlib.sha256()

    def read(self, size=-1):
        chunk = self.handle.read(size)
        self.digest.update(chunk)
        return chunk


def add_snapshot_references(tables: dict, source: dict) -> None:
    """Bind newly extracted rows to their original transaction and exact source values."""
    for table in TABLES:
        for index, row in enumerate(tables.get(table, []), 1):
            if row.get("_source_refs"):
                continue
            raw_hash = hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
            row.setdefault("_source_refs", [{"snapshot_sha256": source["source_sha256"], "table": table,
                                             "ordinal": index, "row_sha256": raw_hash}])


def load_verified_corpus(manifests: list[Path], *, production: Path | None = None) -> tuple[dict, dict]:
    """Verify compressed logical streams while reading each once, and retain row references."""
    tables, origins = defaultdict(list), []
    for path in manifests:
        manifest = json.loads(path.read_text())
        logical = manifest["logical"]
        if (manifest.get("state") != "complete" or manifest.get("quick_check") != ["ok"]
                or not manifest.get("preservation", {}).get("readback_verified")):
            raise ValueError("Unverified preservation snapshot cannot enter training")
        if any(logical["tables"].get(table, {}).get("state") != "complete" for table in TABLES):
            raise ValueError("Required research tables are incomplete")
        counts = Counter()
        with Path(logical["path"]).open("rb") as raw:
            hashed = HashReader(raw)
            with gzip.GzipFile(fileobj=hashed) as stream:
                for line in stream:
                    if not any(token in line for token in TABLE_MARKERS):
                        continue
                    item = json.loads(line)
                    if item.get("type") != "row" or item.get("table") not in TABLES:
                        continue
                    table, row = item["table"], item["row"]
                    row_digest = hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
                    if row_digest != item["row_sha256"]:
                        raise ValueError("Verified logical row hash mismatch")
                    row["_source_refs"] = [{"snapshot_sha256": manifest["source_id"],
                                             "logical_sha256": logical["sha256"],
                                             "table": table, "ordinal": item["ordinal"],
                                             "row_sha256": item["row_sha256"]}]
                    tables[table].append(row)
                    counts[table] += 1
            if hashed.digest.hexdigest() != logical["sha256"]:
                raise ValueError("Verified logical vault hash mismatch")
        if any(counts[t] != logical["tables"][t]["rows"] for t in TABLES):
            raise ValueError("Verified logical row count mismatch")
        origins.append({"manifest": str(path), "snapshot_sha256": manifest["source_id"],
                        "logical_sha256": logical["sha256"], "counts": dict(counts), "verified": True})
    if production:
        newer, source = load_source(production)
        add_snapshot_references(newer, source)
        for table in TABLES:
            for row in newer.get(table, []):
                tables[table].append(row)
        origins.append({"source": str(production), **source, "verified": True})
    return deduplicate(dict(tables), origins)


def deduplicate(tables: dict, origins: list[dict]) -> tuple[dict, dict]:
    """Conflicts are excluded, never resolved using outcomes or source profitability."""
    unique, conflicts = {}, set()
    counts = Counter()
    for raw in tables.get("rounds", []):
        row = dict(raw)
        identity = provider_player_key(row)
        if identity is None:
            counts["missing_provider_identity_rounds_excluded"] += 1
            continue
        row["provider_player_key"] = identity
        row["_source_refs"] = [dict(ref) for ref in raw.get("_source_refs", [])]
        row["_source_aliases"] = list(raw.get("_source_aliases", []))
        alias = {k: row.get(k) for k in ("player_key", "player_name")}
        if alias not in row["_source_aliases"]:
            row["_source_aliases"].append(alias)
        key = (str(row.get("tour") or "").lower(), str(row.get("event_id")), int(row.get("year") or 0),
               identity, int(row.get("round_num") or 0))
        if key not in unique:
            unique[key] = row
            continue
        old = unique[key]
        disagreement = any(finite(old.get(c)) is not None and finite(row.get(c)) is not None
                           and finite(old[c]) != finite(row[c]) for c in (*SG_COMPONENTS, "score"))
        disagreement |= any(old.get(c) is not None and row.get(c) is not None and str(old[c]) != str(row[c])
                            for c in ("event_completed", "course_num", "fin_text"))
        if disagreement:
            conflicts.add(key)
        for field, value in row.items():
            if old.get(field) is None:
                old[field] = value
        old.setdefault("_source_refs", []).extend(row.get("_source_refs", []))
        for alias in row["_source_aliases"]:
            if alias not in old["_source_aliases"]:
                old["_source_aliases"].append(alias)
        counts["duplicate_round_observations"] += 1
    calendar, calendar_conflicts = {}, set()
    for row in tables.get("historical_event_info", []):
        key = (str(row.get("tour") or "").lower(), str(row.get("event_id")), int(row.get("year") or 0))
        if key not in calendar:
            calendar[key] = dict(row)
            calendar[key]["_source_refs"] = [dict(ref) for ref in row.get("_source_refs", [])]
            continue
        old = calendar[key]
        if day(old.get("start_date")) != day(row.get("start_date")):
            calendar_conflicts.add(key)
        if str(old.get("course_id")) != str(row.get("course_id")):
            old["course_id"] = None
            counts["calendar_course_disagreements"] += 1
        old.setdefault("_source_refs", []).extend(row.get("_source_refs", []))
        counts["duplicate_calendar_observations"] += 1
    cleaned = {"rounds": [r for k, r in unique.items() if k not in conflicts],
               "historical_event_info": [r for k, r in calendar.items() if k not in calendar_conflicts]}
    for rows in cleaned.values():
        for row in rows:
            for field in ("_source_refs", "_source_aliases"):
                if field in row:
                    row[field] = sorted({canonical_hash(item): item for item in row[field]}.values(), key=canonical_hash)
    counts.update({"conflicting_round_identities_excluded": len(conflicts),
                   "conflicting_calendar_identities_excluded": len(calendar_conflicts),
                   "unique_rounds": len(cleaned["rounds"]), "unique_calendar_events": len(cleaned["historical_event_info"])})
    digest = canonical_hash({table: sorted((canonical_hash(row) for row in rows)) for table, rows in cleaned.items()})
    source = {"source_sha256": digest, "origins": origins, "deduplication": dict(counts),
              "player_identity": "tour:datagolf:dg_id; human aliases retained only as provenance",
              "forensic_sql_admitted": False, "table_counts": {t: len(r) for t, r in cleaned.items()}}
    return cleaned, source


def save_cache(path: Path, tables: dict, source: dict) -> None:
    """Append an exclusive small corpus; references retain every admitted source observation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as raw, gzip.GzipFile(fileobj=raw, filename="", mode="wb", mtime=0) as stream:
        stream.write(json.dumps({"table": "_manifest", "row": source}, sort_keys=True).encode() + b"\n")
        for table, rows in tables.items():
            for row in rows:
                stream.write(json.dumps({"table": table, "row": row}, sort_keys=True).encode() + b"\n")


def preserve_training_snapshot(output: Path, tables: dict, source: dict) -> dict:
    """Retain the exact effective corpus before fitting, including WAL-visible weekly rows."""
    selected = {table: tables.get(table, []) for table in sorted(TABLES)}
    digest = canonical_hash({table: sorted(canonical_hash(row) for row in rows) for table, rows in selected.items()})
    if digest != source["source_sha256"]:
        raise ValueError("Training snapshot does not match canonical corpus identity")
    destination = output / "sources" / f"{digest}.jsonl.gz"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        save_cache(destination, selected, {k: v for k, v in source.items() if k != "training_snapshot"})
    # Read back one row at a time. Loading another full object graph (and its
    # sorted JSON source hash) can exceed the isolated service's memory cap.
    hashes = {table: [] for table in sorted(TABLES)}
    with gzip.open(destination, "rt") as stream:
        for line in stream:
            item = json.loads(line)
            if item["table"] in hashes:
                hashes[item["table"]].append(canonical_hash(item["row"]))
            elif item["table"] != "_manifest":
                raise ValueError("Unexpected table in retained training corpus")
    verified = canonical_hash({table: sorted(rows) for table, rows in hashes.items()})
    if verified != digest or any(len(hashes[table]) != len(selected[table]) for table in hashes):
        raise ValueError("Retained training corpus readback mismatch")
    with destination.open("rb") as handle:
        compressed_hash = hashlib.file_digest(handle, "sha256").hexdigest()
    return {"path": str(destination.resolve()), "sha256": compressed_hash, "corpus_sha256": digest,
            "bytes": destination.stat().st_size, "table_counts": {table: len(rows) for table, rows in selected.items()},
            "readback_verified": True, "state": "complete"}
