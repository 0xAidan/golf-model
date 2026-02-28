"""
Centralized configuration for the golf betting model.

Single source of truth for magic numbers previously scattered across
value.py, adaptation.py, db.py, matchup_value.py, weather.py, confidence.py.
All tuning should happen here or via environment variables where noted.
"""

import os
from typing import Any

# ---------------------------------------------------------------------------
# Model version (single source of truth; was v3.0 in card.py, v4.0 in methodology)
# ---------------------------------------------------------------------------
MODEL_VERSION = "4.0"

# ---------------------------------------------------------------------------
# Value / EV / blend (from value.py)
# ---------------------------------------------------------------------------
# Default EV threshold; override via env EV_THRESHOLD (e.g. "0.05" for 5%)
DEFAULT_EV_THRESHOLD = float(os.environ.get("EV_THRESHOLD", "0.02"))

MARKET_EV_THRESHOLDS: dict[str, float] = {
    "outright": 0.05,
    "top5": 0.05,
    "top10": 0.02,
    "top20": 0.02,
    "frl": 0.05,
    "make_cut": 0.02,
    "3ball": 0.05,
}

# Maximum credible EV; above this indicates bad data, not real edge
MAX_CREDIBLE_EV = 2.0

# Minimum market implied probability to trust odds
MIN_MARKET_PROB = 0.005

# Dead heat: conservative reduction to placement win prob (~20-30% of top10 bets affected)
DEAD_HEAT_DISCOUNT_TOP5 = 0.05
DEAD_HEAT_DISCOUNT_TOP10 = 0.10
DEAD_HEAT_DISCOUNT_TOP20 = 0.08

# Market-specific max American odds (corrupt data filter)
MAX_REASONABLE_ODDS: dict[str, int] = {
    "outright": 30000,
    "top5": 5000,
    "top10": 3000,
    "top20": 1500,
    "frl": 10000,
    "make_cut": 500,
    "3ball": 5000,
}

# Blend weights: DG vs model. Plan: start 70/30 (configurable); dynamic blend later.
BLEND_WEIGHTS: dict[str, dict[str, float]] = {
    "outright": {"dg": 0.70, "model": 0.30},
    "top5": {"dg": 0.70, "model": 0.30},
    "top10": {"dg": 0.70, "model": 0.30},
    "top20": {"dg": 0.70, "model": 0.30},
    "frl": {"dg": 0.70, "model": 0.30},
    "make_cut": {"dg": 0.70, "model": 0.30},
    "3ball": {"dg": 0.70, "model": 0.30},
}

# Softmax temperature by bet type (value.py model_score_to_prob)
SOFTMAX_TEMP_BY_TYPE: dict[str, float] = {
    "outright": 8.0,
    "top5": 10.0,
    "top10": 12.0,
    "top20": 15.0,
    "make_cut": 20.0,
    "frl": 7.0,
    "3ball": 10.0,
}

# ---------------------------------------------------------------------------
# Adaptation (from adaptation.py) — thresholds for state machine
# ---------------------------------------------------------------------------
ADAPTATION_MIN_BETS = 10
ADAPTATION_CONSECUTIVE_LOSSES_FROZEN = 10
ADAPTATION_EV_THRESHOLD_NORMAL = 0.05
ADAPTATION_EV_THRESHOLD_CAUTION = 0.08
ADAPTATION_EV_THRESHOLD_COLD = 0.12
ADAPTATION_ROI_CAUTION = -20.0   # roi_pct > -20 -> caution
ADAPTATION_ROI_COLD = -40.0      # roi_pct > -40 -> cold
ADAPTATION_STAKE_MULTIPLIER_COLD = 0.5

# ---------------------------------------------------------------------------
# Matchup sigmoid: Platt-style P(win) = 1/(1+exp(A*gap+B)). Refit after each tournament.
# ---------------------------------------------------------------------------
MATCHUP_PLATT_A = -1.0 / 20.0   # -0.05; more conservative until Platt fitted
MATCHUP_PLATT_B = 0.0
MATCHUP_SIGMOID_DIVISOR = 20.0   # legacy; use PLATT_A/B
MATCHUP_CAP = 15                 # max matchups to output
MATCHUP_TIER_STRONG_EV_PCT = 15.0   # EV >= 15% -> STRONG
MATCHUP_TIER_GOOD_EV_PCT = 8.0      # EV >= 8% -> GOOD; else LEAN

# ---------------------------------------------------------------------------
# Default weights (from db.py)
# ---------------------------------------------------------------------------
# SG sub-weights follow DG predictive hierarchy: OTT=1.2, APP=1.0, ARG=0.9, PUTT=0.6
# Normalized: OTT 0.30, APP 0.28, TOT 0.22, PUTT 0.10 (putt downweighted; Bayesian shrinkage also applied)
DEFAULT_WEIGHTS: dict[str, float] = {
    "course_fit": 0.45,
    "form": 0.45,
    "momentum": 0.10,
    "course_sg_tot": 0.22,
    "course_sg_app": 0.28,
    "course_sg_ott": 0.30,
    "course_sg_putt": 0.10,
    "course_par_eff": 0.10,
    "form_16r": 0.35,
    "form_12month": 0.25,
    "form_sim": 0.25,
    "form_rolling": 0.15,
    "form_sg_tot": 0.22,
    "form_sg_app": 0.28,
    "form_sg_ott": 0.30,
    "form_sg_putt": 0.10,
    "form_sg_arg": 0.10,
}
# Bayesian shrinkage on putting: shrink raw putt score toward 50 (neutral)
PUTT_SHRINKAGE_FACTOR = 0.5  # adjusted_putt = 50 + 0.5 * (raw - 50)

# Momentum kill switch: set to False if predictive_power < 0.03 after 5+ tournaments
MOMENTUM_ENABLED = True

# AI brain: cap adjustments to +/-3 (tightened from +/-5)
AI_ADJUSTMENT_CAP = 3.0

# ---------------------------------------------------------------------------
# Weather (from models/weather.py)
# ---------------------------------------------------------------------------
WIND_THRESHOLD_KMH = 15.0
COLD_THRESHOLD_C = 10.0
MAX_WAVE_ADJUSTMENT = 3.0
MAX_RESILIENCE_ADJUSTMENT = 5.0
CONDITIONS_RATING_WIND_FACTOR = 3.0   # (avg_wind - 15) * 3
CONDITIONS_RATING_GUST_FACTOR = 2.0   # (max_gust - 40) * 2
CONDITIONS_RATING_PRECIP_FACTOR = 10.0
CONDITIONS_RATING_COLD_FACTOR = 2.0

# ---------------------------------------------------------------------------
# Confidence (from confidence.py) — factor weights and thresholds
# ---------------------------------------------------------------------------
CONFIDENCE_COURSE_PROFILE_AUTO = 0.85
CONFIDENCE_COURSE_PROFILE_NONE = 0.30
CONFIDENCE_COURSE_HISTORY_YEARS: dict[int, float] = {
    5: 1.0,
    3: 0.85,
    1: 0.70,
}
CONFIDENCE_COURSE_HISTORY_DEFAULT = 0.50
CONFIDENCE_FIELD_STRENGTH: dict[str, float] = {
    "strong": 1.0,
    "average": 0.85,
    "weak": 0.70,
}
CONFIDENCE_FACTOR_WEIGHTS: dict[str, float] = {
    "course_profile": 0.20,
    "dg_coverage": 0.25,
    "course_history": 0.15,
    "field_strength": 0.10,
    "odds_quality": 0.15,
    "model_market_alignment": 0.15,
}
CONFIDENCE_WEAK_THRESHOLD = 0.70
CONFIDENCE_STRONG_THRESHOLD = 0.90
CONFIDENCE_FIELD_STRONG_ABOVE_70 = 5
CONFIDENCE_FIELD_AVERAGE_ABOVE_65 = 8

# ---------------------------------------------------------------------------
# Data integrity gates (for run_predictions.py Phase 0D)
# ---------------------------------------------------------------------------
METRIC_FRESHNESS_HOURS = 48
FIELD_SIZE_MIN = 50
FIELD_SIZE_MAX = 170
PROBABILITY_SUM_TOLERANCE = 0.05   # outright probs sum in [0.95, 1.05]


def get_blend_weights(bet_type: str) -> tuple[float, float]:
    """Return (dg_weight, model_weight) for a bet type."""
    cfg = BLEND_WEIGHTS.get(bet_type, {"dg": 0.70, "model": 0.30})
    return (cfg["dg"], cfg["model"])
