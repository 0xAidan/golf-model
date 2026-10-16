#!/usr/bin/env python3
"""Read-only stdlib collector: stream golf output cards and provenance as tar.gz.

Designed to run via SSH stdin. Never extracts an archive or writes on the server.
Secrets and application state outside golf output directories are not collected.
"""
from __future__ import annotations
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import zipfile

MAX_MEMBER = 32 * 1024 * 1024
SKIP = {".git", "node_modules", ".cursor", "skills", ".venv", "venv", "__pycache__", "site-packages"}


def main():
    roots = [Path("/opt"), Path("/root/golf-model"), Path("/root/opt/golf-model"), Path("/root/.config/superpowers/worktrees/golf-model")]
    sources, omitted, sent = [], [], set()
    with tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz") as archive:
        def add(data, path, *, container=None, member=None):
            sha = hashlib.sha256(data).hexdigest()
            extension = ".md" if str(member or path).lower().endswith(".md") else ".json"
            relative = f"corpus/{sha}{extension}"
            sources.append({"sha256": sha, "corpus_path": relative, "source_path": str(path),
                            "container_path": str(container) if container else None, "member_path": member,
                            "bytes": len(data), "location": "golf-vps", "collection_mode": "read_only"})
            if relative not in sent:
                item = tarfile.TarInfo(relative)
                item.size, item.mode = len(data), 0o600
                archive.addfile(item, io.BytesIO(data))
                sent.add(relative)

        for top in roots:
            if not top.exists():
                continue
            for directory, dirs, files in os.walk(top):
                dirs[:] = [d for d in dirs if d not in SKIP]
                parent = Path(directory)
                if "golf" not in str(parent).lower():
                    continue
                parts = set(parent.parts)
                allowed = bool(parts & {"output", "local_recovery", "research_archive", "predictions", "md_cards"})
                for filename in sorted(files):
                    path = parent / filename
                    if path.is_symlink() or filename.startswith("._"):
                        continue
                    is_snapshot = filename.startswith(("live_refresh_snapshot", "pre_tournament", "pre_teeoff", "prediction_snapshot")) and filename.endswith(".json")
                    if not allowed and not is_snapshot:
                        continue
                    suffix = path.suffix.lower()
                    if suffix not in {".md", ".zip", ".json"}:
                        continue
                    before = path.stat()
                    if before.st_size > MAX_MEMBER:
                        omitted.append({"path": str(path), "reason": "member_size_limit", "bytes": before.st_size})
                        continue
                    if suffix == ".zip":
                        with zipfile.ZipFile(path) as z:
                            for member in z.infolist():
                                if member.is_dir() or not member.filename.lower().endswith(".md") or "__MACOSX" in member.filename or Path(member.filename).name.startswith("._"):
                                    continue
                                if member.file_size > MAX_MEMBER:
                                    omitted.append({"path": str(path), "member": member.filename, "reason": "member_size_limit"})
                                    continue
                                add(z.read(member), path, container=path, member=member.filename)
                    else:
                        add(path.read_bytes(), path)
                    after = path.stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        omitted.append({"path": str(path), "reason": "changed_during_read"})
        body = "".join(json.dumps(s, sort_keys=True) + "\n" for s in sources).encode()
        item = tarfile.TarInfo("sources.jsonl")
        item.size, item.mode = len(body), 0o600
        archive.addfile(item, io.BytesIO(body))
        body = json.dumps({"references": len(sources), "unique_contents": len(sent), "omitted": omitted}, indent=2).encode()
        item = tarfile.TarInfo("collection-summary.json")
        item.size, item.mode = len(body), 0o600
        archive.addfile(item, io.BytesIO(body))


if __name__ == "__main__":
    main()
