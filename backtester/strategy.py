"""
Strategy Configuration & Simulation Engine

StrategyConfig: Defines model weights, thresholds, and parameters.
SimulationResult: Holds results + performance metrics for a simulated strategy.
replay_event: Replays a historical tournament using PIT stats and historical odds.

The replay engine works by:
  1. Loading PIT rolling stats (what we would have known pre-tournament)
  2. Computing composite scores using the StrategyConfig weights
  3. Converting to model probabilities
  4. Comparing against historical odds to find value bets
  5. Evaluating actual outcomes (did the bet win?)
  6. Computing ROI, CLV, Sharpe, calibration metrics
"""

import json
import logging
import math
from dataclasses import dataclass, field, asdict
from typing import Optional

from src import db
from src.datagolf import _safe_float
from src.player_normalizer import normalize_name
from src.scoring import determine_outcome_from_text, compute_profit, american_to_decimal

logger = logging.getLogger("strategy")


# ═══════════════════════════════════════════════════════════════════
#  Strategy Configuration
# ═══════════════════════════════════════════════════════════════════

@dataclass
class StrategyConfig:
    """
    Complete configuration for a betting strategy.

    All parameters that affect model output or bet selection are captured
    here so strategies can be compared, tracked, and optimized.
    """
    # Model weights (must sum to 1.0)
    w_sg_total: float = 0.30
    w_sg_app: float = 0.15
    w_sg_ott: float = 0.10
    w_sg_arg: float = 0.05
    w_sg_putt: float = 0.10
    w_form: float = 0.15
    w_course_fit: float = 0.15

    # Rolling stat window (12, 24, or 50)
    stat_window: int = 24

    # Minimum EV threshold to place a bet (e.g., 0.05 = 5%)
    min_ev: float = 0.05

    # Maximum implied probability from the book (filter longshots)
    max_implied_prob: float = 0.50

    # Minimum model probability to consider (filter tiny edges)
    min_model_prob: float = 0.005

    # Kelly fraction (fraction of full Kelly to bet)
    kelly_fraction: float = 0.25

    # Markets to bet
    markets: list = field(default_factory=lambda: ["win", "top_5", "top_10", "top_20"])

    # Softmax temperature for probability conversion
    softmax_temp: float = 1.0

    # AI adjustment cap
    ai_adj_cap: float = 5.0

    # Enable weather adjustments
    use_weather: bool = True

    # Name/description
    name: str = "default"
    description: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> "StrategyConfig":
        return cls(**json.loads(s))

    def normalized_weights(self) -> dict:
        """Return weights normalized to sum to 1.0."""
        raw = {
            "sg_total": self.w_sg_total,
            "sg_app": self.w_sg_app,
            "sg_ott": self.w_sg_ott,
            "sg_arg": self.w_sg_arg,
            "sg_putt": self.w_sg_putt,
            "form": self.w_form,
            "course_fit": self.w_course_fit,
        }
        total = sum(raw.values())
        if total == 0:
            return {k: 1.0 / len(raw) for k in raw}
        return {k: v / total for k, v in raw.items()}


# ═══════════════════════════════════════════════════════════════════
#  Simulation Result
# ═══════════════════════════════════════════════════════════════════

@dataclass
class SimulationResult:
    """Results from replaying a strategy across historical events."""
    strategy: StrategyConfig
    events_simulated: int = 0
    total_bets: int = 0
    wins: int = 0
    total_wagered: float = 0.0
    total_returned: float = 0.0
    roi_pct: float = 0.0
    clv_avg: float = 0.0
    sharpe: float = 0.0
    calibration_error: float = 0.0
    bet_details: list = field(default_factory=list)
    event_results: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def compute_metrics(self):
        """Calculate summary metrics from bet details."""
        if not self.bet_details:
            return

        self.total_bets = len(self.bet_details)
        self.wins = sum(1 for b in self.bet_details if b.get("won"))
        self.total_wagered = sum(b.get("wager", 1.0) for b in self.bet_details)
        self.total_returned = sum(b.get("payout", 0.0) for b in self.bet_details)

        if self.total_wagered > 0:
            self.roi_pct = round(
                (self.total_returned - self.total_wagered) / self.total_wagered * 100, 2
            )

        # CLV: average of (model_prob - closing_implied_prob) for each bet
        clvs = [b.get("clv", 0.0) for b in self.bet_details if "clv" in b]
        if clvs:
            self.clv_avg = round(sum(clvs) / len(clvs), 4)

        # Sharpe: mean return / std of returns per bet
        returns = []
        for b in self.bet_details:
            wager = b.get("wager", 1.0)
            payout = b.get("payout", 0.0)
            returns.append((payout - wager) / wager if wager > 0 else 0)
        if len(returns) > 1:
            mean_r = sum(returns) / len(returns)
            var_r = sum((r - mean_r) ** 2 for r in returns) / (len(returns) - 1)
            std_r = math.sqrt(var_r) if var_r > 0 else 1e-6
            self.sharpe = round(mean_r / std_r, 3)

        # Calibration: compare predicted probabilities to actual hit rates
        # Group by probability bucket
        buckets = {}
        for b in self.bet_details:
            mp = b.get("model_prob", 0)
            bucket = round(mp * 20) / 20  # 5% buckets
            if bucket not in buckets:
                buckets[bucket] = {"predicted": [], "actual": []}
            buckets[bucket]["predicted"].append(mp)
            buckets[bucket]["actual"].append(1 if b.get("won") else 0)

        cal_errors = []
        for bucket, data in buckets.items():
            if len(data["predicted"]) >= 3:
                pred_avg = sum(data["predicted"]) / len(data["predicted"])
                actual_avg = sum(data["actual"]) / len(data["actual"])
                cal_errors.append(abs(pred_avg - actual_avg))

        if cal_errors:
            self.calibration_error = round(sum(cal_errors) / len(cal_errors), 4)

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy.name,
            "events_simulated": self.events_simulated,
            "total_bets": self.total_bets,
            "wins": self.wins,
            "roi_pct": self.roi_pct,
            "clv_avg": self.clv_avg,
            "sharpe": self.sharpe,
            "calibration_error": self.calibration_error,
            "total_wagered": round(self.total_wagered, 2),
            "total_returned": round(self.total_returned, 2),
            "errors": self.errors[:10],
        }


# ═══════════════════════════════════════════════════════════════════
#  Replay Engine
# ═══════════════════════════════════════════════════════════════════

def _compute_composite(pit: dict, weights: dict) -> float:
    """
    Compute composite score from PIT stats using strategy weights.

    IMPORTANT: This is a simplified SG-weighted model used for backtesting.
    The live model (src/models/composite.py) uses course_fit + form + momentum
    sub-models with richer signal processing. Backtest results validate this
    simplified SG model, NOT the full live model. This divergence is documented
    and intentional -- aligning would require building full sub-model scores
    from PIT stats, which is a future enhancement.

    Higher is better.
    """
    score = 0.0
    if pit.get("sg_total") is not None:
        score += weights.get("sg_total", 0) * pit["sg_total"]
    if pit.get("sg_app") is not None:
        score += weights.get("sg_app", 0) * pit["sg_app"]
    if pit.get("sg_ott") is not None:
        score += weights.get("sg_ott", 0) * pit["sg_ott"]
    if pit.get("sg_arg") is not None:
        score += weights.get("sg_arg", 0) * pit["sg_arg"]
    if pit.get("sg_putt") is not None:
        score += weights.get("sg_putt", 0) * pit["sg_putt"]
    return score


# Market-specific softmax temperatures matching the live model (src/value.py)
MARKET_SOFTMAX_TEMPS = {
    "win": 8.0,
    "top_5": 10.0,
    "top_10": 12.0,
    "top_20": 15.0,
    "make_cut": 20.0,
}


def _softmax_probs(scores: list[float], temperature: float = 12.0,
                   target_sum: float = 1.0) -> list[float]:
    """
    Convert composite scores to probabilities via softmax.

    Applies clamping [0.001, 0.95] per player then renormalizes to preserve
    target_sum, matching the live model behavior.
    """
    if not scores:
        return []
    n = len(scores)
    max_s = max(scores)
    exps = [math.exp((s - max_s) / max(temperature, 0.01)) for s in scores]
    total = sum(exps)
    if total == 0:
        return [target_sum / n] * n

    raw_probs = [target_sum * e / total for e in exps]

    # Clamp then renormalize (matching live model behavior)
    clamped = [max(0.001, min(0.95, p)) for p in raw_probs]
    clamped_sum = sum(clamped)
    if clamped_sum > 0 and abs(clamped_sum - target_sum) > 0.001:
        scale = target_sum / clamped_sum
        clamped = [p * scale for p in clamped]

    return clamped


def _did_bet_win(finish_text: str, market: str,
                 all_finish_texts: list[str] = None) -> dict:
    """
    Check if a bet won given the player's finish and market.

    Returns dict with hit, fraction, is_push from unified scoring module.
    """
    return determine_outcome_from_text(finish_text, market, all_finish_texts)


def _american_to_payout(price: int, wager: float = 1.0) -> float:
    """Convert American odds to payout on a wager (including stake)."""
    if price > 0:
        return wager * (1 + price / 100)
    elif price < 0:
        return wager * (1 + 100 / abs(price))
    return wager


def _american_to_implied(price: int) -> float:
    """Convert American odds to implied probability."""
    if price > 0:
        return 100 / (price + 100)
    elif price < 0:
        return abs(price) / (abs(price) + 100)
    return 0.5


def replay_event(event_id: str, year: int,
                 strategy: StrategyConfig) -> list[dict]:
    """
    Replay a single historical event with the given strategy.

    Returns list of bet dicts: {player, market, model_prob, odds, ev, won, payout, clv}
    """
    conn = db.get_conn()
    weights = strategy.normalized_weights()

    # 1. Get PIT stats for all players in this event
    pit_rows = conn.execute("""
        SELECT player_key, sg_total, sg_ott, sg_app, sg_arg, sg_putt, sg_t2g, rounds_used
        FROM pit_rolling_stats
        WHERE event_id = ? AND year = ? AND window = ?
    """, (str(event_id), year, strategy.stat_window)).fetchall()

    if not pit_rows:
        return []

    players = []
    scores = []
    for row in pit_rows:
        pkey = row[0]
        pit = {
            "sg_total": row[1], "sg_ott": row[2], "sg_app": row[3],
            "sg_arg": row[4], "sg_putt": row[5], "sg_t2g": row[6],
            "rounds_used": row[7],
        }
        cs = _compute_composite(pit, weights)
        players.append({"player_key": pkey, "pit": pit, "composite": cs})
        scores.append(cs)

    # 2. Convert to probabilities per market
    market_targets = {
        "win": 1.0, "top_5": 5.0, "top_10": 10.0,
        "top_20": 20.0, "make_cut": len(players) * 0.65,
    }

    # 3. Get historical odds for this event
    odds_rows = conn.execute("""
        SELECT player_dg_id, player_name, market, book, close_line
        FROM historical_odds
        WHERE event_id = ? AND year = ?
    """, (str(event_id), year)).fetchall()

    # Build odds lookup: {player_key: {market: best_odds_price}}
    # NOTE: Historical odds are DG model prices (synthetic), not real
    # sportsbook odds. We apply a vig spread to simulate real market
    # conditions (+12% overround), making the backtested odds shorter
    # and the resulting ROI more realistic.
    VIG_FACTOR = 0.88  # Simulate ~12% overround (real books have 10-20%)

    odds_by_player = {}
    for row in odds_rows:
        dg_id, name, market, book, close_line = row
        pkey = normalize_name(name)
        if pkey not in odds_by_player:
            odds_by_player[pkey] = {}

        if close_line is not None:
            # Apply vig: convert to implied prob, increase by vig, convert back
            implied = _american_to_implied(close_line)
            vigged_implied = min(0.95, implied / VIG_FACTOR)
            # Convert back to American odds (shorter/worse for the bettor)
            if vigged_implied >= 0.5:
                vigged_price = int(-100 * vigged_implied / (1 - vigged_implied))
            else:
                vigged_price = int(100 * (1 - vigged_implied) / vigged_implied)

            existing = odds_by_player[pkey].get(market)
            if existing is None or vigged_price > existing:
                odds_by_player[pkey][market] = vigged_price

    # 4. Get actual results
    results = conn.execute("""
        SELECT DISTINCT player_key, fin_text
        FROM rounds
        WHERE event_id = ? AND year = ?
    """, (str(event_id), year)).fetchall()
    finish_by_key = {r[0]: r[1] for r in results if r[0] and r[1]}
    # Collect all finish texts for dead-heat detection
    all_finish_texts = [r[1] for r in results if r[0] and r[1]]

    # 5. Find value bets and evaluate
    bets = []
    for market in strategy.markets:
        target = market_targets.get(market, 1.0)
        # Use market-specific temperature for consistency with live model
        temp = MARKET_SOFTMAX_TEMPS.get(market, strategy.softmax_temp)
        probs = _softmax_probs(scores, temp, target)

        for i, p in enumerate(players):
            pkey = p["player_key"]
            model_prob = probs[i]

            if model_prob < strategy.min_model_prob:
                continue

            player_odds = odds_by_player.get(pkey, {})
            price = player_odds.get(market)
            if price is None:
                continue

            implied_prob = _american_to_implied(price)
            if implied_prob > strategy.max_implied_prob:
                continue

            # True EV: how much we expect to win per dollar wagered
            # EV = (model_prob / implied_prob) - 1.0
            # e.g., model=10%, market=5% → EV = 2.0 - 1.0 = +100%
            if implied_prob > 0:
                ev = (model_prob / implied_prob) - 1.0
            else:
                continue

            if ev < strategy.min_ev:
                continue

            # Kelly criterion: f* = (b*p - q) / b
            # where b = net decimal odds, p = model_prob, q = 1 - model_prob
            odds_decimal_net = (1.0 / implied_prob) - 1.0 if implied_prob < 1 else 0
            if odds_decimal_net > 0:
                kelly_full = (odds_decimal_net * model_prob - (1 - model_prob)) / odds_decimal_net
                kelly = max(0, kelly_full)
                wager = max(0.01, min(0.05, kelly * strategy.kelly_fraction))
            else:
                wager = 0.01

            # Check outcome using unified scoring (dead-heat aware)
            fin_text = finish_by_key.get(pkey, "")
            outcome = _did_bet_win(fin_text, market, all_finish_texts)
            won = outcome["hit"] == 1
            fraction = outcome["fraction"]
            is_push = outcome["is_push"]

            # Compute payout with dead-heat and push handling
            odds_dec = american_to_decimal(price)
            if odds_dec is not None:
                profit = compute_profit(
                    outcome["hit"], fraction, is_push, odds_dec, wager
                )
                payout = wager + profit  # total return
            else:
                profit = -wager
                payout = 0.0

            bets.append({
                "event_id": event_id,
                "year": year,
                "player_key": pkey,
                "market": market,
                "model_prob": round(model_prob, 4),
                "implied_prob": round(implied_prob, 4),
                "ev": round(ev, 4),
                "prob_edge": round(model_prob - implied_prob, 4),
                "odds": price,
                "wager": round(wager, 4),
                "won": won,
                "fraction": round(fraction, 4),
                "is_push": is_push,
                "payout": round(max(0, payout), 4),
                "clv": round(model_prob - implied_prob, 4),
                "finish": fin_text,
            })

    return bets


def simulate_strategy(strategy: StrategyConfig,
                      years: list[int] = None,
                      tour: str = "pga",
                      max_events: int = None) -> SimulationResult:
    """
    Run a full strategy simulation across historical events.

    Replays each event in chronological order, accumulates bets,
    and computes performance metrics.
    """
    if years is None:
        years = [2024, 2025]

    conn = db.get_conn()
    result = SimulationResult(strategy=strategy)

    for year in years:
        events = conn.execute("""
            SELECT DISTINCT event_id
            FROM pit_rolling_stats
            WHERE year = ?
        """, (year,)).fetchall()

        event_ids = [e[0] for e in events if e[0]]
        if max_events:
            event_ids = event_ids[:max_events]

        for eid in event_ids:
            try:
                bets = replay_event(eid, year, strategy)
                result.bet_details.extend(bets)
                result.events_simulated += 1
                result.event_results.append({
                    "event_id": eid,
                    "year": year,
                    "bets": len(bets),
                    "wins": sum(1 for b in bets if b.get("won")),
                })
            except Exception as e:
                result.errors.append(f"{eid}/{year}: {e}")
                logger.warning("Replay failed for %s/%s: %s", eid, year, e)

    result.compute_metrics()
    return result


def walk_forward_validate(strategy: StrategyConfig,
                          train_years: list[int] = None,
                          test_years: list[int] = None,
                          tour: str = "pga") -> dict:
    """
    Walk-forward validation: train on earlier years, test on later years.

    Default split:
      - Train: 2019-2023 (for understanding what the strategy would have done)
      - Test: 2024-2025 (out-of-sample evaluation)

    Returns dict with separate metrics for train and test periods,
    plus a combined summary.
    """
    if train_years is None:
        train_years = [2022, 2023]
    if test_years is None:
        test_years = [2024, 2025]

    train_result = simulate_strategy(strategy, years=train_years, tour=tour)
    test_result = simulate_strategy(strategy, years=test_years, tour=tour)

    # Degradation check: how much worse is out-of-sample?
    train_roi = train_result.roi_pct
    test_roi = test_result.roi_pct
    degradation = train_roi - test_roi if train_roi and test_roi else None

    return {
        "train": {
            "years": train_years,
            "roi_pct": train_result.roi_pct,
            "total_bets": train_result.total_bets,
            "sharpe": train_result.sharpe,
            "events": train_result.events_simulated,
            "wins": train_result.wins,
            "calibration_error": train_result.calibration_error,
        },
        "test": {
            "years": test_years,
            "roi_pct": test_result.roi_pct,
            "total_bets": test_result.total_bets,
            "sharpe": test_result.sharpe,
            "events": test_result.events_simulated,
            "wins": test_result.wins,
            "calibration_error": test_result.calibration_error,
        },
        "degradation_pct": round(degradation, 2) if degradation is not None else None,
        "is_robust": degradation is not None and degradation < 20.0 and test_roi > 0,
        "test_result": test_result,
        "train_result": train_result,
    }
