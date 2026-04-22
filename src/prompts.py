"""
Expert-Level AI Prompt Frameworks

8 specialized prompts that transform the AI brain from a generic assistant
into a domain-expert golf analytics partner. Each prompt includes:
  - Expert persona with specific domain knowledge
  - Structured input format
  - Required JSON output schema
  - Domain-specific reasoning instructions

Used by GolfModelService, research_agent, outlier_investigator, and intel harvester.

Prompt templates live in prompts/<version>/<name>.md at the repo root so they can be
reviewed and A/B tested without touching code. This module keeps the public function
signatures unchanged: each prompt builder precomputes any complex interpolations into
simple named variables and then runs .format(**kwargs) on the loaded template.
"""

import json
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════
#  Template loader (versioned, cached)
# ═══════════════════════════════════════════════════════════════════

_PROMPTS_ROOT = Path(__file__).resolve().parent.parent / "prompts"
_CACHE: dict[tuple[str, str], str] = {}


def load_prompt(name: str, version: str = "v1") -> str:
    """
    Load a prompt template from prompts/<version>/<name>.md.

    Contents are returned verbatim except that a single trailing newline is
    stripped so that .format(...) output matches the original f-string output
    byte-for-byte. Templates use {placeholder} tokens compatible with
    str.format(); literal braces must be written as {{ and }}.

    Raises FileNotFoundError with a clear, actionable message when the
    requested template does not exist.
    """
    key = (version, name)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    path = _PROMPTS_ROOT / version / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(
            f"Prompt template not found: {path}. "
            f"Expected file prompts/{version}/{name}.md — "
            f"check the name/version and that the file exists."
        )

    text = path.read_text(encoding="utf-8")
    if text.endswith("\n"):
        text = text[:-1]

    _CACHE[key] = text
    return text


# ═══════════════════════════════════════════════════════════════════
#  1. PRE-TOURNAMENT ANALYSIS
# ═══════════════════════════════════════════════════════════════════

def pre_tournament_analysis(event_name: str, course_name: str,
                            field_data: list[dict],
                            weather_forecast: dict = None,
                            course_profile: dict = None,
                            intel_items: list[dict] = None) -> str:
    """
    Expert pre-tournament analysis prompt.
    Produces course-fit ratings, sleeper picks, and fade candidates.
    """
    field_summary = json.dumps(field_data[:40], indent=2, default=str) if field_data else "[]"
    weather_str = json.dumps(weather_forecast, indent=2) if weather_forecast else "Not available"
    course_str = json.dumps(course_profile, indent=2) if course_profile else "Not available"
    intel_str = json.dumps(intel_items[:10], indent=2) if intel_items else "[]"

    return load_prompt("pre_tournament_analysis").format(
        event_name=event_name,
        course_name=course_name,
        course_str=course_str,
        weather_str=weather_str,
        field_summary=field_summary,
        intel_str=intel_str,
    )


# ═══════════════════════════════════════════════════════════════════
#  2. BETTING DECISION
# ═══════════════════════════════════════════════════════════════════

def betting_decision(value_bets: list[dict],
                     bankroll: float = 1000.0,
                     weather_context: str = "",
                     intel_context: str = "") -> str:
    """
    DISABLED: AI betting decisions removed due to poor performance.
    The AI concentrated 87% of units on one player and recommended bets on
    corrupted +500000 odds data. Betting decisions are now purely quantitative.
    Returns None to signal the caller to skip AI betting.
    """
    return None


# ═══════════════════════════════════════════════════════════════════
#  3. POST-TOURNAMENT REVIEW
# ═══════════════════════════════════════════════════════════════════

def post_tournament_review(event_name: str,
                           predictions: list[dict],
                           actual_results: list[dict],
                           bets_placed: list[dict],
                           weather_actual: dict = None) -> str:
    """
    Expert post-tournament review prompt.
    Identifies what the model got right/wrong and why.
    """
    predictions_str = json.dumps(predictions[:20], indent=2, default=str)
    actual_results_str = json.dumps(actual_results[:20], indent=2, default=str)
    bets_placed_str = json.dumps(bets_placed, indent=2, default=str)
    weather_actual_str = (
        json.dumps(weather_actual, indent=2, default=str) if weather_actual else "Not available"
    )

    return load_prompt("post_tournament_review").format(
        event_name=event_name,
        predictions_str=predictions_str,
        actual_results_str=actual_results_str,
        bets_placed_str=bets_placed_str,
        weather_actual_str=weather_actual_str,
    )


# ═══════════════════════════════════════════════════════════════════
#  4. HYPOTHESIS GENERATION
# ═══════════════════════════════════════════════════════════════════

def hypothesis_generation(current_performance: dict,
                          outlier_patterns: list[dict],
                          experiment_history: list[dict]) -> str:
    """
    Expert hypothesis generation prompt for the research agent.
    """
    current_performance_str = json.dumps(current_performance, indent=2, default=str)
    outlier_patterns_str = json.dumps(outlier_patterns, indent=2, default=str)
    experiment_history_str = json.dumps(experiment_history[:10], indent=2, default=str)

    return load_prompt("hypothesis_generation").format(
        current_performance_str=current_performance_str,
        outlier_patterns_str=outlier_patterns_str,
        experiment_history_str=experiment_history_str,
    )


# ═══════════════════════════════════════════════════════════════════
#  5. OUTLIER INVESTIGATION
# ═══════════════════════════════════════════════════════════════════

def outlier_investigation(player_name: str,
                          event_name: str,
                          predicted_rank: int,
                          actual_finish: str,
                          sg_splits: dict = None,
                          weather: list[dict] = None,
                          equipment: list[dict] = None,
                          intel: list[dict] = None) -> str:
    """
    Expert outlier investigation prompt.
    Deep-dives into a specific prediction miss.
    """
    sg_splits_str = json.dumps(sg_splits, indent=2, default=str) if sg_splits else "Not available"
    weather_str = json.dumps(weather, indent=2, default=str) if weather else "Not available"
    equipment_str = json.dumps(equipment, indent=2, default=str) if equipment else "None known"
    intel_str = json.dumps(intel, indent=2, default=str) if intel else "None"

    return load_prompt("outlier_investigation").format(
        player_name=player_name,
        event_name=event_name,
        predicted_rank=predicted_rank,
        actual_finish=actual_finish,
        sg_splits_str=sg_splits_str,
        weather_str=weather_str,
        equipment_str=equipment_str,
        intel_str=intel_str,
    )


# ═══════════════════════════════════════════════════════════════════
#  6. WEATHER IMPACT ASSESSMENT
# ═══════════════════════════════════════════════════════════════════

def weather_impact_assessment(event_name: str, course_name: str,
                              weather_data: dict,
                              field: list[dict]) -> str:
    """
    Expert weather impact prompt.
    Assesses which players benefit/suffer from forecasted conditions.
    """
    weather_data_str = json.dumps(weather_data, indent=2, default=str)
    field_str = json.dumps(field[:30], indent=2, default=str)

    return load_prompt("weather_impact_assessment").format(
        event_name=event_name,
        course_name=course_name,
        weather_data_str=weather_data_str,
        field_str=field_str,
    )


# ═══════════════════════════════════════════════════════════════════
#  7. INTEL ANALYSIS
# ═══════════════════════════════════════════════════════════════════

def intel_analysis(raw_intel: list[dict],
                   player_context: dict = None) -> str:
    """
    Expert intel analysis prompt.
    Filters noise from signal in news/social data.
    """
    raw_intel_str = json.dumps(raw_intel, indent=2, default=str)
    player_context_str = (
        json.dumps(player_context, indent=2, default=str) if player_context else "Not available"
    )

    return load_prompt("intel_analysis").format(
        raw_intel_str=raw_intel_str,
        player_context_str=player_context_str,
    )


# ═══════════════════════════════════════════════════════════════════
#  8. COURSE PROFILING
# ═══════════════════════════════════════════════════════════════════

def course_profiling(course_name: str,
                     historical_winners: list[dict] = None,
                     sg_importance_data: dict = None,
                     course_stats: dict = None) -> str:
    """
    Expert course profiling prompt.
    Creates a comprehensive course DNA profile.
    """
    historical_winners_str = (
        json.dumps(historical_winners, indent=2, default=str) if historical_winners else "Not available"
    )
    sg_importance_str = (
        json.dumps(sg_importance_data, indent=2, default=str) if sg_importance_data else "Not available"
    )
    course_stats_str = (
        json.dumps(course_stats, indent=2, default=str) if course_stats else "Not available"
    )

    return load_prompt("course_profiling").format(
        course_name=course_name,
        historical_winners_str=historical_winners_str,
        sg_importance_str=sg_importance_str,
        course_stats_str=course_stats_str,
    )


# ═══════════════════════════════════════════════════════════════════
#  Utility: Format prompt for specific AI provider
# ═══════════════════════════════════════════════════════════════════

def wrap_for_provider(prompt: str, provider: str = "openai",
                      system_message: str = None) -> dict:
    """
    Wrap a prompt into the format expected by different AI providers.
    Returns a dict ready to pass to the API call.
    """
    if system_message is None:
        system_message = load_prompt("system_default")

    if provider == "openai":
        return {
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ]
        }
    elif provider == "anthropic":
        return {
            "system": system_message,
            "messages": [
                {"role": "user", "content": prompt},
            ]
        }
    else:
        return {
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ]
        }
