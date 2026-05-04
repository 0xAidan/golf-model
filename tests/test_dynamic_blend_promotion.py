"""Tests for dynamic blend OOS promotion gate."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _insert_history(conn, rows):
    for tid, bd, bm, bb, n, dg_w, mw in rows:
        conn.execute(
            """INSERT INTO blend_history
               (tournament_id, bet_type, brier_dg, brier_model, brier_blended,
                n_predictions, dg_weight, model_weight)
               VALUES (?, 'outright', ?, ?, ?, ?, ?, ?)""",
            (tid, bd, bm, bb, n, dg_w, mw),
        )
    conn.commit()


def test_oos_promotion_allows_when_model_beats_dg(tmp_db, monkeypatch):
    monkeypatch.setattr(
        "src.dynamic_blend.is_enabled",
        lambda name: name in ("dynamic_blend", "dynamic_blend_oos_promotion"),
    )
    monkeypatch.setattr("src.dynamic_blend.MIN_TOURNAMENTS_FOR_EWA", 2)
    conn = tmp_db.get_conn()
    rows = []
    for i in range(8):
        tid = 100 + i
        rows.append((tid, 0.25, 0.20, 0.22, 10, 0.92, 0.08))
    _insert_history(conn, rows)
    conn.close()

    from src.dynamic_blend import _oos_promotion_allows_model_weight_increase

    assert _oos_promotion_allows_model_weight_increase("outright") is True


def test_oos_promotion_rejects_when_model_not_better(tmp_db, monkeypatch):
    monkeypatch.setattr(
        "src.dynamic_blend.is_enabled",
        lambda name: name in ("dynamic_blend", "dynamic_blend_oos_promotion"),
    )
    conn = tmp_db.get_conn()
    rows = []
    for i in range(8):
        tid = 200 + i
        rows.append((tid, 0.22, 0.24, 0.23, 10, 0.92, 0.08))
    _insert_history(conn, rows)
    conn.close()

    from src.dynamic_blend import _oos_promotion_allows_model_weight_increase

    assert _oos_promotion_allows_model_weight_increase("outright") is False


def test_get_blend_ratio_clamps_model_increase_when_promotion_fails(tmp_db, monkeypatch):
    monkeypatch.setattr(
        "src.dynamic_blend.is_enabled",
        lambda name: name in ("dynamic_blend", "dynamic_blend_oos_promotion"),
    )
    monkeypatch.setattr("src.dynamic_blend.MIN_TOURNAMENTS_FOR_EWA", 2)
    conn = tmp_db.get_conn()
    for i in range(8):
        tid = 300 + i
        conn.execute(
            """INSERT INTO blend_history
               (tournament_id, bet_type, brier_dg, brier_model, brier_blended,
                n_predictions, dg_weight, model_weight)
               VALUES (?, 'top10', ?, ?, ?, ?, ?, ?)""",
            (tid, 0.22, 0.24, -0.5, 10, 0.90, 0.10),
        )
    conn.commit()
    conn.close()

    from src.dynamic_blend import get_blend_ratio

    dg, mw = get_blend_ratio("top10")
    assert mw == pytest.approx(0.10, abs=1e-6)


def test_get_blend_ratio_allows_increase_when_promotion_passes(tmp_db, monkeypatch):
    monkeypatch.setattr(
        "src.dynamic_blend.is_enabled",
        lambda name: name in ("dynamic_blend", "dynamic_blend_oos_promotion"),
    )
    monkeypatch.setattr("src.dynamic_blend.MIN_TOURNAMENTS_FOR_EWA", 2)
    conn = tmp_db.get_conn()
    for i in range(8):
        tid = 400 + i
        conn.execute(
            """INSERT INTO blend_history
               (tournament_id, bet_type, brier_dg, brier_model, brier_blended,
                n_predictions, dg_weight, model_weight)
               VALUES (?, 'top10', ?, ?, ?, ?, ?, ?)""",
            (tid, 0.26, 0.18, -0.5, 10, 0.90, 0.10),
        )
    conn.commit()
    conn.close()

    from src.dynamic_blend import get_blend_ratio

    dg, mw = get_blend_ratio("top10")
    assert mw > 0.10
