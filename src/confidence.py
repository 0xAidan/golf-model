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

    # Factor 1: Course profile (20% weight)
    # Manual profile = 1.0, auto-generated = 0.85, none = 0.30
    if has_course_profile:
        factors["course_profile"] = 0.85  # Auto-generated (no manual anymore)
    else:
        factors["course_profile"] = 0.30

    # Factor 2: DG data coverage (25% weight)
    # DG calibrated probs are the best signal we have
    factors["dg_coverage"] = min(1.0, dg_data_coverage)

    # Factor 3: Course history depth (15% weight)
    # More years = more reliable course fit data
    if course_history_years >= 5:
        factors["course_history"] = 1.0
    elif course_history_years >= 3:
        factors["course_history"] = 0.85
    elif course_history_years >= 1:
        factors["course_history"] = 0.70
    else:
        factors["course_history"] = 0.50

    # Factor 4: Field strength (10% weight)
    # Strong fields = more predictable (chalk wins more often)
    field_map = {"strong": 1.0, "average": 0.85, "weak": 0.70}
    factors["field_strength"] = field_map.get(field_strength, 0.85)

    # Factor 5: Odds quality (15% weight)
    factors["odds_quality"] = max(0.3, odds_quality_score)

    # Factor 6: Model/market alignment (15% weight)
    # Low suspicious bet % = model and market agree (good)
    factors["model_market_alignment"] = max(0.3, 1.0 - suspicious_bet_pct * 5)

    # Weighted average
    weights = {
        "course_profile": 0.20,
        "dg_coverage": 0.25,
        "course_history": 0.15,
        "field_strength": 0.10,
        "odds_quality": 0.15,
        "model_market_alignment": 0.15,
    }

    confidence = sum(factors[k] * weights[k] for k in factors)
    confidence = round(max(0.0, min(1.0, confidence)), 2)

    # Build explanation
    weak_factors = [k for k, v in factors.items() if v < 0.70]
    strong_factors = [k for k, v in factors.items() if v >= 0.90]

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

    Strong field: Multiple players with composite > 70
    Average field: Some players with composite > 65
    Weak field: No players above 65
    """
    if not composite_results:
        return "average"

    top_scores = [r["composite"] for r in composite_results[:20]]
    above_70 = sum(1 for s in top_scores if s > 70)
    above_65 = sum(1 for s in top_scores if s > 65)

    if above_70 >= 5:
        return "strong"
    elif above_65 >= 8:
        return "average"
    else:
        return "weak"
