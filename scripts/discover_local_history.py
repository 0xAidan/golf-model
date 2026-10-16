#!/usr/bin/env python3
"""Read-only filesystem/archive discovery into a new content-addressed MD corpus.

Never extracts archive paths or opens databases. Source bytes remain unchanged;
every recovered Markdown payload receives a SHA-256 name and all source wrappers
remain distinct provenance entries. Existing corpus entries can be augmented.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import signal
import stat
import subprocess
import tarfile
import zipfile

EXCLUDED = ["node_modules", ".git", ".venv", "venv", "__pycache__", ".next", ".pytest_cache", "Caches", ".cache", ".codex", ".cursor", ".claude", ".agents", ".ssh", ".npm", ".cargo", ".rustup", "DerivedData", ".Trash"]
EXTENSIONS = ["*.md", "*.markdown", "*.md.gz", "*.json", "*.json.gz", "*.jsonl", "*.jsonl.gz", "*.csv", "*.db", "*.sqlite", "*.sqlite3", "*.db.gz", "*.sqlite.gz", "*.zip", "*.tar.gz", "*.tgz"]
NAME_HINT = re.compile(r"golf|pga|(?:^|[/ _-])md[ _-]*cards?|(?:betting|prediction)[ _-]*cards?|(?:wm[ _-]*phoenix|pebble|genesis|cognizant|arnold[ _-]*palmer|players[ _-]*championship|valspar|houston[ _-]*open|valero|masters[ _-]*tournament|rbc[ _-]*(?:heritage|canadian)|truist|cadillac|memorial[ _-]*tournament|us[ _.]*open|u\.s\.[ _]*open|travelers[ _-]*championship|john[ _-]*deere|3m[ _-]*open|scottish[ _-]*open|the[ _-]*open[ _-]*championship|wyndham|rocket[ _-]*classic|fedex|bmw[ _-]*championship|tour[ _-]*championship|baycurrent|bank[ _-]*of[ _-]*utah|bermuda[ _-]*championship)", re.I)
CONTENT_HINT = re.compile(r"(?im)^(?:#{1,4}\s+.*(?:betting card|power rankings|golf model|tournament.*card)|\*\*Tournament\*\*:|\|\s*(?:Rank\s*\|\s*Player|Player\s*\|.*(?:Win|Odds|EV|Composite)))")
SECRET_HINT = re.compile(r"(?:^|[/_. -])(?:secrets?|credentials?|api[_ -]?keys?|tokens?|passwords?)(?:[/_. -]|$)", re.I)


def source_kind(path: str, title: str | None = None) -> str:
    value = path.lower()
    if "/__macosx/" in value or Path(value.split("!")[-1]).name.startswith("._"):
        return "macos_resource_fork"
    if any(part in value for part in ("output/research/", "exports/research_archive/")):
        return "research_trial_output"
    if any(part in value for part in ("/sandbox", "/backtests/", "/shadow_")):
        return "sandbox_or_backtest_output"
    if "methodology" in value:
        return "methodology_document"
    if any(part in value for part in ("/docs/", "/audits/", "/qa/")):
        return "supporting_report"
    if "live_refresh_snapshot" in value or "live-refresh-snapshot" in value:
        return "published_snapshot_candidate"
    if "trackrecord" in value:
        return "historical_track_record"
    if "provenance" in Path(value.split("!")[-1]).name:
        return "prediction_run_provenance"
    if "betting card" in (title or "").lower() or "/md cards/" in value:
        return "original_card_candidate"
    return "other_generated_or_supporting_output"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path: Path):
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.name.endswith(".gz") else data)


def scan(root: Path, seconds: int) -> tuple[list[str], dict]:
    arguments = ["rg", "--files", "--hidden", "--no-ignore", str(root)]
    for pattern in EXTENSIONS:
        arguments += ["-g", pattern]
    for item in EXCLUDED:
        arguments += ["-g", f"!**/{item}/**"]
    arguments += ["-g", "!**/*.app/**"]
    if root == Path.home():
        arguments += ["-g", "!**/Library/**"]
    try:
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=seconds)
        output, error, state = result.stdout, result.stderr, f"exit_{result.returncode}"
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""
        error = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr or ""
        state = "timeout_partial_listing"
    paths = output.splitlines()
    return paths, {"root": str(root), "state": state, "listed_files": len(paths), "errors": error.splitlines()}


class Collector:
    def __init__(self, output: Path):
        self.output = output.resolve()
        self.corpus = self.output / "corpus"
        self.corpus.mkdir(parents=True, exist_ok=True)
        self.entries, self.files, self.errors, self.prior_scans, self.structured_entries = [], [], [], [], []
        self.structured_known = set()
        self.known = set()
        sources = self.output / "sources.jsonl"
        if sources.exists():
            self.entries = [json.loads(line) for line in sources.read_text().splitlines() if line]
            self.known = {(row["source_path"], row["sha256"]) for row in self.entries}
        structured = self.output / "structured_sources.jsonl"
        if structured.exists():
            self.structured_entries = [json.loads(line) for line in structured.read_text().splitlines() if line]
            self.structured_known = {(row["source_path"], row["sha256"]) for row in self.structured_entries}
        inventory = self.output / "files.jsonl"
        if inventory.exists():
            self.files = [json.loads(line) for line in inventory.read_text().splitlines() if line]
        summary = self.output / "summary.json"
        if summary.exists():
            previous = json.loads(summary.read_text())
            self.errors, self.prior_scans = previous.get("errors", []), previous.get("scans", [])

    def markdown(self, data: bytes, source_path: str, **metadata) -> None:
        if source_path.split("!")[-1].split("/")[-1].startswith("._") or "/__MACOSX/" in source_path:
            return
        sha = hashlib.sha256(data).hexdigest()
        identity = (source_path, sha)
        if identity in self.known:
            return
        path = self.corpus / f"{sha}.md.gz"
        if not path.exists():
            with path.open("xb") as handle:
                handle.write(gzip.compress(data, compresslevel=6, mtime=0))
        elif hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest() != sha:
            raise ValueError(f"Existing corpus hash mismatch: {path}")
        text = data.decode("utf-8", errors="replace")
        title = next((line.lstrip("# ").strip() for line in text.splitlines() if line.startswith("# ")), None)
        basename = source_path.split("!")[-1].rsplit("/", 1)[-1]
        dates = sorted(set(re.sub(r"[^0-9]", "", value) for value in re.findall(r"(?<!\d)(20(?:25|26)[-_]?(?:0[1-9]|1[0-2])[-_]?(?:0[1-9]|[12]\d|3[01]))(?!\d)", basename)))
        generated = [line[:500] for line in text.splitlines()[:60] if re.search(r"generated|created|timestamp|date|tournament|course|model|version|baseline", line, re.I)]
        row = {"sha256": sha, "corpus_path": str(path), "source_path": source_path, "bytes": len(data), "title": title,
               "filename_dates": dates, "header_evidence": generated, "contains_pipe_table": "\n|" in text,
               "contains_prediction_heading": bool(CONTENT_HINT.search(text)), "source_kind": source_kind(source_path, title), **metadata}
        self.entries.append(row)
        self.known.add(identity)

    def structured(self, data: bytes, source_path: str, **metadata) -> None:
        """Preserve original prediction JSON; parsing/classification is separate."""
        sha = hashlib.sha256(data).hexdigest()
        if (source_path, sha) in self.structured_known:
            return
        directory = self.output / "json_corpus"
        directory.mkdir(exist_ok=True)
        path = directory / f"{sha}.json.gz"
        if not path.exists():
            with path.open("xb") as handle:
                handle.write(gzip.compress(data, compresslevel=6, mtime=0))
        elif hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest() != sha:
            raise ValueError(f"Existing structured corpus hash mismatch: {path}")
        self.structured_entries.append({"sha256": sha, "corpus_path": str(path), "source_path": source_path, "bytes": len(data), "source_kind": source_kind(source_path), **metadata})
        self.structured_known.add((source_path, sha))

    def zip_bytes(self, data: bytes, source_path: str, depth: int = 0) -> None:
        if depth > 4:
            self.errors.append({"source": source_path, "error": "nested_archive_depth_exceeded"})
            return
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            container_sha = hashlib.sha256(data).hexdigest()
            for member in archive.infolist():
                if member.is_dir() or "/__MACOSX/" in "/" + member.filename or Path(member.filename).name.startswith("._"):
                    continue
                name = member.filename.lower()
                if SECRET_HINT.search(member.filename):
                    continue
                if name.endswith((".md", ".markdown", ".md.gz")):
                    payload = archive.read(member)
                    if name.endswith(".gz"):
                        payload = gzip.decompress(payload)
                    self.markdown(payload, f"{source_path}!{member.filename}", container_path=source_path, member_path=member.filename,
                                  container_sha256=container_sha, archive_member_modified_at=list(member.date_time), archive_member_size=member.file_size)
                elif name.endswith(".zip"):
                    self.zip_bytes(archive.read(member), f"{source_path}!{member.filename}", depth + 1)
                elif name.endswith((".json", ".json.gz")):
                    payload = archive.read(member)
                    if name.endswith(".gz"):
                        payload = gzip.decompress(payload)
                    self.structured(payload, f"{source_path}!{member.filename}", container_path=source_path, member_path=member.filename,
                                    container_sha256=container_sha, archive_member_size=member.file_size)

    def archive(self, path: Path) -> None:
        try:
            stat = path.stat()
            if getattr(stat, "st_flags", 0) & 0x40000000:
                self.files.append({"path": str(path), "bytes": stat.st_size, "kind": "archive", "state": "icloud_dataless_pending", "mtime_ns": stat.st_mtime_ns})
                return
            sha = digest(path)
            self.files.append({"path": str(path), "bytes": stat.st_size, "sha256": sha, "kind": "archive", "mtime_ns": stat.st_mtime_ns})
            if path.name.lower().endswith(".zip"):
                self.zip_bytes(path.read_bytes(), str(path))
            else:
                with tarfile.open(path, mode="r|gz") as archive:
                    for member in archive:
                        if not member.isfile() or SECRET_HINT.search(member.name):
                            continue
                        name = member.name.lower()
                        structured = name.endswith((".json", ".json.gz")) and (name.startswith("output/") or "research_archive/" in name or "local_recovery/" in name or name.endswith(("trackrecord.json", "live_refresh_snapshot.json")))
                        if name.endswith((".md", ".markdown", ".md.gz", ".zip")) or structured:
                            stream = archive.extractfile(member)
                            if stream is None:
                                continue
                            payload = stream.read()
                            if name.endswith(".zip"):
                                self.zip_bytes(payload, f"{path}!{member.name}")
                            elif structured:
                                if name.endswith(".gz"):
                                    payload = gzip.decompress(payload)
                                self.structured(payload, f"{path}!{member.name}", container_path=str(path), member_path=member.name,
                                                archive_sha256=sha, archive_member_mtime=member.mtime, archive_member_size=member.size)
                            else:
                                if name.endswith(".gz"):
                                    payload = gzip.decompress(payload)
                                self.markdown(payload, f"{path}!{member.name}", container_path=str(path), member_path=member.name,
                                              archive_sha256=sha, archive_member_mtime=member.mtime, archive_member_size=member.size)
        except (OSError, ValueError, EOFError, tarfile.TarError, zipfile.BadZipFile) as exc:
            self.errors.append({"source": str(path), "error": str(exc)})

    def loose(self, path: Path, content_search: bool = False) -> None:
        try:
            if self.output == path.resolve() or self.output in path.resolve().parents or SECRET_HINT.search(str(path)):
                return
            stat = path.stat()
            name = path.name.lower()
            is_md = name.endswith((".md", ".markdown", ".md.gz"))
            if getattr(stat, "st_flags", 0) & 0x40000000:
                if not content_search:
                    self.files.append({"path": str(path), "bytes": stat.st_size, "kind": "markdown" if is_md else "data_or_report", "state": "icloud_dataless_pending", "mtime_ns": stat.st_mtime_ns, "flags": hex(stat.st_flags)})
                return
            if is_md:
                data = path.read_bytes()
                if name.endswith(".gz"):
                    data = gzip.decompress(data)
                if content_search and not CONTENT_HINT.search(data.decode("utf-8", errors="replace")):
                    return
                self.markdown(data, str(path), mtime_ns=stat.st_mtime_ns, birthtime=getattr(stat, "st_birthtime", None))
            elif not content_search:
                entry = {"path": str(path), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns, "kind": "database" if re.search(r"\.(?:db|sqlite|sqlite3)(?:\.gz)?$", name) else "data_or_report"}
                # Hash all local MD and small data artifacts; large DBs remain metadata-only.
                if stat.st_size <= 100 * 1024 * 1024:
                    entry["sha256"] = digest(path)
                else:
                    entry["hash_state"] = "large_file_metadata_only_not_opened"
                self.files.append(entry)
                if name.endswith((".json", ".json.gz")) and ("/output/" in str(path) or "live-refresh-snapshot" in name or name in {"live_refresh_snapshot.json", "trackrecord.json"}) and stat.st_size <= 100 * 1024 * 1024:
                    data = path.read_bytes()
                    if name.endswith(".gz"):
                        data = gzip.decompress(data)
                    self.structured(data, str(path), mtime_ns=stat.st_mtime_ns, source_file_sha256=entry.get("sha256"))
        except (OSError, ValueError, EOFError) as exc:
            self.errors.append({"source": str(path), "error": str(exc)})

    def save(self, scans: list[dict]) -> dict:
        self.entries.sort(key=lambda row: (row["source_path"], row["sha256"]))
        for row in [*self.entries, *self.structured_entries]:
            row["source_kind"] = source_kind(row["source_path"], row.get("title"))
            row["source_context"] = ("Finder resource-fork metadata, not a forecast payload." if row["source_kind"] == "macos_resource_fork" else "Research trial/backtest output is not an issued forecast." if row["source_kind"] in {"research_trial_output", "sandbox_or_backtest_output"} else "Original preserved source; generation/publication time and event identity require reconciliation.")
        inventory = {}
        for row in self.files:
            inventory.setdefault(row["path"], {}).update(row)
        self.files = list(inventory.values())
        recovered = {row["source_path"]: row for row in [*self.entries, *self.structured_entries] if "!" not in row["source_path"]}
        for row in self.files:
            if row["path"] in recovered:
                row.update(state="recovered", sha256=recovered[row["path"]]["sha256"], corpus_path=recovered[row["path"]]["corpus_path"])
        self.structured_entries.sort(key=lambda row: (row["source_path"], row["sha256"]))
        for name, rows in (("sources.jsonl", self.entries), ("structured_sources.jsonl", self.structured_entries), ("files.jsonl", self.files)):
            temporary = self.output / f"{name}.tmp"
            with temporary.open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            temporary.replace(self.output / name)
        dates = sorted({date for row in self.entries for date in row.get("filename_dates", [])})
        summary = {"schema_version": 1, "collected_at_utc": datetime.now(timezone.utc).isoformat(),
                   "corpus_root": str(self.corpus), "markdown_source_occurrences": len(self.entries),
                   "distinct_markdown_hashes": len({row["sha256"] for row in self.entries}),
                   "duplicate_source_occurrences": len(self.entries) - len({row["sha256"] for row in self.entries}),
                   "structured_source_occurrences": len(self.structured_entries), "distinct_structured_hashes": len({row["sha256"] for row in self.structured_entries}),
                   "distinct_payload_bytes": sum({row["sha256"]: row["bytes"] for row in self.entries}.values()),
                   "distinct_corpus_bytes": sum(path.stat().st_size for path in self.corpus.glob("*.md.gz")), "corpus_encoding": "gzip",
                   "filename_date_range": [dates[0], dates[-1]] if dates else None,
                   "inventory_files": len(self.files), "icloud_pending_files": sum(row.get("state") == "icloud_dataless_pending" for row in self.files),
                   "errors": self.errors, "scans": self.prior_scans + scans,
                   "limitations": ["A filename or filesystem timestamp does not prove pre-event publication.",
                                   "Markdown payloads include research/backtest/supporting documents as well as original cards; parser must retain section context.",
                                   "No originals were edited, moved, imported, initialized or deleted. Large databases were listed without opening."]}
        (self.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, action="append", default=[])
    parser.add_argument("--paths-json", type=Path, action="append", default=[])
    parser.add_argument("--archive", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scan-seconds", type=int, default=120)
    parser.add_argument("--inventory-only", action="store_true", help="List relevant source metadata without reading file payloads")
    args = parser.parse_args()
    collector, scans, all_paths = Collector(args.output), [], set()
    for path_list in args.paths_json:
        all_paths.update(read_json(path_list))
    for root in args.root:
        paths, audit = scan(root, args.scan_seconds)
        all_paths.update(paths)
        scans.append(audit)
        print(json.dumps(audit), flush=True)
    listed = args.output / "listed-paths.json.gz"
    previous_paths = read_json(listed) if listed.exists() else []
    payload = json.dumps(sorted(set(previous_paths) | all_paths), ensure_ascii=False).encode()
    temporary = listed.with_name(f".{listed.name}.tmp")
    temporary.write_bytes(gzip.compress(payload, compresslevel=6, mtime=0))
    temporary.replace(listed)
    archive_paths = set(args.archive)
    def timed_out(_signal, _frame):
        raise TimeoutError("file_metadata_or_read_timeout_after_10_seconds")
    signal.signal(signal.SIGALRM, timed_out)
    for index, text in enumerate(sorted(all_paths)):
        path = Path(text)
        if str(collector.output) in text or SECRET_HINT.search(text) or any(f"/{excluded}/" in text for excluded in EXCLUDED):
            continue
        if args.inventory_only and not NAME_HINT.search(text):
            continue
        signal.setitimer(signal.ITIMER_REAL, 10)
        try:
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                continue
            relevant = bool(NAME_HINT.search(text))
            name = path.name.lower()
            if args.inventory_only:
                if relevant:
                    collector.files.append({"path": text, "bytes": metadata.st_size, "mtime_ns": metadata.st_mtime_ns,
                                            "kind": "metadata_inventory", "state": "icloud_dataless_pending" if getattr(metadata, "st_flags", 0) & 0x40000000 else "available_not_collected", "flags": hex(getattr(metadata, "st_flags", 0))})
            elif name.endswith((".zip", ".tar.gz", ".tgz")):
                if relevant and not any(excluded in name for excluded in ("quarantines-with-sidecars", "history-evidence-vault")):
                    archive_paths.add(path)
                elif name.endswith(".zip") and not getattr(metadata, "st_flags", 0) & 0x40000000:
                    try:
                        with zipfile.ZipFile(path) as archive:
                            if any(NAME_HINT.search(member.filename) and member.filename.lower().endswith((".md", ".json", ".csv")) for member in archive.infolist()):
                                archive_paths.add(path)
                    except (OSError, zipfile.BadZipFile):
                        pass
            elif relevant:
                collector.loose(path)
            elif name.endswith((".md", ".markdown")) and metadata.st_size <= 2 * 1024 * 1024:
                collector.loose(path, content_search=True)
        except (OSError, ValueError) as exc:
            collector.errors.append({"source": text, "error": str(exc)})
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        if index and index % 10000 == 0:
            print(json.dumps({"paths_inspected": index, "recovered_markdown_sources": len(collector.entries)}), flush=True)
            collector.save(scans)
    for path in sorted(archive_paths):
        print(json.dumps({"reading_archive": str(path)}), flush=True)
        collector.archive(path)
        collector.save(scans)
    print(json.dumps(collector.save(scans), indent=2), flush=True)


if __name__ == "__main__":
    main()
