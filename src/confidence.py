"""
Model Confidence Calculator

Replaces subjective AI confidence with a calculated metric based on
concrete, measurable factors.

Confidence factors:
- Course profile availability (manual or auto-generated)
- DG probability data coverage
- Course history depth (years of data)
- Field strength
- Odds data quality
- Model/market alignment (low suspicious bet %)
"""

from src import config


def calculate_model_confidence(
    has_course_profile: bool,
    dg_data_coverage: float,
    course_history_years: int,
    field_strength: str,
    odds_quality_score: float,
    suspicious_bet_pct: float,
) -> dict:
    """
    Calculate model confidence based on concrete factors.

    Args:
        has_course_profile: Whether a course profile exists (manual or auto)
        dg_data_coverage: Fraction of field with DG probability data (0-1)
        course_history_years: Years of historical data at this course
        field_strength: "weak", "average", "strong" (affects variance)
        odds_quality_score: Quality score from compute_run_quality (0-1)
        suspicious_bet_pct: Fraction of bets flagged as suspicious (0-1)

    Returns:
        dict with confidence (0-1), factors breakdown, and explanation
    """
    factors = {}

    # Factor 1: Course profile (from config weights)
    if has_course_profile:
        factors["course_profile"] = config.CONFIDENCE_COURSE_PROFILE_AUTO
    else:
        factors["course_profile"] = config.CONFIDENCE_COURSE_PROFILE_NONE

    # Factor 2: DG data coverage
    factors["dg_coverage"] = min(1.0, dg_data_coverage)

    # Factor 3: Course history depth (thresholds from config)
    factors["course_history"] = config.CONFIDENCE_COURSE_HISTORY_DEFAULT
    for min_years in sorted(config.CONFIDENCE_COURSE_HISTORY_YEARS.keys(), reverse=True):
        if course_history_years >= min_years:
            factors["course_history"] = config.CONFIDENCE_COURSE_HISTORY_YEARS[min_years]
            break

    # Factor 4: Field strength (from config)
    factors["field_strength"] = config.CONFIDENCE_FIELD_STRENGTH.get(field_strength, 0.85)

    # Factor 5: Odds quality
    factors["odds_quality"] = max(0.3, odds_quality_score)

    # Factor 6: Model/market alignment
    factors["model_market_alignment"] = max(0.3, 1.0 - suspicious_bet_pct * 5)

    # Weighted average (weights from config)
    weights = config.CONFIDENCE_FACTOR_WEIGHTS
    confidence = sum(factors[k] * weights[k] for k in factors)
    confidence = round(max(0.0, min(1.0, confidence)), 2)

    # Build explanation (thresholds from config)
    weak_factors = [k for k, v in factors.items() if v < config.CONFIDENCE_WEAK_THRESHOLD]
    strong_factors = [k for k, v in factors.items() if v >= config.CONFIDENCE_STRONG_THRESHOLD]

    explanation = []
    if weak_factors:
        explanation.append(f"Weak: {', '.join(weak_factors)}")
    if strong_factors:
        explanation.append(f"Strong: {', '.join(strong_factors)}")

    return {
        "confidence": confidence,
        "factors": {k: round(v, 2) for k, v in factors.items()},
        "explanation": "; ".join(explanation) if explanation else "Balanced factors",
    }


def get_field_strength(composite_results: list[dict]) -> str:
    """
    Determine field strength based on top player composite scores.
    Thresholds from config.
    """
    if not composite_results:
        return "average"

    top_scores = [r["composite"] for r in composite_results[:20]]
    above_70 = sum(1 for s in top_scores if s > 70)
    above_65 = sum(1 for s in top_scores if s > 65)

    if above_70 >= config.CONFIDENCE_FIELD_STRONG_ABOVE_70:
        return "strong"
    elif above_65 >= config.CONFIDENCE_FIELD_AVERAGE_ABOVE_65:
        return "average"
    else:
        return "weak"
