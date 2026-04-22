"""Tests for T3 Phase 0 + Phase 1 — pair / team matchup model.

Tracks issue #47. The critical guarantees tested here are:

* ``predict_pair`` behaves directionally — a stronger pair wins more often,
  and the function correctly handles missing features.
* With ``PAIR_MATCHUP_V1=False`` (default), the team-event guard path
  produces a result payload and on-disk card that are byte-identical to
  main. This is the ship guarantee for Zurich week 2026.
* With ``PAIR_MATCHUP_V1=True``, shadow writes happen but the card hash is
  still byte-identical. The flag must never change user-facing output.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path

import pytest

from src import config
from src.models import pair_matchup_v1 as pmv1


# ---------------------------------------------------------------------------
# Unit tests for predict_pair
# ---------------------------------------------------------------------------


def _features(**kwargs: dict) -> dict:
    return {k: v for k, v in kwargs.items()}


def test_predict_pair_invalid_format_raises():
    with pytest.raises(ValueError):
        pmv1.predict_pair(("a", "b"), ("c", "d"), format="scramble", features={})


def test_predict_pair_rejects_wrong_team_size():
    with pytest.raises(ValueError):
        pmv1.predict_pair(("a",), ("c", "d"), format="foursomes", features={})  # type: ignore[arg-type]


def test_predict_pair_returns_half_with_no_signal():
    p = pmv1.predict_pair(("a", "b"), ("c", "d"), format="foursomes", features={})
    assert p == pytest.approx(0.5)


@pytest.mark.parametrize("fmt", ["foursomes", "fourball", "FOURSOMES", "Fourball"])
def test_predict_pair_accepts_both_formats_case_insensitive(fmt):
    feats = _features(
        a={"skill": 1.0}, b={"skill": 1.0}, c={"skill": 1.0}, d={"skill": 1.0}
    )
    p = pmv1.predict_pair(("a", "b"), ("c", "d"), format=fmt, features=feats)
    assert 0.0 <= p <= 1.0
    # Evenly matched teams → 0.5.
    assert p == pytest.approx(0.5, abs=1e-9)


def test_foursomes_stronger_team_wins_more_often():
    """Two good players vs two average players — stronger team should win > 50%."""
    feats = _features(
        a={"skill": 2.0},  # Scheffler-tier
        b={"skill": 2.0},
        c={"skill": 0.0},  # tour average
        d={"skill": 0.0},
    )
    p = pmv1.predict_pair(("a", "b"), ("c", "d"), format="foursomes", features=feats)
    assert p > 0.6


def test_foursomes_punishes_weak_link_more_than_fourball():
    """Same duo of (elite, weak) vs two average players: foursomes should be
    closer to 50% than fourball, because alt-shot is sensitive to the weak
    player while best-ball hides them."""
    feats = _features(
        a={"skill": 3.0},  # elite
        b={"skill": -1.0},  # well below tour average
        c={"skill": 0.5},  # average+
        d={"skill": 0.5},
    )
    p_fs = pmv1.predict_pair(("a", "b"), ("c", "d"), format="foursomes", features=feats)
    p_fb = pmv1.predict_pair(("a", "b"), ("c", "d"), format="fourball", features=feats)
    # Fourball should favour the team with the elite player more strongly
    # because the weak teammate's bad holes are masked by the partner.
    assert p_fb > p_fs


def test_predict_pair_symmetric_swap():
    """Swapping A and B should give 1 - p (within float tolerance)."""
    feats = _features(
        a={"skill": 1.5},
        b={"skill": 0.2},
        c={"skill": 0.8},
        d={"skill": 0.9},
    )
    p_ab = pmv1.predict_pair(("a", "b"), ("c", "d"), format="fourball", features=feats)
    p_ba = pmv1.predict_pair(("c", "d"), ("a", "b"), format="fourball", features=feats)
    assert p_ab + p_ba == pytest.approx(1.0, abs=1e-9)


def test_composite_fallback_when_skill_missing():
    """If only composites are present, the fallback path should still return
    a reasonable probability — not the no-signal 0.5."""
    feats = _features(
        a={"composite": 2.5},
        b={"composite": 2.5},
        c={"composite": 0.0},
        d={"composite": 0.0},
    )
    p = pmv1.predict_pair(("a", "b"), ("c", "d"), format="foursomes", features=feats)
    assert p > 0.5


def test_one_team_missing_signal_is_tied():
    """If team_b has no features at all and team_a has composite-only, we still
    cannot meaningfully compare — must return 0.5 rather than invent an edge.
    (team_b falls back to composite fallback which is also None.)"""
    feats = _features(a={"composite": 2.0}, b={"composite": 2.0})
    p = pmv1.predict_pair(("a", "b"), ("c", "d"), format="fourball", features=feats)
    assert p == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Shadow-table logging
# ---------------------------------------------------------------------------


def _in_memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_log_pair_prediction_is_noop_when_flag_off(monkeypatch):
    monkeypatch.setattr(config, "PAIR_MATCHUP_V1", False)
    conn = _in_memory_conn()
    new_id = pmv1.log_pair_prediction(
        conn,
        event_id="026",
        team_a=("a", "b"),
        team_b=("c", "d"),
        format="foursomes",
        predicted_p_a=0.6,
    )
    assert new_id == -1
    # Table should not be created and no rows written.
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "pair_matchup_predictions" not in tables


def test_log_pair_prediction_writes_when_flag_on(monkeypatch):
    monkeypatch.setattr(config, "PAIR_MATCHUP_V1", True)
    conn = _in_memory_conn()
    new_id = pmv1.log_pair_prediction(
        conn,
        event_id="026",
        team_a=("scottie", "sam"),
        team_b=("rory", "shane"),
        format="fourball",
        predicted_p_a=0.6234,
    )
    assert new_id > 0
    rows = pmv1.fetch_shadow_predictions(conn)
    assert len(rows) == 1
    r = rows[0]
    assert r["team_a_p1"] == "scottie"
    assert r["team_a_p2"] == "sam"
    assert r["team_b_p1"] == "rory"
    assert r["team_b_p2"] == "shane"
    assert r["format"] == "fourball"
    assert r["predicted_p_a"] == pytest.approx(0.6234)


def test_fetch_shadow_predictions_filters_by_event(monkeypatch):
    monkeypatch.setattr(config, "PAIR_MATCHUP_V1", True)
    conn = _in_memory_conn()
    pmv1.log_pair_prediction(
        conn,
        event_id="A",
        team_a=("a", "b"),
        team_b=("c", "d"),
        format="foursomes",
        predicted_p_a=0.5,
    )
    pmv1.log_pair_prediction(
        conn,
        event_id="B",
        team_a=("a", "b"),
        team_b=("c", "d"),
        format="foursomes",
        predicted_p_a=0.5,
    )
    assert len(pmv1.fetch_shadow_predictions(conn, event_id="A")) == 1
    assert len(pmv1.fetch_shadow_predictions(conn, event_id="B")) == 1
    assert len(pmv1.fetch_shadow_predictions(conn)) == 2


# ---------------------------------------------------------------------------
# Golden test: team-event card is byte-identical regardless of the flag.
# ---------------------------------------------------------------------------


_TIMESTAMP_LINE_RE = re.compile(r"^\*\*Generated:\*\*.*$", re.MULTILINE)


def _stable_card_hash(card_path: Path) -> str:
    """Hash the card with the auto-generated timestamp stripped.

    Only the ``**Generated:** ...`` line is non-deterministic across runs;
    the rest of the card is fully deterministic. Stripping that one line
    gives us a stable hash that catches any other content change.
    """
    text = card_path.read_text(encoding="utf-8")
    text = _TIMESTAMP_LINE_RE.sub("**Generated:** <stripped>", text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _run_zurich_guard(monkeypatch, tmp_path: Path, flag_value: bool) -> tuple[str, dict]:
    """Run the team-event branch for Zurich and return (card_hash, sanitised_result).

    Uses the real team-event guard path in ``GolfModelService.run_analysis``;
    all downstream I/O (tournament, output dir) is redirected to the temp
    workspace provided by the ``tmp_db`` fixture + tmp_path.
    """
    monkeypatch.setattr(config, "PAIR_MATCHUP_V1", flag_value)

    from src.services.golf_model_service import GolfModelService

    service = GolfModelService(tour="pga")

    out_dir = tmp_path / f"flag_{int(flag_value)}"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = service.run_analysis(
        tournament_name="Zurich Classic of New Orleans",
        course_name="TPC Louisiana",
        event_id="026",
        enable_ai=False,
        enable_backfill=False,
        include_methodology=False,
        output_dir=str(out_dir),
    )

    assert result["skipped_reason"] == "team_event"
    card_path = Path(result["card_filepath"])
    card_hash = _stable_card_hash(card_path)

    # Strip volatile fields from the result dict for a stable compare.
    sanitised = {
        k: v
        for k, v in result.items()
        if k not in {"run_duration_seconds", "card_filepath", "tournament_id"}
    }
    return card_hash, sanitised


def test_zurich_card_byte_identical_flag_off(tmp_db, tmp_path, monkeypatch):
    """Ship guarantee: with flag OFF the team-event card hash is the same as
    a second run with flag OFF. A baseline self-identity check."""
    h1, r1 = _run_zurich_guard(monkeypatch, tmp_path / "a", False)
    h2, r2 = _run_zurich_guard(monkeypatch, tmp_path / "b", False)
    assert h1 == h2
    assert r1 == r2


def test_zurich_card_byte_identical_when_flag_toggled(tmp_db, tmp_path, monkeypatch):
    """Core T3 P1 guarantee (issue #47): enabling PAIR_MATCHUP_V1 must NOT
    change the team-event card or the sanitised result dict. Shadow writes
    are allowed; user-visible output is not."""
    h_off, r_off = _run_zurich_guard(monkeypatch, tmp_path / "off", False)
    h_on, r_on = _run_zurich_guard(monkeypatch, tmp_path / "on", True)
    assert h_off == h_on, "card hash diverged between flag OFF and flag ON"
    assert r_off == r_on, "result dict diverged between flag OFF and flag ON"


def test_flag_on_creates_shadow_table(tmp_db, tmp_path, monkeypatch):
    """When the flag is on and a team event is seen, the shadow table is
    ensured to exist. No rows required yet (predictions wiring is Phase 2)."""
    _run_zurich_guard(monkeypatch, tmp_path, True)
    conn = tmp_db.get_conn()
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()
    assert "pair_matchup_predictions" in tables


def test_flag_off_does_not_create_shadow_table(tmp_db, tmp_path, monkeypatch):
    """When the flag is off, the pipeline must not touch the shadow table."""
    _run_zurich_guard(monkeypatch, tmp_path, False)
    conn = tmp_db.get_conn()
    try:
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()
    assert "pair_matchup_predictions" not in tables
