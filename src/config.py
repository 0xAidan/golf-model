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
MODEL_VERSION = "4.2"

# ---------------------------------------------------------------------------
# T3 — Pair / team matchup model (Zurich Classic). See issue #47.
# Phase 1 is analytics-only: when this flag is ON and the current event is a
# team format, predictions are logged to pair_matchup_predictions for post-hoc
# inspection. Nothing is added to the card, snapshot, or live API. Phase 3
# (card output / live pricing) is deliberately not shipped this week.
# Override via env PAIR_MATCHUP_V1=1.
# ---------------------------------------------------------------------------
PAIR_MATCHUP_V1: bool = os.environ.get("PAIR_MATCHUP_V1", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# ---------------------------------------------------------------------------
# Value / EV / blend (from value.py)
# ---------------------------------------------------------------------------
# Default EV threshold; override via env EV_THRESHOLD
# v4.0 used 2% for placement — too low, most "value" was noise.
# v4.1: raised across all markets to filter noise from uncalibrated model.
DEFAULT_EV_THRESHOLD = float(os.environ.get("EV_THRESHOLD", "0.08"))

MARKET_EV_THRESHOLDS: dict[str, float] = {
    "outright": 0.15,
    "top5": 0.10,
    "top10": 0.08,
    "top20": 0.08,
    "frl": 0.10,
    "make_cut": 0.05,
    "3ball": 0.08,
}

# Maximum total value bets per card (across all markets)
# v4.0 had no cap — 23 bets on Cognizant Classic. Quality over quantity.
MAX_TOTAL_VALUE_BETS = 5
MAX_TOTAL_VALUE_BETS_WEAK_FIELD = 6

# Maximum credible EV; above this indicates bad data, not real edge
MAX_CREDIBLE_EV = 2.0

# Best Bets: matchup-focused card. Placements only used as fallback.
MAX_CREDIBLE_PLACEMENT_EV = 0.50  # Cap displayed placement EV at 50%
BEST_BETS_MATCHUP_ONLY = True     # Top 3 bets drawn from matchups first
BEST_BETS_COUNT = 5                   # Number of top matchup plays shown in card header
PLACEMENT_CARD_EV_FLOOR = 0.15        # Only show placements on card when EV >= 15%
PLACEMENT_CARD_MAX = 3                # Max placement bets shown on card

# Phantom EV: hard gate for placement bets with impossibly high EV
PHANTOM_EV_THRESHOLD = 1.0        # >100% EV excluded entirely
MODEL_MARKET_DISCREPANCY_THRESHOLD = 2.0  # model_prob > 2x market_prob -> speculative

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

# Blend weights: DG vs model.
# v4.0 used 70/30 — model softmax is uncalibrated, inflated probabilities.
# v4.1: 95/5 per methodology. Model is a minor tiebreaker until calibrated.
BLEND_WEIGHTS: dict[str, dict[str, float]] = {
    "outright": {"dg": 0.95, "model": 0.05},
    "top5": {"dg": 0.95, "model": 0.05},
    "top10": {"dg": 0.95, "model": 0.05},
    "top20": {"dg": 0.95, "model": 0.05},
    "frl": {"dg": 0.95, "model": 0.05},
    "make_cut": {"dg": 0.95, "model": 0.05},
    "3ball": {"dg": 0.95, "model": 0.05},
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
# Live focus: matchups have been plus-ROI; use a lower EV threshold to surface more.
# ---------------------------------------------------------------------------
MATCHUP_PLATT_A = -1.0 / 20.0   # -0.05; more conservative until Platt fitted
MATCHUP_PLATT_B = 0.0
MATCHUP_SIGMOID_DIVISOR = 20.0   # legacy; use PLATT_A/B
MATCHUP_EV_THRESHOLD = float(os.environ.get("MATCHUP_EV_THRESHOLD", "0.05"))  # 5% min EV for matchups (live focus)
MATCHUP_CAP = 20                 # max matchups to output (live: more matchup options)
MATCHUP_MAX_PLAYER_EXPOSURE = 3  # max times one player can appear across all matchup bets (WD protection)
MATCHUP_TOURNAMENT_MAX_PLAYER_EXPOSURE = 2  # Tighter cap for 72-hole matchups (WD protection)
MATCHUP_TIER_STRONG_EV_PCT = 15.0   # EV >= 15% -> STRONG
MATCHUP_TIER_GOOD_EV_PCT = 8.0      # EV >= 8% -> GOOD; else LEAN
MATCHUP_TIER_STRONG_GAP = 8.0
MATCHUP_TIER_GOOD_GAP = 5.0

# DG matchup probability blending (live pipeline)
DG_MATCHUP_BLEND_WEIGHT = 0.80
MODEL_MATCHUP_BLEND_WEIGHT = 0.20
REQUIRE_DG_MODEL_AGREEMENT = True

# AI adjustment validation
AI_ADJUSTMENT_MIN_HIT_RATE = 0.55

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

# Ranking trust hardening: conservative layoff / low-coverage penalties
RANKING_LAYOFF_WARNING_DAYS = 28
RANKING_LAYOFF_PENALTY_DAYS = 31
RANKING_LAYOFF_MAX_DAYS = 49
RANKING_LAYOFF_BASE_PENALTY = 4.0
RANKING_LAYOFF_MAX_PENALTY = 8.0
RANKING_LOW_COVERAGE_ROUNDS = 8
RANKING_LOW_COVERAGE_MAX_PENALTY = 4.0
RANKING_COMPARABLE_RECENT_ROUNDS_MIN = 4
RANKING_RECENT_ROUNDS_LOOKBACK = 24
RANKING_COMPARABLE_TOURS = ("pga", "liv", "euro")
PLAYER_AVAILABILITY_OVERRIDES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data",
    "player_availability_overrides.yaml",
)

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
# Weak-field adjustments: more uncertainty = higher bar for bets
WEAK_FIELD_EV_MULTIPLIER = 1.5       # multiply EV thresholds by 1.5x for weak fields
WEAK_FIELD_SOFTMAX_TEMP_BOOST = 1.2  # increase softmax temps by 20% for weak fields

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

# Pipeline timing: block execution after R1 starts unless --force is used.
# Mid-tournament odds are in-play prices, not pre-tournament — comparing them
# to static DG sim probabilities produces meaningless EV calculations.
ALLOW_MID_TOURNAMENT_RUN = False

# ---------------------------------------------------------------------------
# Autoresearch guardrails (backtester/weighted_walkforward.evaluate_guardrails)
# Set AUTORESEARCH_GUARDRAIL_MODE=loose for exploratory runs; default is strict.
# ---------------------------------------------------------------------------
AUTORESEARCH_GUARDRAIL_MIN_BETS = int(os.environ.get("AUTORESEARCH_GUARDRAIL_MIN_BETS", "30"))
AUTORESEARCH_GUARDRAIL_MAX_CLV_REGRESSION = float(os.environ.get("AUTORESEARCH_GUARDRAIL_MAX_CLV_REGRESSION", "0.02"))
AUTORESEARCH_GUARDRAIL_MAX_CALIBRATION_REGRESSION = float(os.environ.get("AUTORESEARCH_GUARDRAIL_MAX_CALIBRATION_REGRESSION", "0.03"))
AUTORESEARCH_GUARDRAIL_MAX_DRAWDOWN_REGRESSION = float(os.environ.get("AUTORESEARCH_GUARDRAIL_MAX_DRAWDOWN_REGRESSION", "10.0"))
def get_autoresearch_guardrail_params() -> dict[str, Any]:
    """Return effective guardrail params. Mode: env AUTORESEARCH_GUARDRAIL_MODE > UI setting (data/autoresearch_settings.json) > strict."""
    from src.autoresearch_settings import get_guardrail_mode

    env_mode = (os.environ.get("AUTORESEARCH_GUARDRAIL_MODE", "") or "").strip().lower()
    mode = env_mode if env_mode in ("strict", "loose") else get_guardrail_mode()
    if mode == "loose":
        return {
            "min_bets": 15,
            "max_clv_regression": 0.05,
            "max_calibration_regression": 0.06,
            "max_drawdown_regression": 20.0,
        }
    return {
        "min_bets": AUTORESEARCH_GUARDRAIL_MIN_BETS,
        "max_clv_regression": AUTORESEARCH_GUARDRAIL_MAX_CLV_REGRESSION,
        "max_calibration_regression": AUTORESEARCH_GUARDRAIL_MAX_CALIBRATION_REGRESSION,
        "max_drawdown_regression": AUTORESEARCH_GUARDRAIL_MAX_DRAWDOWN_REGRESSION,
    }


# ---------------------------------------------------------------------------
# API / pipeline timing
# ---------------------------------------------------------------------------
API_TIMEOUT = 120
API_RATE_LIMIT_SECONDS = 1.0
API_SLEEP_SECONDS = 2.0
PIPELINE_LOCK_STALE_SECONDS = 7200
PLATT_CACHE_TTL = 300

# Supported sportsbooks for odds comparison
SUPPORTED_BOOKS = [
    "draftkings", "fanduel", "betmgm", "caesars", "bet365",
    "pointsbet", "betrivers", "fanatics",
]


def get_blend_weights(bet_type: str) -> tuple[float, float]:
    """Return (dg_weight, model_weight) for a bet type."""
    cfg = BLEND_WEIGHTS.get(bet_type, {"dg": 0.95, "model": 0.05})
    return (cfg["dg"], cfg["model"])


# ---------------------------------------------------------------------------
# Champion-challenger rails (recovery defect 3.3.1)
# ---------------------------------------------------------------------------
# CHAMPION names the model that actually prices live bets. CHALLENGERS lists
# models evaluated in shadow mode — their predictions are recorded for offline
# comparison but MUST NEVER influence any card, snapshot, or bet-selection
# logic. Default is empty: no challengers in main, so pipeline output is
# byte-identical to the pre-rails baseline.
CHAMPION: str = "v4.2"
CHALLENGERS: list[str] = []
