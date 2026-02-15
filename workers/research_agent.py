"""
Autonomous Research Agent

A 5-thread daemon that continuously improves the golf prediction model:

Thread 1 - DATA COLLECTOR: Keeps historical data fresh
Thread 2 - HYPOTHESIS GENERATOR: Uses AI to propose new strategies
Thread 3 - EXPERIMENT RUNNER: Executes backtests on pending experiments
Thread 4 - OUTLIER ANALYST: Investigates prediction misses for insights
Thread 5 - OPTIMIZER: Bayesian neighborhood search around best strategies

Runs as a background daemon. Each thread sleeps between cycles to
respect API rate limits and CPU usage.
"""

import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime

logger = logging.getLogger("research_agent")

# Global shutdown flag
_shutdown = threading.Event()


def _handle_signal(signum, frame):
    logger.info("Received signal %d, shutting down...", signum)
    _shutdown.set()


# ═══════════════════════════════════════════════════════════════════
#  Thread 1: Data Collector
# ═══════════════════════════════════════════════════════════════════

def data_collector_loop(interval_hours: float = 6.0):
    """
    Keeps historical data up to date.

    Runs backfill for current + previous year to catch newly completed events.
    Rebuilds PIT stats for any new events.
    """
    from backtester.backfill import run_full_backfill
    from backtester.pit_stats import build_all_pit_stats

    while not _shutdown.is_set():
        try:
            current_year = datetime.now().year
            years = [current_year - 1, current_year]

            logger.info("[DATA] Starting data refresh for %s", years)
            run_full_backfill(
                tours=["pga"],
                years=years,
                include_weather=True,
                include_odds=True,
                include_predictions=True,
            )

            logger.info("[DATA] Rebuilding PIT stats...")
            build_all_pit_stats(years=years)

            logger.info("[DATA] Refresh complete, sleeping %.1f hours", interval_hours)
        except Exception as e:
            logger.error("[DATA] Error: %s", e)

        _shutdown.wait(interval_hours * 3600)


# ═══════════════════════════════════════════════════════════════════
#  Thread 2: Hypothesis Generator
# ═══════════════════════════════════════════════════════════════════

def hypothesis_generator_loop(interval_hours: float = 12.0):
    """
    Uses AI to generate new strategy hypotheses based on:
    - Current experiment results
    - Outlier investigation findings
    - Model performance patterns
    """
    from src import db
    from backtester.experiments import (
        create_experiment, get_experiment_leaderboard,
    )
    from backtester.strategy import StrategyConfig

    while not _shutdown.is_set():
        try:
            logger.info("[HYPOTHESIS] Generating new hypotheses...")

            # Gather context for AI
            leaderboard = get_experiment_leaderboard(limit=10)
            conn = db.get_conn()

            # Recent outlier insights
            outliers = conn.execute("""
                SELECT root_cause, suggested_model_change, COUNT(*) as cnt
                FROM outlier_investigations
                WHERE actionable = 1 AND suggested_model_change IS NOT NULL
                GROUP BY root_cause
                ORDER BY cnt DESC
                LIMIT 5
            """).fetchall()

            outlier_insights = [
                {"cause": o[0], "suggestion": o[1], "count": o[2]}
                for o in outliers
            ]

            # Build prompt
            prompt = _build_hypothesis_prompt(leaderboard, outlier_insights)

            try:
                from src.ai_brain import call_ai
                response = call_ai(prompt, max_tokens=1000)
                hypotheses = _parse_hypotheses(response)
            except Exception as e:
                logger.warning("[HYPOTHESIS] AI call failed: %s, using fallback", e)
                hypotheses = _fallback_hypotheses()

            # Create experiments for each hypothesis
            for h in hypotheses[:3]:  # Max 3 per cycle
                try:
                    strategy = StrategyConfig(**h.get("config", {}))
                    strategy.name = h.get("name", "ai_hypothesis")
                    create_experiment(
                        hypothesis=h.get("hypothesis", "AI generated"),
                        strategy=strategy,
                        source="ai_hypothesis",
                        scope=h.get("scope", "global"),
                    )
                except Exception as e:
                    logger.warning("[HYPOTHESIS] Failed to create experiment: %s", e)

            logger.info("[HYPOTHESIS] Generated %d hypotheses, sleeping %.1f hours",
                        len(hypotheses), interval_hours)
        except Exception as e:
            logger.error("[HYPOTHESIS] Error: %s", e)

        _shutdown.wait(interval_hours * 3600)


def _build_hypothesis_prompt(leaderboard: list, outlier_insights: list) -> str:
    top_strategies = json.dumps(leaderboard[:5], indent=2) if leaderboard else "No experiments yet"
    insights = json.dumps(outlier_insights, indent=2) if outlier_insights else "No outlier insights yet"

    return f"""You are an expert golf analytics researcher. Your job is to generate NEW strategy hypotheses
that could improve our golf betting model's ROI.

CURRENT TOP STRATEGIES:
{top_strategies}

OUTLIER INVESTIGATION INSIGHTS (recurring patterns):
{insights}

AVAILABLE WEIGHT PARAMETERS (must sum reasonably):
- w_sg_total: weight for overall strokes gained (default 0.30)
- w_sg_app: weight for approach play (default 0.15)
- w_sg_ott: weight for off-the-tee driving (default 0.10)
- w_sg_arg: weight for around-the-green (default 0.05)
- w_sg_putt: weight for putting (default 0.10)
- w_form: weight for recent form (default 0.15)
- w_course_fit: weight for course fit (default 0.15)

OTHER TUNABLE PARAMETERS:
- min_ev: minimum expected value to bet (default 0.05)
- stat_window: rolling rounds window - 12, 24, or 50 (default 24)
- softmax_temp: probability sharpness (default 1.0, lower = more concentrated)
- kelly_fraction: bet sizing fraction (default 0.25)

Generate 3 NEW hypotheses as JSON array. Each element:
{{
  "name": "short_name",
  "hypothesis": "What we're testing and why",
  "scope": "global" or "links" or "parkland",
  "config": {{strategy parameters to change from defaults}}
}}

Focus on NOVEL ideas not already tested. Consider:
- Weather-adjusted strategies
- Course-type specific weights
- Different rolling windows for volatile vs stable players
- Approach-heavy weighting for specific course types
- Putting weight changes for Bermuda vs bentgrass"""


def _parse_hypotheses(response: str) -> list[dict]:
    """Extract hypothesis JSON from AI response."""
    if not response:
        return []
    try:
        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            return json.loads(response[start:end])
    except (json.JSONDecodeError, ValueError):
        pass

    # Try individual objects
    results = []
    for chunk in response.split("},"):
        chunk = chunk.strip()
        if not chunk.endswith("}"):
            chunk += "}"
        try:
            start = chunk.find("{")
            if start >= 0:
                results.append(json.loads(chunk[start:]))
        except (json.JSONDecodeError, ValueError):
            pass
    return results


def _fallback_hypotheses() -> list[dict]:
    """Generate simple hypotheses when AI is unavailable."""
    return [
        {
            "name": "approach_heavy",
            "hypothesis": "Increase approach weight — approach play most predictive of scoring",
            "scope": "global",
            "config": {"w_sg_app": 0.25, "w_sg_total": 0.20},
        },
        {
            "name": "short_window",
            "hypothesis": "Use 12-round window — recent hot form matters more than stability",
            "scope": "global",
            "config": {"stat_window": 12},
        },
        {
            "name": "higher_ev_threshold",
            "hypothesis": "Raise min_ev to 8% — only take strong edges, reduce variance",
            "scope": "global",
            "config": {"min_ev": 0.08, "kelly_fraction": 0.30},
        },
    ]


# ═══════════════════════════════════════════════════════════════════
#  Thread 3: Experiment Runner
# ═══════════════════════════════════════════════════════════════════

def experiment_runner_loop(interval_hours: float = 2.0):
    """
    Picks pending experiments and runs them.
    Evaluates significance and promotes winners.
    """
    from src import db
    from backtester.experiments import (
        run_experiment, evaluate_significance, promote_strategy,
    )

    while not _shutdown.is_set():
        try:
            conn = db.get_conn()

            # Find pending experiments
            pending = conn.execute("""
                SELECT id FROM experiments
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT 3
            """).fetchall()

            if not pending:
                logger.info("[RUNNER] No pending experiments, sleeping")
            else:
                for (exp_id,) in pending:
                    if _shutdown.is_set():
                        break

                    logger.info("[RUNNER] Running experiment %d...", exp_id)
                    try:
                        run_experiment(exp_id)
                        sig = evaluate_significance(exp_id)
                        if sig.get("significant"):
                            promote_strategy(exp_id)
                            logger.info("[RUNNER] Experiment %d is SIGNIFICANT! ROI=%.1f%%",
                                       exp_id, sig.get("roi_pct", 0))
                    except Exception as e:
                        logger.error("[RUNNER] Experiment %d failed: %s", exp_id, e)

        except Exception as e:
            logger.error("[RUNNER] Error: %s", e)

        _shutdown.wait(interval_hours * 3600)


# ═══════════════════════════════════════════════════════════════════
#  Thread 4: Outlier Analyst
# ═══════════════════════════════════════════════════════════════════

def outlier_analyst_loop(interval_hours: float = 8.0):
    """
    Reviews recently completed events for prediction outliers.
    Runs AI investigation on top misses.
    """
    from src import db
    from backtester.outlier_investigator import investigate_event

    while not _shutdown.is_set():
        try:
            conn = db.get_conn()
            current_year = datetime.now().year

            # Find events with PIT stats but no outlier investigations
            events = conn.execute("""
                SELECT DISTINCT p.event_id, p.year
                FROM pit_rolling_stats p
                LEFT JOIN outlier_investigations o
                    ON p.event_id = o.event_id AND p.year = o.year
                WHERE o.id IS NULL AND p.year >= ?
                LIMIT 5
            """, (current_year - 1,)).fetchall()

            for event_id, year in events:
                if _shutdown.is_set():
                    break
                logger.info("[OUTLIER] Investigating %s/%d", event_id, year)
                try:
                    results = investigate_event(
                        event_id, year,
                        threshold=25,
                        use_ai=True,
                        max_outliers=5,
                    )
                    logger.info("[OUTLIER] Found %d outliers for %s/%d",
                               len(results), event_id, year)
                except Exception as e:
                    logger.error("[OUTLIER] Investigation failed for %s/%d: %s",
                                event_id, year, e)

        except Exception as e:
            logger.error("[OUTLIER] Error: %s", e)

        _shutdown.wait(interval_hours * 3600)


# ═══════════════════════════════════════════════════════════════════
#  Thread 5: Optimizer (Bayesian Neighborhood Search)
# ═══════════════════════════════════════════════════════════════════

def optimizer_loop(interval_hours: float = 4.0):
    """
    Takes the current best strategy and generates neighboring
    variations for fine-tuning via Bayesian-style exploration.
    """
    from backtester.experiments import (
        get_active_strategy, create_experiment,
        generate_neighbor_strategies,
    )

    while not _shutdown.is_set():
        try:
            logger.info("[OPTIMIZER] Generating neighbor strategies...")
            base = get_active_strategy("global")

            neighbors = generate_neighbor_strategies(base, n=3, perturbation=0.03)
            for i, neighbor in enumerate(neighbors):
                neighbor.name = f"opt_{datetime.now().strftime('%m%d')}_{i}"
                create_experiment(
                    hypothesis=f"Bayesian neighborhood optimization around current best ({base.name})",
                    strategy=neighbor,
                    source="bayesian_opt",
                    scope="global",
                )

            logger.info("[OPTIMIZER] Created %d neighbor experiments", len(neighbors))
        except Exception as e:
            logger.error("[OPTIMIZER] Error: %s", e)

        _shutdown.wait(interval_hours * 3600)


# ═══════════════════════════════════════════════════════════════════
#  Daemon Entry Point
# ═══════════════════════════════════════════════════════════════════

def start_agent(config: dict = None):
    """
    Start the autonomous research agent with all 5 threads.

    config keys:
        data_interval: hours between data refreshes (default 6)
        hypothesis_interval: hours between hypothesis generation (default 12)
        runner_interval: hours between experiment runs (default 2)
        outlier_interval: hours between outlier analyses (default 8)
        optimizer_interval: hours between optimization runs (default 4)
    """
    if config is None:
        config = {}

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # Ensure DB is initialized
    from src.db import ensure_initialized
    ensure_initialized()

    logger.info("=" * 60)
    logger.info("  AUTONOMOUS RESEARCH AGENT STARTING")
    logger.info("  Press Ctrl+C to stop")
    logger.info("=" * 60)

    threads = [
        threading.Thread(
            target=data_collector_loop,
            args=(config.get("data_interval", 6.0),),
            name="DataCollector",
            daemon=True,
        ),
        threading.Thread(
            target=hypothesis_generator_loop,
            args=(config.get("hypothesis_interval", 12.0),),
            name="HypothesisGen",
            daemon=True,
        ),
        threading.Thread(
            target=experiment_runner_loop,
            args=(config.get("runner_interval", 2.0),),
            name="ExperimentRunner",
            daemon=True,
        ),
        threading.Thread(
            target=outlier_analyst_loop,
            args=(config.get("outlier_interval", 8.0),),
            name="OutlierAnalyst",
            daemon=True,
        ),
        threading.Thread(
            target=optimizer_loop,
            args=(config.get("optimizer_interval", 4.0),),
            name="Optimizer",
            daemon=True,
        ),
    ]

    for t in threads:
        t.start()
        logger.info("  Started thread: %s", t.name)

    # Wait for shutdown signal
    try:
        while not _shutdown.is_set():
            _shutdown.wait(1)
    except KeyboardInterrupt:
        _shutdown.set()

    logger.info("Shutting down agent threads...")
    for t in threads:
        t.join(timeout=10)

    logger.info("Research agent stopped.")


if __name__ == "__main__":
    start_agent()
