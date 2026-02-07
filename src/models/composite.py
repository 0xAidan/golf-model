"""
Composite Edge Score

Combines course fit + form + momentum into one score per player.
Weights are tunable and stored in the database.

Output: ranked player list with composite score and all sub-scores.
"""

from src import db
from src.models.course_fit import compute_course_fit
from src.models.form import compute_form
from src.models.momentum import compute_momentum


def compute_composite(tournament_id: int, weights: dict = None,
                      course_name: str = None) -> list[dict]:
    """
    Compute composite edge score for all players in the tournament.

    Returns a sorted list (best first):
    [
        {
            "player_key": str,
            "player_display": str,
            "composite": float,
            "course_fit": float,
            "form": float,
            "momentum": float,
            "momentum_direction": str,
            "course_confidence": float,
            "details": dict,
        },
        ...
    ]
    """
    if weights is None:
        weights = db.get_active_weights()

    # Compute each sub-model
    course_scores = compute_course_fit(tournament_id, weights, course_name=course_name)
    form_scores = compute_form(tournament_id, weights)
    momentum_scores = compute_momentum(tournament_id, weights)

    # Get display names
    display_names = db.get_player_display_names(tournament_id)

    # Collect all players that appear in ANY model
    all_players = set()
    all_players.update(course_scores.keys())
    all_players.update(form_scores.keys())
    all_players.update(momentum_scores.keys())

    if not all_players:
        return []

    # Top-level weights
    w_course = weights.get("course_fit", 0.40)
    w_form = weights.get("form", 0.40)
    w_momentum = weights.get("momentum", 0.20)

    # If no course data was uploaded, redistribute weight to form + momentum
    has_course_data = bool(course_scores)
    if not has_course_data:
        w_form_adj = w_form + w_course * 0.7
        w_momentum_adj = w_momentum + w_course * 0.3
        w_course_adj = 0.0
    else:
        w_course_adj = w_course
        w_form_adj = w_form
        w_momentum_adj = w_momentum

    results = []
    for pk in all_players:
        cs = course_scores.get(pk, {})
        fs = form_scores.get(pk, {})
        ms = momentum_scores.get(pk, {})

        course_score = cs.get("score", 50.0)
        form_score = fs.get("score", 50.0)
        momentum_score = ms.get("score", 50.0)

        composite = (
            w_course_adj * course_score
            + w_form_adj * form_score
            + w_momentum_adj * momentum_score
        )

        results.append({
            "player_key": pk,
            "player_display": display_names.get(pk, pk),
            "composite": round(composite, 2),
            "course_fit": round(course_score, 2),
            "form": round(form_score, 2),
            "momentum": round(momentum_score, 2),
            "momentum_direction": ms.get("direction", "unknown"),
            "momentum_trend": ms.get("trend", 0),
            "course_confidence": cs.get("confidence", 0),
            "course_rounds": cs.get("rounds", 0),
            "details": {
                "course_components": cs.get("components", {}),
                "form_components": fs.get("components", {}),
                "momentum_windows": ms.get("windows", {}),
            },
        })

    # Sort by composite score (best first)
    results.sort(key=lambda x: x["composite"], reverse=True)

    # Add rank
    for i, r in enumerate(results):
        r["rank"] = i + 1

    return results
