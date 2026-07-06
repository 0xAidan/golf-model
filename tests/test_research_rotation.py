"""Research artifact rotation (D5)."""

from __future__ import annotations

import gzip
import os
import time

from src.output_manager import rotate_research_artifacts, summarize_research_output


def test_rotate_research_artifacts_archives_old_files(tmp_path) -> None:
    research = tmp_path / "output" / "research"
    archive = tmp_path / "data" / "exports" / "research_archive"
    research.mkdir(parents=True)
    old_file = research / "ledger_old.jsonl"
    old_file.write_text('{"trial": 1}\n', encoding="utf-8")
    stale = time.time() - (100 * 86400)
    os.utime(old_file, (stale, stale))

    recent = research / "ledger_recent.jsonl"
    recent.write_text('{"trial": 2}\n', encoding="utf-8")

    result = rotate_research_artifacts(
        research_dir=research,
        archive_dir=archive,
        retain_days=90,
        dry_run=False,
    )

    assert result["ok"] is True
    assert result["archived_count"] == 1
    assert old_file.exists() is False
    assert recent.exists() is True
    archives = list(archive.glob("*.gz"))
    assert len(archives) == 1
    with gzip.open(archives[0], "rt", encoding="utf-8") as gz:
        assert '"trial": 1' in gz.read()


def test_rotate_research_artifacts_dry_run(tmp_path) -> None:
    research = tmp_path / "research"
    archive = tmp_path / "archive"
    research.mkdir(parents=True)
    old_file = research / "study.db"
    old_file.write_bytes(b"sqlite")
    stale = time.time() - (120 * 86400)
    os.utime(old_file, (stale, stale))

    result = rotate_research_artifacts(
        research_dir=research,
        archive_dir=archive,
        retain_days=90,
        dry_run=True,
    )

    assert result["archived_count"] == 1
    assert old_file.exists() is True
    assert list(archive.glob("*")) == []


def test_summarize_research_output(tmp_path) -> None:
    research = tmp_path / "research"
    research.mkdir()
    (research / "a.txt").write_text("hello", encoding="utf-8")

    summary = summarize_research_output(research_dir=research)

    assert summary["file_count"] == 1
    assert summary["bytes"] >= 5
