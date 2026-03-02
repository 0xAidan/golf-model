"""
Output File Manager

Keeps the output/ directory clean by archiving previous versions
when new predictions are generated. Only the latest card and
methodology per tournament live in output/; older versions go to
output/archive/.
"""

import glob
import logging
import os
import shutil

logger = logging.getLogger("output_manager")


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
