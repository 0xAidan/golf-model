"""Tests for Tier 2: signal detection, dossiers, operator-gated PR creation."""

from __future__ import annotations

import json

import pytest

from backtester import tier2
from backtester.tier2 import (
    MIN_SEGMENT_N,
    detect_segment_signals,
    run_detection,
    slugify,
    write_hypothesis_dossier,
)


def _line(book: str, outcome: str, implied: float, **extra) -> dict:
    base = {
        "market_type": "tournament_matchups",
        "book": book,
        "implied_prob": implied,
        "outcome": outcome,
    }
    base.update(extra)
    return base


def test_detect_flags_losing_book_segment():
    # 40 losses at even money on 'sketchybook' => strongly negative ROI.
    lines = [_line("sketchybook", "loss", 0.5) for _ in range(40)]
    lines += [_line("goodbook", "win", 0.5) for _ in range(40)]
    signals = detect_segment_signals(lines)
    segs = {s["segment"]: s for s in signals}
    assert "book=sketchybook" in segs
    assert segs["book=sketchybook"]["roi_pct"] < -MIN_SEGMENT_N  # deeply negative
    assert segs["book=sketchybook"]["direction"] == "model_leak"
    assert "book=goodbook" not in segs or segs["book=goodbook"]["roi_pct"] > 0


def test_detect_ignores_small_and_flat_segments():
    lines = [_line("tiny", "loss", 0.5) for _ in range(MIN_SEGMENT_N - 1)]
    assert detect_segment_signals(lines) == []

    flat = [_line("flat", "win" if i % 2 else "loss", 0.5) for i in range(60)]
    assert detect_segment_signals(flat) == []


def test_detect_requires_outcomes():
    lines = [_line("nograde", None, 0.5) for _ in range(50)]
    assert detect_segment_signals(lines) == []


def test_write_dossier_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(tier2, "DOSSIER_DIR", tmp_path)
    signal = {
        "segment": "book=sketchybook",
        "n": 42,
        "roi_pct": -8.5,
        "direction": "model_leak",
        "hypothesis": "test hypothesis",
        "proposed_tier2_action": "investigate",
    }
    path = write_hypothesis_dossier(signal)
    payload = json.loads(path.read_text())
    assert payload["status"].startswith("HYPOTHESIS")
    assert payload["segment"] == "book=sketchybook"
    assert "evaluator_fingerprint" in payload


def test_run_detection_writes_dossiers_and_ledgers(tmp_path, monkeypatch):
    from src import db as db_mod

    monkeypatch.setattr(tier2, "DOSSIER_DIR", tmp_path)

    # In-memory DB with the ledger table + a couple of graded lines.
    conn = db_mod.get_conn() if False else None  # keep linters calm
    import sqlite3

    real_conn = sqlite3.connect(":memory:")
    real_conn.row_factory = sqlite3.Row
    real_conn.execute(
        "CREATE TABLE research_backtest_lines (market_type TEXT, book TEXT, implied_prob REAL, outcome TEXT)"
    )
    for _ in range(35):
        real_conn.execute(
            "INSERT INTO research_backtest_lines VALUES ('tournament_matchups','leakbook',0.5,'loss')"
        )

    class Proxy:
        def execute(self, sql, params=()):
            return real_conn.execute(sql, params)

        def close(self):
            return None

    monkeypatch.setattr("src.db.ensure_initialized", lambda: None)
    monkeypatch.setattr(db_mod, "get_conn", lambda: Proxy())
    monkeypatch.setattr(
        "backtester.research_lab.ledger.append_ledger_row", lambda row: row
    )
    monkeypatch.setattr(
        "backtester.backtest_ledger.coverage_summary", lambda: {"total_lines": 35}
    )

    alerts = []
    summary = run_detection(alert_fn=alerts.append)
    assert summary["signals_found"] >= 1
    assert any("Tier 2" in a for a in alerts)
    assert list(tmp_path.glob("hypothesis_*.json"))


def test_slugify():
    assert slugify("book=Bet365 Online") == "book-bet365-online"


# ---------------------------------------------------------------------------
# PR creation is operator-gated (endpoint requires explicit POST; gh mocked)
# ---------------------------------------------------------------------------


def test_create_pr_requires_existing_dossier(tmp_path, monkeypatch):
    monkeypatch.setattr(tier2, "DOSSIER_DIR", tmp_path)
    result = tier2.create_hypothesis_draft_pr("book=nothing")
    assert result["created"] is False


def test_create_pr_happy_path_with_mocked_git(tmp_path, monkeypatch):
    monkeypatch.setattr(tier2, "DOSSIER_DIR", tmp_path)
    signal = {"segment": "book=x", "n": 30, "roi_pct": -6.0, "hypothesis": "h", "proposed_tier2_action": "a"}
    write_hypothesis_dossier(signal)

    calls: list[list[str]] = []
    import subprocess

    class FakeCompleted:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(cmd, capture_output=True, text=True, timeout=None, cwd=None):
        calls.append(list(cmd))
        if cmd[0] == "gh":
            return FakeCompleted(0, stdout="https://github.com/0xAidan/golf-model/pull/999\n")
        return FakeCompleted(0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_path)

    result = tier2.create_hypothesis_draft_pr("book=x")
    assert result["created"] is True
    assert result["pr_url"].endswith("/pull/999")
    gh_call = next(c for c in calls if c[0] == "gh")
    assert "--draft" in gh_call  # draft PR — inert until merged
