"""
Output File Manager

Keeps the output/ directory clean by archiving previous versions
when new predictions are generated. Only the latest card and
methodology per tournament live in output/; older versions go to
output/archive/.
"""

import glob
import gzip
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("output_manager")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_RESEARCH_DIR = _REPO_ROOT / "output" / "research"
_DEFAULT_RESEARCH_ARCHIVE = _REPO_ROOT / "data" / "exports" / "research_archive"


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
            shutil.move(old_file, dest)
            logger.info("Archived %s -> archive/%s", basename, basename)
            archived += 1
        return archived

    matches = glob.glob(pattern)
    archived = 0
    for old_file in matches:
        basename = os.path.basename(old_file)
        dest = os.path.join(archive_dir, basename)
        shutil.move(old_file, dest)
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
        shutil.move(f, dest)
        actions["research"].append(os.path.basename(f))

    remaining = [f for f in all_files if f not in research_files]

    shadow_files = [f for f in remaining if os.path.basename(f).startswith("shadow_")]
    backtest_files = [f for f in remaining if "backtest" in os.path.basename(f)]
    for f in shadow_files + backtest_files:
        dest = os.path.join(archive_dir, os.path.basename(f))
        shutil.move(f, dest)
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
            shutil.move(f, dest)
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
        dest = archive_path / dest_name
        entry = {
            "source": _display_path(source),
            "archive": _display_path(dest),
        }
        if dry_run:
            archived.append(entry)
            continue

        try:
            with open(source, "rb") as raw, gzip.open(dest, "wb", compresslevel=6) as gz:
                shutil.copyfileobj(raw, gz)
            if dest.stat().st_size <= 0:
                raise OSError("empty gzip archive")
            source.unlink()
            archived.append(entry)
            logger.info("Archived research artifact %s -> %s", source.name, dest.name)
        except OSError as exc:
            errors.append(f"archive failed for {source}: {exc}")
            if dest.exists():
                try:
                    dest.unlink()
                except OSError:
                    pass

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
