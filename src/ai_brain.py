"""
AI Brain — The thinking layer on top of the quantitative model.

Uses OpenAI (default) for structured JSON outputs with schema enforcement.
Optional adapters for Anthropic (Claude) and Google Gemini.

Three main functions, each tournament week:
  1. pre_tournament_analysis()  — qualitative analysis + player adjustments
  2. make_betting_decisions()   — portfolio-level betting decisions
  3. post_tournament_review()   — what worked, what to learn, store memories

Plus a persistent memory system that makes the AI smarter each week.

Provider selection via env: AI_BRAIN_PROVIDER=openai|anthropic|gemini
"""

import json
import logging
import os
from collections import defaultdict
from datetime import datetime
from typing import Optional

from src import db
from src.player_normalizer import display_name

logger = logging.getLogger("ai_brain")

# ═══════════════════════════════════════════════════════════════════
#  Provider Abstraction
# ═══════════════════════════════════════════════════════════════════

def _get_provider() -> str:
    return os.environ.get("AI_BRAIN_PROVIDER", "openai").lower()


def _call_ai(system_prompt: str, user_prompt: str,
             response_schema: dict = None) -> dict:
    """
    Call the configured AI provider and return parsed JSON.

    Uses structured outputs (OpenAI) or tool-use (Anthropic) for
    guaranteed valid JSON.
    """
    provider = _get_provider()

    if provider == "openai":
        return _call_openai(system_prompt, user_prompt, response_schema)
    elif provider == "anthropic":
        return _call_anthropic(system_prompt, user_prompt, response_schema)
    elif provider == "gemini":
        return _call_gemini(system_prompt, user_prompt, response_schema)
    else:
        raise ValueError(f"Unknown AI_BRAIN_PROVIDER: {provider}. Use openai, anthropic, or gemini.")


def _call_openai(system_prompt: str, user_prompt: str,
                 response_schema: dict = None) -> dict:
    """Call OpenAI with structured outputs for guaranteed JSON."""
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not set. Get your key from https://platform.openai.com/api-keys"
        )

    client = OpenAI(api_key=api_key)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    kwargs = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o"),
        "messages": messages,
        "temperature": 0.7,
    }

    # Use structured outputs if schema provided
    if response_schema:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": response_schema.get("name", "response"),
                "strict": True,
                "schema": response_schema.get("schema", {}),
            },
        }
    else:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content
    return json.loads(content)


def _call_anthropic(system_prompt: str, user_prompt: str,
                    response_schema: dict = None) -> dict:
    """Call Anthropic Claude using tool-use pattern for structured JSON."""
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Run: pip install anthropic")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set.")

    client = anthropic.Anthropic(api_key=api_key)

    # Use tool-use to enforce JSON schema
    tools = []
    tool_choice = None
    if response_schema:
        tools = [{
            "name": response_schema.get("name", "respond"),
            "description": "Return the structured analysis response.",
            "input_schema": response_schema.get("schema", {"type": "object"}),
        }]
        tool_choice = {"type": "tool", "name": response_schema.get("name", "respond")}

    kwargs = {
        "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice

    message = client.messages.create(**kwargs)

    if tools:
        # Extract from tool use
        for block in message.content:
            if hasattr(block, "input"):
                return block.input
        # Fallback: parse text
        text = message.content[0].text if message.content else "{}"
    else:
        text = message.content[0].text if message.content else "{}"

    # Clean markdown code blocks
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    return json.loads(text)


def _call_gemini(system_prompt: str, user_prompt: str,
                 response_schema: dict = None) -> dict:
    """Call Google Gemini with JSON schema."""
    try:
        import google.generativeai as genai
    except ImportError:
        raise RuntimeError(
            "google-generativeai package not installed. Run: pip install google-generativeai"
        )

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        os.environ.get("GEMINI_MODEL", "gemini-2.5-pro"),
    )

    generation_config = {"response_mime_type": "application/json"}
    if response_schema:
        generation_config["response_schema"] = response_schema.get("schema", {})

    response = model.generate_content(
        f"{system_prompt}\n\n{user_prompt}",
        generation_config=generation_config,
    )

    return json.loads(response.text)


# ═══════════════════════════════════════════════════════════════════
#  Response Schemas (JSON Schema for structured outputs)
# ═══════════════════════════════════════════════════════════════════

PRE_ANALYSIS_SCHEMA = {
    "name": "pre_tournament_analysis",
    "schema": {
        "type": "object",
        "properties": {
            "course_narrative": {"type": "string"},
            "key_factors": {
                "type": "array",
                "items": {"type": "string"},
            },
            "players_to_watch": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "player": {"type": "string"},
                        "edge": {"type": "string"},
                        "adjustment": {"type": "number"},
                    },
                    "required": ["player", "edge", "adjustment"],
                    "additionalProperties": False,
                },
            },
            "players_to_fade": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "player": {"type": "string"},
                        "reason": {"type": "string"},
                        "adjustment": {"type": "number"},
                    },
                    "required": ["player", "reason", "adjustment"],
                    "additionalProperties": False,
                },
            },
            "confidence": {"type": "number"},
        },
        "required": ["course_narrative", "key_factors", "players_to_watch",
                      "players_to_fade", "confidence"],
        "additionalProperties": False,
    },
}

BETTING_DECISIONS_SCHEMA = {
    "name": "betting_decisions",
    "schema": {
        "type": "object",
        "properties": {
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "player": {"type": "string"},
                        "bet_type": {"type": "string"},
                        "odds": {"type": "string"},
                        "model_ev": {"type": "number"},
                        "recommended_stake": {"type": "string"},
                        "confidence": {"type": "string"},
                        "reasoning": {"type": "string"},
                    },
                    "required": ["player", "bet_type", "odds", "model_ev",
                                 "recommended_stake", "confidence", "reasoning"],
                    "additionalProperties": False,
                },
            },
            "portfolio_notes": {"type": "string"},
            "pass_notes": {"type": "string"},
            "total_units": {"type": "number"},
            "expected_roi": {"type": "string"},
        },
        "required": ["decisions", "portfolio_notes", "pass_notes",
                      "total_units", "expected_roi"],
        "additionalProperties": False,
    },
}

POST_REVIEW_SCHEMA = {
    "name": "post_tournament_review",
    "schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "what_worked": {"type": "string"},
            "what_missed": {"type": "string"},
            "learnings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string"},
                        "insight": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["topic", "insight", "confidence"],
                    "additionalProperties": False,
                },
            },
            "weight_suggestions": {
                "type": "object",
                "properties": {
                    "course_fit": {"type": "number"},
                    "form": {"type": "number"},
                    "momentum": {"type": "number"},
                },
                "required": ["course_fit", "form", "momentum"],
                "additionalProperties": False,
            },
            "calibration_note": {"type": "string"},
        },
        "required": ["summary", "what_worked", "what_missed", "learnings",
                      "weight_suggestions", "calibration_note"],
        "additionalProperties": False,
    },
}


# ═══════════════════════════════════════════════════════════════════
#  Context Builders
# ═══════════════════════════════════════════════════════════════════

def _build_field_context(composite_results: list[dict], top_n: int = 30) -> str:
    """Build a concise text summary of the top N players for the AI."""
    lines = []
    for r in composite_results[:top_n]:
        line = (
            f"#{r['rank']} {r['player_display']}: "
            f"composite={r['composite']:.1f}, "
            f"course_fit={r['course_fit']:.1f}, "
            f"form={r['form']:.1f}, "
            f"momentum={r['momentum']:.1f} ({r.get('momentum_direction', '?')})"
        )
        lines.append(line)
    return "\n".join(lines)


def _build_value_context(value_bets: list[dict], top_n: int = 20) -> str:
    """Build text summary of top value bets for the AI."""
    lines = []
    for vb in value_bets[:top_n]:
        line = (
            f"{vb['player_display']} ({vb.get('best_book', '?')}): "
            f"odds={vb.get('best_odds', '?')}, "
            f"model_prob={vb.get('model_prob', 0):.1%}, "
            f"market_prob={vb.get('market_prob', 0):.1%}, "
            f"EV={vb.get('ev', 0):.1%}, "
            f"source={vb.get('prob_source', '?')}"
        )
        lines.append(line)
    return "\n".join(lines) if lines else "No value bets found."


def _build_memory_context(topics: list[str]) -> str:
    """Retrieve and format relevant memories for the AI."""
    memories = db.get_ai_memories(topics=topics, limit=30)
    if not memories:
        return "No prior memories for these topics."
    lines = []
    for m in memories:
        age = ""
        if m.get("created_at"):
            try:
                created = datetime.fromisoformat(m["created_at"])
                days_ago = (datetime.now() - created).days
                age = f" ({days_ago}d ago)"
            except (ValueError, TypeError):
                pass
        lines.append(
            f"[{m['topic']}]{age} (conf={m.get('confidence', '?')}): {m['insight']}"
        )
    return "\n".join(lines)


def _build_roi_context() -> str:
    """Build summary of historical ROI and performance."""
    from src.learning import compute_calibration
    cal = compute_calibration()
    if cal.get("status") == "no_data":
        return "No historical performance data yet. This is early in the model's life."

    roi = cal.get("roi", {})
    brier = cal.get("brier_score")

    lines = [
        f"Historical bets: {roi.get('total_bets', 0)}",
        f"ROI: {roi.get('roi_pct', 0):.1f}%",
        f"Total profit: {roi.get('total_profit', 0):.1f} units",
    ]
    if brier:
        lines.append(f"Brier score: {brier:.4f}")

    comparison = cal.get("model_comparison")
    if comparison:
        lines.append(
            f"Model comparison (Brier, lower=better): "
            f"Us={comparison['model_brier']:.4f}, "
            f"DG={comparison['dg_brier']:.4f}, "
            f"Market={comparison['market_brier']:.4f}"
        )

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
#  Main AI Functions
# ═══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are an expert golf betting analyst AI. You have access to:
- Quantitative model scores (composite, course fit, form, momentum)
- Data Golf pre-tournament probabilities (calibrated model)
- Market odds from multiple sportsbooks
- Historical round-level strokes-gained data
- Course profiles (difficulty ratings, correlated courses)
- Your own persistent memory from past tournaments

Your job is to make smart, data-driven betting decisions. Be specific
and quantitative in your reasoning. When you're uncertain, say so.
Your confidence should reflect genuine uncertainty, not just optimism.

Key principles:
- Only recommend bets on players ranked in the model's top 35 by composite score.
  The composite ranking reflects course fit, form, and momentum — do not override it
  with gut feel. If a player is not in the top 35, do not recommend them.
- Only bet when there's genuine edge (positive EV preferred, minimum -3% tolerable with strong qualitative reasons)
- Consider correlation between bets (don't over-expose to similar outcomes)
- HARD RULE: No single player may receive more than 40% of total units wagered. No single bet may exceed 3 units. Spread risk across at least 3 players when possible.
- Course fit matters more at some venues than others
- Recent form (last 8-12 rounds) is usually more predictive than long-term averages
- DG course-history model probabilities are well-calibrated; trust them
- The market is usually efficient; large deviations should have a strong reason
- When no positive-EV bets exist, it is acceptable to pass entirely — not every week has value"""


def pre_tournament_analysis(tournament_id: int,
                            composite_results: list[dict],
                            course_profile: dict = None,
                            tournament_name: str = "",
                            course_name: str = "") -> dict:
    """
    AI pre-tournament analysis: qualitative edge-finding.

    Returns structured analysis with player adjustments.
    """
    # Build context
    field_ctx = _build_field_context(composite_results)

    course_ctx = "No course profile available."
    if course_profile:
        ratings = course_profile.get("skill_ratings", {})
        facts = course_profile.get("course_facts", {})
        correlated = facts.get("correlated_courses", [])
        course_ctx = (
            f"Course: {course_name}\n"
            f"Par: {facts.get('par', '?')}, Yardage: {facts.get('yardage', '?')}\n"
            f"Scoring: {facts.get('avg_scoring_conditions', '?')}\n"
            f"Greens: {facts.get('greens_surface', '?')}, Speed: {facts.get('greens_speed', '?')}\n"
            f"SG:OTT difficulty: {ratings.get('sg_ott', '?')}\n"
            f"SG:APP difficulty: {ratings.get('sg_app', '?')}\n"
            f"SG:ARG difficulty: {ratings.get('sg_arg', '?')}\n"
            f"SG:Putting difficulty: {ratings.get('sg_putting', '?')}\n"
            f"Correlated courses: {', '.join(correlated[:5]) if correlated else 'Unknown'}"
        )

    # Memory topics: course, correlated courses, general strategy
    memory_topics = [course_name.lower().replace(" ", "_")] if course_name else []
    memory_topics += ["general_strategy", "course_fit_learning"]
    if course_profile:
        correlated = course_profile.get("course_facts", {}).get("correlated_courses", [])
        memory_topics += [c.lower().replace(" ", "_") for c in correlated[:3]]
    memory_ctx = _build_memory_context(memory_topics)

    user_prompt = f"""Tournament: {tournament_name}
Course: {course_name}

=== COURSE PROFILE ===
{course_ctx}

=== TOP 30 PLAYERS BY COMPOSITE SCORE ===
{field_ctx}

=== RELEVANT MEMORIES FROM PAST TOURNAMENTS ===
{memory_ctx}

Analyze this field and course. Identify:
1. A narrative about what skills matter most this week
2. Key factors that will separate the field
3. Players who have an edge the numbers might understate (with a small +/- adjustment to their composite)
4. Players to fade (overrated by the model this week)
5. Your overall confidence in the model's output for this event (0-1)

Keep adjustments small: -5 to +5 points on the 0-100 composite scale."""

    result = _call_ai(SYSTEM_PROMPT, user_prompt, PRE_ANALYSIS_SCHEMA)

    # Log decision
    db.store_ai_decision(
        tournament_id, "pre_analysis",
        f"Field: {len(composite_results)} players, Course: {course_name}",
        json.dumps(result),
    )

    return result


def _enforce_portfolio_limits(result: dict,
                              max_player_pct: float = 0.40,
                              max_single_bet_units: float = 3.0) -> dict:
    """
    Enforce portfolio diversification limits on AI betting decisions.

    Rules:
    - No single player may receive more than max_player_pct (40%) of total units
    - No individual bet may exceed max_single_bet_units (3 units)
    - If limits are violated, stakes are proportionally scaled down

    Returns the result dict with adjusted stakes if necessary.
    """
    decisions = result.get("decisions", [])
    if not decisions:
        return result

    # Parse stakes from each decision
    parsed = []
    for d in decisions:
        stake_str = d.get("recommended_stake", "0")
        try:
            stake = float(str(stake_str).replace("u", "").replace("U", "").strip())
        except (ValueError, TypeError):
            stake = 1.0
        parsed.append({"decision": d, "stake": stake, "player": d.get("player", "")})

    # Cap individual bets
    any_capped = False
    for p in parsed:
        if p["stake"] > max_single_bet_units:
            logger.warning(
                "Portfolio limit: capping %s %s from %.1f to %.1f units",
                p["player"], p["decision"].get("bet_type", ""),
                p["stake"], max_single_bet_units,
            )
            p["stake"] = max_single_bet_units
            any_capped = True

    # Check per-player concentration
    total_units = sum(p["stake"] for p in parsed)
    if total_units > 0:
        player_totals = defaultdict(float)
        for p in parsed:
            player_totals[p["player"]] += p["stake"]

        for player, player_total in player_totals.items():
            pct = player_total / total_units
            if pct > max_player_pct:
                # Scale down this player's bets proportionally
                max_allowed = max_player_pct * total_units
                scale_factor = max_allowed / player_total
                logger.warning(
                    "Portfolio limit: scaling %s from %.1f units (%.0f%%) to %.1f units (%.0f%%)",
                    player, player_total, pct * 100,
                    max_allowed, max_player_pct * 100,
                )
                for p in parsed:
                    if p["player"] == player:
                        p["stake"] = round(p["stake"] * scale_factor, 2)
                any_capped = True

    # Write back adjusted stakes
    if any_capped:
        new_total = sum(p["stake"] for p in parsed)
        for p in parsed:
            p["decision"]["recommended_stake"] = f"{p['stake']:.1f}u"
        result["total_units"] = round(new_total, 2)
        result["portfolio_notes"] = (
            result.get("portfolio_notes", "")
            + f" [Portfolio limits applied: max {max_player_pct*100:.0f}% per player, "
            + f"max {max_single_bet_units:.0f}u per bet. Adjusted total: {new_total:.1f}u]"
        )

    return result


def make_betting_decisions(tournament_id: int,
                           value_bets_by_type: dict,
                           pre_analysis: dict = None,
                           composite_results: list[dict] = None,
                           tournament_name: str = "",
                           course_name: str = "") -> dict:
    """
    DISABLED: AI betting decisions removed due to poor performance.
    The AI concentrated 87% of units on one player and recommended bets on
    corrupted +500000 odds data. Betting decisions are now purely quantitative.
    Returns None so all callers (service, run_predictions, app, analyze) skip AI bets.
    """
    logger.info("AI betting decisions disabled — returning None")
    return None

    # --- Original implementation below (preserved for potential re-enablement) ---
    # Build value bets context — show top bets per market (not just positive EV)
    value_lines = []
    for bet_type, bets in value_bets_by_type.items():
        value_only = [b for b in bets if b.get("is_value")]
        if value_only:
            value_lines.append(f"\n--- {bet_type.upper()} ({len(value_only)} POSITIVE-EV bets) ---")
            value_lines.append(_build_value_context(value_only))
        else:
            # Show top 8 closest-to-value bets so AI has context
            top_bets = sorted(bets, key=lambda x: x.get("ev", -999), reverse=True)[:8]
            if top_bets:
                value_lines.append(f"\n--- {bet_type.upper()} (0 positive-EV, showing top 8 closest) ---")
                value_lines.append(_build_value_context(top_bets))
    value_ctx = "\n".join(value_lines) if value_lines else "No value bets found in any market."

    # Build composite rankings context so AI knows the model's player ordering
    rankings_ctx = "No composite rankings available."
    if composite_results:
        rank_lines = []
        for r in composite_results[:35]:
            rank_lines.append(
                f"#{r['rank']} {r['player_display']}: "
                f"composite={r['composite']:.1f}, "
                f"course_fit={r['course_fit']:.1f}, "
                f"form={r['form']:.1f}, "
                f"momentum={r['momentum']:.1f} ({r.get('momentum_direction', '?')})"
            )
        rankings_ctx = "\n".join(rank_lines)

    pre_ctx = ""
    if pre_analysis:
        pre_ctx = (
            f"Your pre-tournament analysis:\n"
            f"Narrative: {pre_analysis.get('course_narrative', 'N/A')}\n"
            f"Key factors: {', '.join(pre_analysis.get('key_factors', []))}\n"
            f"Confidence: {pre_analysis.get('confidence', 'N/A')}"
        )

    roi_ctx = _build_roi_context()

    memory_topics = ["betting_strategy", "bankroll", "bet_sizing"]
    if course_name:
        memory_topics.append(course_name.lower().replace(" ", "_"))
    memory_ctx = _build_memory_context(memory_topics)

    user_prompt = f"""Tournament: {tournament_name} at {course_name}

=== MODEL COMPOSITE RANKINGS (Top 35) ===
IMPORTANT: You may ONLY recommend bets on players listed below.
Do NOT recommend any player outside this top-35 ranking.

{rankings_ctx}

=== ODDS & EV BY MARKET ===
{value_ctx}

=== YOUR PRE-TOURNAMENT ANALYSIS ===
{pre_ctx}

=== HISTORICAL PERFORMANCE ===
{roi_ctx}

=== RELEVANT MEMORIES ===
{memory_ctx}

Make your betting decisions for this tournament. For each bet:
- State the player, bet type, odds, EV, and recommended stake (in units)
- The player MUST be in the top-35 composite rankings above
- Explain your reasoning (2-3 sentences), referencing their model scores
- Rate confidence: "high", "medium", or "low"

If no bets have genuine edge this week, it is fine to pass entirely (empty decisions list).

Also provide:
- Portfolio notes (correlation, total exposure)
- What you're passing on and why
- Total units to be wagered
- Expected ROI for this week's bets

PORTFOLIO RULES (enforced post-hoc, but follow them to avoid scaling):
- Max 40% of total units on any single player across all bet types
- Max 3 units on any individual bet
- Diversify across at least 3 players when placing 3+ bets"""

    result = _call_ai(SYSTEM_PROMPT, user_prompt, BETTING_DECISIONS_SCHEMA)

    # Enforce portfolio diversification limits post-hoc
    result = _enforce_portfolio_limits(result)

    db.store_ai_decision(
        tournament_id, "betting_decisions",
        f"Tournament: {tournament_name}, Markets: {list(value_bets_by_type.keys())}",
        json.dumps(result),
    )

    return result


def post_tournament_review(tournament_id: int,
                           scoring_result: dict = None,
                           value_bets_by_type: dict = None,
                           tournament_name: str = "",
                           course_name: str = "") -> dict:
    """
    AI post-tournament review: what worked, what to learn.

    Stores learnings in persistent memory.
    """
    # Get the AI's prior decisions
    prior_decisions = db.get_ai_decisions(tournament_id=tournament_id)
    prior_ctx = ""
    for d in prior_decisions:
        if d["phase"] in ("pre_analysis", "betting_decisions"):
            output = d.get("output_json") or ""
            prior_ctx += f"\n--- {d['phase']} ---\n{output[:1000]}\n"

    scoring_ctx = "No scoring data."
    if scoring_result:
        scoring_ctx = (
            f"Picks scored: {scoring_result.get('scored', 0)}\n"
            f"Hits: {scoring_result.get('hits', 0)}\n"
            f"Misses: {scoring_result.get('misses', 0)}\n"
            f"Hit rate: {scoring_result.get('hit_rate', 0):.1%}\n"
            f"Profit: {scoring_result.get('total_profit', 0):.1f} units"
        )

    roi_ctx = _build_roi_context()

    user_prompt = f"""Tournament: {tournament_name} at {course_name}

=== YOUR PRIOR ANALYSIS & DECISIONS ===
{prior_ctx}

=== RESULTS ===
{scoring_ctx}

=== CUMULATIVE PERFORMANCE ===
{roi_ctx}

Review this tournament's results against your predictions and decisions.

1. What's the headline summary?
2. What worked well? (Be specific about which factors/players/bet types)
3. What did the model miss? (Be honest about failures)
4. What should you remember for next time? (Learnings with topic tags and confidence)
5. Should the model weights change? Suggest course_fit/form/momentum weights (must sum to ~1.0)
6. Calibration note: were we overconfident or underconfident?"""

    result = _call_ai(SYSTEM_PROMPT, user_prompt, POST_REVIEW_SCHEMA)

    db.store_ai_decision(
        tournament_id, "post_review",
        f"Tournament: {tournament_name}, Scoring: {scoring_ctx[:200]}",
        json.dumps(result),
    )

    # Store learnings in persistent memory
    for learning in result.get("learnings", []):
        topic = learning.get("topic", "general")
        insight = learning.get("insight", "")
        confidence = learning.get("confidence", 0.5)
        if insight:
            db.store_ai_memory(
                topic=topic,
                insight=insight,
                source_tournament_id=tournament_id,
                confidence=confidence,
                expires_days=180,
            )

    return result


# ═══════════════════════════════════════════════════════════════════
#  Utilities
# ═══════════════════════════════════════════════════════════════════

def apply_ai_adjustments(composite_results: list[dict],
                         pre_analysis: dict) -> list[dict]:
    """
    Apply the AI's pre-tournament player adjustments to composite scores.

    Modifies scores in-place and re-sorts.
    """
    if not pre_analysis:
        return composite_results

    # Build adjustment map
    adjustments = {}
    for p in pre_analysis.get("players_to_watch", []):
        name = p.get("player")
        adj = p.get("adjustment", 0)
        if name and adj:
            from src.player_normalizer import normalize_name
            adjustments[normalize_name(name)] = adj

    for p in pre_analysis.get("players_to_fade", []):
        name = p.get("player")
        adj = p.get("adjustment", 0)
        if name and adj:
            from src.player_normalizer import normalize_name
            adjustments[normalize_name(name)] = adj

    if not adjustments:
        return composite_results

    # Apply adjustments, clamped to [-5.0, +5.0]
    for r in composite_results:
        adj = adjustments.get(r["player_key"], 0)
        if adj:
            clamped = max(-5.0, min(5.0, adj))
            if clamped != adj:
                import logging
                logging.getLogger("ai_brain").warning(
                    f"Clamped AI adjustment for {r.get('player_display', r['player_key'])}: "
                    f"{adj} -> {clamped}"
                )
            r["composite"] = round(r["composite"] + clamped, 2)
            r["ai_adjustment"] = clamped

    # Re-sort and re-rank
    composite_results.sort(key=lambda x: x["composite"], reverse=True)
    for i, r in enumerate(composite_results):
        r["rank"] = i + 1

    return composite_results


def is_ai_available() -> bool:
    """Check if an AI provider is configured and available."""
    provider = _get_provider()
    if provider == "openai":
        return bool(os.environ.get("OPENAI_API_KEY"))
    elif provider == "anthropic":
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
    elif provider == "gemini":
        return bool(os.environ.get("GOOGLE_API_KEY"))
    return False


def call_ai(prompt: str, system_prompt: str = None,
            max_tokens: int = None, response_schema: dict = None) -> dict:
    """
    Public interface for making AI calls.

    Args:
        prompt: The user prompt / question.
        system_prompt: Optional system prompt (defaults to a generic golf analyst).
        max_tokens: Ignored (kept for API compatibility; provider handles limits).
        response_schema: Optional JSON schema for structured output.

    Returns: Parsed JSON dict from the AI provider.
    """
    if system_prompt is None:
        system_prompt = (
            "You are an expert golf analytics researcher. "
            "Respond with valid JSON only."
        )
    return _call_ai(system_prompt, prompt, response_schema)


def get_ai_status() -> dict:
    """Return status of AI brain configuration."""
    provider = _get_provider()
    available = is_ai_available()
    memory_count = len(db.get_ai_memories(limit=9999))
    topics = db.get_all_ai_memory_topics()

    return {
        "provider": provider,
        "available": available,
        "model": os.environ.get(
            f"{provider.upper()}_MODEL",
            {"openai": "gpt-4o", "anthropic": "claude-sonnet-4-20250514",
             "gemini": "gemini-2.5-pro"}.get(provider, "unknown"),
        ),
        "memory_count": memory_count,
        "memory_topics": topics,
    }
