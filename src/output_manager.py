"""
Output File Manager

Keeps the output/ directory clean by archiving previous versions
when new predictions are generated. Only the latest card and
methodology per tournament live in output/; older versions go to
output/archive/.
"""

import glob
import gzip
import hashlib
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.history_preservation import prediction_history_preservation_enabled, preservation_skip

logger = logging.getLogger("output_manager")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_RESEARCH_DIR = _REPO_ROOT / "output" / "research"
_DEFAULT_RESEARCH_ARCHIVE = _REPO_ROOT / "data" / "exports" / "research_archive"


def _file_hash(path: Path, *, compressed: bool = False) -> str:
    digest = hashlib.sha256()
    opener = gzip.open if compressed else open
    with opener(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _unique_archive_path(source: Path, destination: Path, *, compressed: bool = False) -> tuple[Path, bool]:
    """Never replace different historical bytes, including flattened-name collisions."""
    original_hash = _file_hash(source)
    candidate = destination
    while candidate.exists():
        try:
            if _file_hash(candidate, compressed=compressed) == original_hash:
                return candidate, True
        except (OSError, EOFError):
            pass
        suffix = original_hash if candidate == destination else f"{original_hash}.{uuid4().hex[:8]}"
        candidate = destination.with_name(f"{destination.stem}.{suffix}{destination.suffix}")
    return candidate, False


def _archive_card(source: str, destination: str) -> str:
    original = Path(source)
    target, existing = _unique_archive_path(original, Path(destination))
    target.parent.mkdir(parents=True, exist_ok=True)
    if not existing:
        with original.open("rb") as raw, target.open("xb") as output:
            shutil.copyfileobj(raw, output)
        if _file_hash(original) != _file_hash(target):
            raise OSError(f"Archive copy verification failed for {original}")
        shutil.copystat(original, target)
    if not prediction_history_preservation_enabled():
        original.unlink()
    return str(target)


def write_versioned_output(path: str | Path, text: str, *, encoding: str = "utf-8") -> str:
    """Write a new forecast artifact exclusively; return its actual versioned path."""
    requested = Path(path)
    if not prediction_history_preservation_enabled():
        requested.write_text(text, encoding=encoding)
        return str(requested)
    candidate = requested
    while True:
        try:
            with candidate.open("x", encoding=encoding) as handle:
                handle.write(text)
            return str(candidate)
        except FileExistsError:
            stamp = datetime.now(timezone.utc).strftime("%H%M%S_%f")
            candidate = requested.with_name(f"{requested.stem}_{stamp}_{uuid4().hex[:8]}{requested.suffix}")


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


def archive_previous(output_dir: str, safe_name: str, file_type: str = "card") -> int:
    """
    Move previous versions of a tournament's output to archive/.

    Returns the number of files archived.
    """
    archive_dir = os.path.join(output_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)

    if file_type == "methodology":
        pattern = os.path.join(output_dir, f"{safe_name}_methodology*.md")
    elif file_type == "shadow":
        pattern = os.path.join(output_dir, f"shadow_{safe_name}*.md")
    else:
        patterns = [
            os.path.join(output_dir, f"{safe_name}_2*.md"),
            os.path.join(output_dir, f"{safe_name}_backtest*.md"),
        ]
        matches = []
        for p in patterns:
            matches.extend(glob.glob(p))
        archived = 0
        for old_file in matches:
            basename = os.path.basename(old_file)
            if basename.startswith("shadow_") or "_methodology" in basename:
                continue
            dest = os.path.join(archive_dir, basename)
            _archive_card(old_file, dest)
            logger.info("Archived %s -> archive/%s", basename, basename)
            archived += 1
        return archived

    matches = glob.glob(pattern)
    archived = 0
    for old_file in matches:
        basename = os.path.basename(old_file)
        dest = os.path.join(archive_dir, basename)
        _archive_card(old_file, dest)
        logger.info("Archived %s -> archive/%s", basename, basename)
        archived += 1
    return archived


def cleanup_output_directory(output_dir: str = "output") -> dict:
    """
    One-time cleanup: organize existing output files.

    Moves research docs to output/research/, shadow/backtest files
    to output/archive/, and for each tournament keeps only the latest
    card and methodology in output/.

    Returns a summary dict of actions taken.
    """
    archive_dir = os.path.join(output_dir, "archive")
    research_dir = os.path.join(output_dir, "research")
    os.makedirs(archive_dir, exist_ok=True)
    os.makedirs(research_dir, exist_ok=True)

    actions = {"archived": [], "research": [], "kept": []}

    all_files = glob.glob(os.path.join(output_dir, "*.md"))
    if not all_files:
        return actions

    research_files = [f for f in all_files if os.path.basename(f).startswith("research_")]
    for f in research_files:
        dest = os.path.join(research_dir, os.path.basename(f))
        _archive_card(f, dest)
        actions["research"].append(os.path.basename(f))

    remaining = [f for f in all_files if f not in research_files]

    shadow_files = [f for f in remaining if os.path.basename(f).startswith("shadow_")]
    backtest_files = [f for f in remaining if "backtest" in os.path.basename(f)]
    for f in shadow_files + backtest_files:
        dest = os.path.join(archive_dir, os.path.basename(f))
        _archive_card(f, dest)
        actions["archived"].append(os.path.basename(f))

    remaining = [f for f in remaining if f not in shadow_files and f not in backtest_files]

    tournaments = {}
    for f in remaining:
        basename = os.path.basename(f)
        is_methodology = "_methodology" in basename
        parts = basename.replace("_methodology", "").replace(".md", "")
        date_suffix = parts[-8:] if len(parts) >= 8 and parts[-8:].isdigit() else ""
        tournament_key = parts[:-9] if date_suffix else parts

        if "_v" in tournament_key:
            tournament_key = tournament_key[:tournament_key.rindex("_v")]

        file_type = "methodology" if is_methodology else "card"
        key = (tournament_key, file_type)
        if key not in tournaments:
            tournaments[key] = []
        tournaments[key].append((f, date_suffix, basename))

    for (tournament_key, file_type), files in tournaments.items():
        files.sort(key=lambda x: x[1], reverse=True)
        if files:
            actions["kept"].append(os.path.basename(files[0][0]))
        for f, _, basename in files[1:]:
            dest = os.path.join(archive_dir, basename)
            _archive_card(f, dest)
            actions["archived"].append(basename)

    return actions


def rotate_research_artifacts(
    *,
    research_dir: str | os.PathLike[str] | None = None,
    archive_dir: str | os.PathLike[str] | None = None,
    retain_days: int = 90,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Archive-first rotation for autoresearch artifacts older than ``retain_days``.

    Files under ``output/research/`` are gzip-compressed into
    ``data/exports/research_archive/``; originals are removed only after the
    archive file is written successfully.
    """
    research_path = Path(research_dir) if research_dir else _DEFAULT_RESEARCH_DIR
    archive_path = Path(archive_dir) if archive_dir else _DEFAULT_RESEARCH_ARCHIVE

    if not research_path.is_dir():
        return {
            "ok": True,
            "skipped": True,
            "reason": "research directory missing",
            "research_dir": str(research_path),
            "archived": [],
            "dry_run": dry_run,
        }

    if prediction_history_preservation_enabled():
        return preservation_skip(archived=[], archived_count=0, research_dir=str(research_path), dry_run=dry_run)

    archive_path.mkdir(parents=True, exist_ok=True)
    cutoff_ts = time.time() - (int(retain_days) * 86400)
    archived: list[dict[str, Any]] = []
    errors: list[str] = []

    for source in sorted(research_path.rglob("*")):
        if not source.is_file():
            continue
        if source.suffix == ".gz":
            continue
        try:
            mtime = source.stat().st_mtime
        except OSError as exc:
            errors.append(f"stat failed for {source}: {exc}")
            continue
        if mtime >= cutoff_ts:
            continue

        stamp = datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y%m%d")
        dest_name = f"{stamp}_{source.name}.gz"
        dest = archive_path / source.relative_to(research_path).parent / dest_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest, already_archived = _unique_archive_path(source, dest, compressed=True)
        entry = {
            "source": _display_path(source),
            "archive": _display_path(dest),
        }
        if dry_run:
            archived.append(entry)
            continue

        try:
            if not already_archived:
                with open(source, "rb") as raw, open(dest, "xb") as output:
                    with gzip.GzipFile(fileobj=output, mode="wb", compresslevel=6, mtime=0) as gz:
                        shutil.copyfileobj(raw, gz)
            if _file_hash(source) != _file_hash(dest, compressed=True):
                raise OSError("gzip archive content verification failed")
            source.unlink()
            archived.append(entry)
            logger.info("Archived research artifact %s -> %s", source.name, dest.name)
        except OSError as exc:
            errors.append(f"archive failed for {source}: {exc}")
            # Preserve failed artifacts for inspection; never remove an older archive.

    return {
        "ok": not errors,
        "dry_run": dry_run,
        "retain_days": int(retain_days),
        "research_dir": str(research_path),
        "archive_dir": str(archive_path),
        "archived": archived,
        "archived_count": len(archived),
        "errors": errors,
    }


def summarize_research_output(research_dir: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Byte/file totals for ``output/research`` (read-only audit helper)."""
    research_path = Path(research_dir) if research_dir else _DEFAULT_RESEARCH_DIR
    if not research_path.is_dir():
        return {
            "path": str(research_path),
            "file_count": 0,
            "bytes": 0,
            "mb": 0.0,
        }

    file_count = 0
    total_bytes = 0
    for path in research_path.rglob("*"):
        if not path.is_file():
            continue
        file_count += 1
        try:
            total_bytes += path.stat().st_size
        except OSError:
            continue

    return {
        "path": _display_path(research_path),
        "file_count": file_count,
        "bytes": total_bytes,
        "mb": round(total_bytes / (1024 * 1024), 2),
    }
