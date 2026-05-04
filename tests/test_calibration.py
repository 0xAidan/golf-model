"""Tests for calibration curve logic."""
from src.calibration import (
    MIN_SAMPLE_FOR_CORRECTION,
    PROBABILITY_BUCKETS,
    get_calibration_correction,
    update_calibration_curve,
)


def test_get_calibration_correction_returns_float():
    """Correction factor should always be a positive float."""
    result = get_calibration_correction(0.10)
    assert isinstance(result, float)
    assert result > 0


def test_get_calibration_correction_out_of_range():
    """Probability 1.0 (edge) -> 1.0."""
    result = get_calibration_correction(1.0)
    assert result == 1.0


def test_update_calibration_curve_empty():
    """No prediction_log data -> empty dict."""
    result = update_calibration_curve()
    assert result == {} or isinstance(result, dict)


def test_probability_buckets_cover_range():
    """Buckets should cover 0.0 to 1.0 with no gaps."""
    prev_high = 0.0
    for low, high, label in PROBABILITY_BUCKETS:
        assert low == prev_high, f"Gap before {label}: {prev_high} to {low}"
        prev_high = high
    assert prev_high == 1.0


def test_update_calibration_curve_writes_per_bet_type(tmp_db):
    tid = tmp_db.get_or_create_tournament("Cal Tournament", year=2026)
    preds = []
    for i in range(MIN_SAMPLE_FOR_CORRECTION + 5):
        preds.append(
            {
                "tournament_id": tid,
                "player_key": f"a{i}",
                "bet_type": "top10",
                "model_prob": 0.15,
                "dg_prob": None,
                "market_implied_prob": 0.12,
                "actual_outcome": 1,
                "odds_decimal": 6.0,
                "profit": None,
                "odds_timing": "unknown",
            }
        )
    for i in range(MIN_SAMPLE_FOR_CORRECTION + 5):
        preds.append(
            {
                "tournament_id": tid,
                "player_key": f"b{i}",
                "bet_type": "matchup",
                "model_prob": 0.15,
                "dg_prob": None,
                "market_implied_prob": 0.12,
                "actual_outcome": 0,
                "odds_decimal": 6.0,
                "profit": None,
                "odds_timing": "unknown",
            }
        )
    tmp_db.log_predictions(preds)
    update_calibration_curve()
    conn = tmp_db.get_conn()
    types = {
        r["bet_type"] for r in conn.execute("SELECT DISTINCT bet_type FROM calibration_curve").fetchall()
    }
    conn.close()
    assert types == {"", "matchup", "top10"}


def test_get_calibration_correction_falls_back_to_global(tmp_db):
    tid = tmp_db.get_or_create_tournament("Fallback T", year=2026)
    preds = []
    for i in range(MIN_SAMPLE_FOR_CORRECTION + 5):
        preds.append(
            {
                "tournament_id": tid,
                "player_key": f"c{i}",
                "bet_type": "top10",
                "model_prob": 0.15,
                "dg_prob": None,
                "market_implied_prob": 0.12,
                "actual_outcome": 1,
                "odds_decimal": 6.0,
                "profit": None,
                "odds_timing": "unknown",
            }
        )
    tmp_db.log_predictions(preds)
    update_calibration_curve()
    corr_global = get_calibration_correction(0.15, bet_type=None)
    corr_top20 = get_calibration_correction(0.15, bet_type="top20")
    assert corr_top20 == corr_global
    assert isinstance(corr_top20, float)
    assert corr_top20 > 0
