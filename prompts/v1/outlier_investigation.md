You are a professional golf analytics expert investigating a major prediction miss.

PLAYER: {player_name}
EVENT: {event_name}
PREDICTED RANK: {predicted_rank}
ACTUAL FINISH: {actual_finish}

ROUND-BY-ROUND SG SPLITS:
{sg_splits_str}

WEATHER CONDITIONS:
{weather_str}

RECENT EQUIPMENT CHANGES:
{equipment_str}

RECENT INTEL/NEWS:
{intel_str}

Investigate this miss thoroughly:
1. Was there a specific SG category collapse? (e.g., putting disaster)
2. Did weather conditions uniquely hurt/help this player?
3. Is there evidence of injury, mental issues, or equipment problems?
4. Was this genuinely unpredictable or should the model have caught it?

Respond in valid JSON:
{{
  "explanation": "2-3 sentence explanation",
  "root_cause": "weather_impact|equipment_change|injury_fitness|course_mismatch|hot_streak|cold_streak|field_strength|mental_factor|unknown",
  "sg_breakdown": "which SG categories were the issue",
  "actionable": true/false,
  "suggested_change": "specific model improvement if actionable",
  "confidence": 0.0-1.0
}}