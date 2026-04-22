You are conducting a rigorous post-tournament review as a professional golf analyst.
Your goal is to identify systematic biases, lucky/unlucky outcomes, and model improvements.

EVENT: {event_name}

TOP 20 MODEL PREDICTIONS (pre-tournament):
{predictions_str}

ACTUAL TOP 20 RESULTS:
{actual_results_str}

BETS PLACED AND OUTCOMES:
{bets_placed_str}

ACTUAL WEATHER CONDITIONS:
{weather_actual_str}

Perform a thorough review:
1. Prediction accuracy: How well did rankings correlate?
2. Biggest misses: Which players were way off and why?
3. Betting outcomes: Skill vs luck decomposition
4. Weather impact: Did conditions favor/hurt certain players unexpectedly?
5. Model improvements: Specific, actionable changes

Respond in valid JSON:
{{
  "accuracy_grade": "A/B/C/D/F",
  "correlation_rank": 0.0-1.0,
  "biggest_misses": [
    {{"player": "Name", "predicted_rank": N, "actual_rank": N, "likely_cause": "explanation"}}
  ],
  "betting_review": {{
    "total_bets": N, "wins": N, "roi_pct": N,
    "skill_vs_luck": "assessment"
  }},
  "model_improvements": [
    {{"area": "weights/data/logic", "change": "specific change", "expected_impact": "description"}}
  ],
  "key_learnings": ["learning 1", "learning 2"]
}}