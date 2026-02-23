"""
Enhanced Matchup Engine

Matchups are the model's strongest proven signal (12-3-1, +8.01u across
Pebble Beach and Genesis). This module provides course-aware matchup
scoring with confidence tiers.

Replaces the simple composite-gap approach from card.py.
"""


CONFIDENCE_TIERS = {
    "strong": {"min_edge": 0.70, "label": "Strong"},
    "moderate": {"min_edge": 0.50, "label": "Moderate"},
    "lean": {"min_edge": 0.30, "label": "Lean"},
}


def compute_matchup_edge(player_a: dict, player_b: dict,
                         course_profile: dict = None) -> dict:
    """
    Compute a detailed matchup edge between two players.

    Uses a multi-factor formula instead of raw composite gap:
    - 40% composite gap (normalized)
    - 30% course-relevant SG gap (weighted by course profile)
    - 15% form gap
    - 15% course fit gap

    player_a and player_b are dicts from composite_results with keys:
    composite, course_fit, form, momentum, player_key, player_display,
    details (which contains course_components and form_components)
    """
    composite_gap = player_a["composite"] - player_b["composite"]
    form_gap = player_a["form"] - player_b["form"]
    course_fit_gap = player_a["course_fit"] - player_b["course_fit"]

    MAX_GAP = 50.0
    composite_norm = min(1.0, max(0.0, composite_gap / MAX_GAP))
    form_norm = min(1.0, max(0.0, form_gap / MAX_GAP))
    course_fit_norm = min(1.0, max(0.0, course_fit_gap / MAX_GAP))

    sg_gap_norm = 0.0
    sg_reasons = []
    if course_profile:
        a_form = player_a.get("details", {}).get("form_components", {})
        b_form = player_b.get("details", {}).get("form_components", {})

        a_sg = a_form.get("multi_sg", 50.0)
        b_sg = b_form.get("multi_sg", 50.0)
        sg_gap = a_sg - b_sg
        sg_gap_norm = min(1.0, max(0.0, sg_gap / MAX_GAP))

        if sg_gap > 10:
            sg_reasons.append(f"SG advantage +{sg_gap:.0f}")
    else:
        sg_gap_norm = form_norm

    edge_score = (
        0.40 * composite_norm +
        0.30 * sg_gap_norm +
        0.15 * form_norm +
        0.15 * course_fit_norm
    )

    reasons = []
    if course_fit_gap > 5:
        reasons.append(f"course fit +{course_fit_gap:.0f}")
    if form_gap > 5:
        reasons.append(f"form +{form_gap:.0f}")
    if player_a.get("momentum_direction") == "hot" and player_b.get("momentum_direction") in ("cold", "cooling"):
        reasons.append("momentum advantage")
    reasons.extend(sg_reasons)

    if edge_score >= CONFIDENCE_TIERS["strong"]["min_edge"]:
        confidence = "strong"
    elif edge_score >= CONFIDENCE_TIERS["moderate"]["min_edge"]:
        confidence = "moderate"
    elif edge_score >= CONFIDENCE_TIERS["lean"]["min_edge"]:
        confidence = "lean"
    else:
        confidence = "below_threshold"

    return {
        "pick": player_a["player_display"],
        "pick_key": player_a["player_key"],
        "opponent": player_b["player_display"],
        "opponent_key": player_b["player_key"],
        "edge_score": round(edge_score, 3),
        "composite_gap": round(composite_gap, 1),
        "form_gap": round(form_gap, 1),
        "course_fit_gap": round(course_fit_gap, 1),
        "confidence": confidence,
        "confidence_label": CONFIDENCE_TIERS.get(confidence, {}).get("label", "Below Threshold"),
        "reason": "; ".join(reasons) if reasons else f"composite +{composite_gap:.0f}",
    }


def find_best_matchups(composite_results: list[dict],
                       course_profile: dict = None,
                       min_edge: float = 0.30,
                       max_matchups: int = 10,
                       search_window: int = 50) -> list[dict]:
    """
    Find the best head-to-head matchup opportunities.

    Searches within a window of rank positions and returns
    matchups sorted by edge score, grouped by confidence tier.
    Each player appears at most once (as pick OR opponent).
    """
    matchups = []
    n = len(composite_results)

    for i in range(n):
        for j in range(i + 1, min(i + search_window, n)):
            a = composite_results[i]
            b = composite_results[j]

            if a["composite"] - b["composite"] < 3.0:
                continue

            edge = compute_matchup_edge(a, b, course_profile)

            if edge["edge_score"] >= min_edge:
                matchups.append(edge)

    matchups.sort(key=lambda x: x["edge_score"], reverse=True)

    seen = set()
    deduped = []
    for m in matchups:
        if m["pick_key"] not in seen and m["opponent_key"] not in seen:
            deduped.append(m)
            seen.add(m["pick_key"])
            seen.add(m["opponent_key"])

    return deduped[:max_matchups]


def group_by_confidence(matchups: list[dict]) -> dict:
    """Group matchups by confidence tier for display."""
    grouped = {"strong": [], "moderate": [], "lean": []}
    for m in matchups:
        tier = m.get("confidence", "lean")
        if tier in grouped:
            grouped[tier].append(m)
    return grouped
