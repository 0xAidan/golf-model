You are a golf course architecture and analytics expert. You can analyze
a course's strategic demands and translate them into quantitative model adjustments.

COURSE: {course_name}

HISTORICAL WINNERS (last 5-10 years):
{historical_winners_str}

SG CATEGORY IMPORTANCE (from historical decomposition):
{sg_importance_str}

COURSE STATISTICS:
{course_stats_str}

Create a comprehensive course profile. Consider:
- Par distribution (par 3/4/5 mix) and how it weights SG categories
- Historical winner profiles: what do they have in common?
- Course setup trends (green speeds, rough height, fairway width)
- Weather patterns at this location
- Altitude and its effect on distance
- Course renovation history

Respond in valid JSON:
{{
  "course_type": "links|parkland|desert|mountain|resort",
  "difficulty_rating": 1-10,
  "sg_weights": {{
    "sg_ott": 0.0-0.4 (importance),
    "sg_app": 0.0-0.4,
    "sg_arg": 0.0-0.4,
    "sg_putt": 0.0-0.4
  }},
  "key_attributes": ["attribute 1", "attribute 2"],
  "ideal_player_profile": "description of the ideal player for this course",
  "historical_patterns": "notable patterns from past results",
  "scoring_expectation": "typical winning score relative to par",
  "volatility": "low|medium|high (how much randomness in outcomes)",
  "similar_courses": ["course 1", "course 2"],
  "model_adjustment_notes": "specific notes for our model when running this course"
}}