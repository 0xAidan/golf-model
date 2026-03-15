# Research Report: Safe Deployment, Cold Start, Go-Live Criteria & Background Worker Safety

**Compiled:** 2026-02-28
**Scope:** Rollback/feature flags for ML, cold start bootstrap, go-live criteria, background worker deployment safety
**Purpose:** Concrete implementation patterns for safely deploying and evolving a self-improving golf betting model

---

## Table of Contents

1. [Rollback & Feature Flag Strategies for ML Prediction Systems](#1-rollback--feature-flag-strategies-for-ml-prediction-systems)
2. [Cold Start / Bootstrap Period for Betting Models](#2-cold-start--bootstrap-period-for-betting-models)
3. [Go-Live Criteria for Betting Systems](#3-go-live-criteria-for-betting-systems)
4. [Background Workers & Deployment Conflicts](#4-background-workers--deployment-conflicts)
5. [Synthesis: Implementation Checklist for Our Golf Model](#5-synthesis-implementation-checklist-for-our-golf-model)

---

## 1. Rollback & Feature Flag Strategies for ML Prediction Systems

### 1.1 Why ML Prediction Systems Need Special Deployment Safety

Unlike traditional software where bugs cause crashes, ML models **fail silently** — they serve confident predictions that are completely wrong. This makes rollback and feature flag patterns critical for prediction systems.

**Core failure modes requiring instant rollback:**
- Data drift causing unexpected behavior (new season, course changes)
- Feature pipeline changes breaking model inputs
- Prediction accuracy drops after deployment
- Memory/resource consumption spikes
- Latency exceeding acceptable thresholds

> **Key Insight:** Progressive delivery with feature flags cuts production incidents by 70-90% (DesignRevision, 2026). Every AI feature should have a kill switch.

**Sources:**
- OneUpTime, "How to Implement Model Rollback" (2026)
- Uber Engineering, "Raising the Bar on ML Model Deployment Safety"
- AWS Well-Architected ML Lens, MLREL04-BP02
- Zen Van Riel, "Feature Flagging for AI: Ship AI Features Safely" (2026)
- DesignRevision, "Feature Flags Best Practices: Complete Guide" (2026)

---

### 1.2 Feature Flag Patterns for Prediction Systems

These are NOT web UX feature flags — these control which model version produces predictions, what confidence thresholds trigger bets, and whether the system operates in shadow or live mode.

#### Pattern 1: Kill Switches

The most basic and most essential pattern. Every prediction feature gets a boolean flag that can be flipped without code deployment.

```python
# config/feature_flags.yaml
flags:
  model_predictions_enabled: true
  live_betting_enabled: false       # Master kill switch for real money
  shadow_mode_enabled: true         # Log predictions without acting
  research_agents_enabled: true     # Background data collection
  auto_calibration_enabled: false   # Self-improving feedback loop
```

```python
# In the prediction pipeline
def generate_predictions(tournament_data: dict) -> PredictionReport:
    flags = load_feature_flags()
    
    if not flags["model_predictions_enabled"]:
        return PredictionReport.empty(reason="predictions_disabled")
    
    predictions = model.predict(tournament_data)
    
    if flags["shadow_mode_enabled"]:
        log_shadow_predictions(predictions)
        return PredictionReport.shadow(predictions)
    
    if flags["live_betting_enabled"]:
        return PredictionReport.live(predictions)
    
    return PredictionReport.display_only(predictions)
```

**Best practices:**
- Kill switches must be flippable without deployment (YAML/JSON config file or environment variable)
- Test kill switches regularly — flip them in staging weekly
- Default to OFF (safe) when flag service is unavailable

#### Pattern 2: Configuration-Driven Model Selection

Switch between model versions at runtime without code changes using a model registry pattern.

```python
# config/model_config.yaml
active_model:
  name: "golf_predictor"
  version: "v2.3.1"
  artifact_path: "models/golf_predictor_v2.3.1.pkl"
  
fallback_model:
  name: "golf_predictor"
  version: "v2.2.0"
  artifact_path: "models/golf_predictor_v2.2.0.pkl"

shadow_model:  # Runs in parallel, predictions logged but not used
  name: "golf_predictor"  
  version: "v3.0.0-beta"
  artifact_path: "models/golf_predictor_v3.0.0_beta.pkl"
  enabled: true
```

```python
class ModelRegistry:
    """Lightweight model registry — no MLflow dependency needed."""
    _registry: dict[str, Any] = {}
    
    @classmethod
    def register(cls, name: str, version: str):
        def decorator(model_cls):
            key = f"{name}:{version}"
            cls._registry[key] = model_cls
            return model_cls
        return decorator
    
    @classmethod
    def get_model(cls, name: str, version: str, **kwargs):
        key = f"{name}:{version}"
        if key not in cls._registry:
            raise ValueError(f"Model {key} not found in registry")
        return cls._registry[key](**kwargs)
    
    @classmethod
    def load_from_config(cls, config_path: str = "config/model_config.yaml"):
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        active = config["active_model"]
        return cls.get_model(active["name"], active["version"])
```

**Sources:**
- Abhik Sarkar, "Dynamically Loading Models: A Guide to Model Registry Patterns" (2024)
- OpenMMLab decorator-based registry pattern
- LaunchDarkly, "Upgrade OpenAI models in Python FastAPI applications" (2026)

#### Pattern 3: Shadow / Canary Deployment

Run the new model in parallel with production. New model predictions are logged but never acted upon until validated.

```python
class ShadowDeployment:
    """Run new model alongside production, compare outputs."""
    
    def __init__(self, production_model, shadow_model, metrics_logger):
        self.production = production_model
        self.shadow = shadow_model
        self.logger = metrics_logger
    
    def predict(self, features: dict) -> PredictionResult:
        prod_result = self.production.predict(features)
        
        try:
            shadow_result = self.shadow.predict(features)
            self.logger.log_comparison(
                tournament=features.get("tournament"),
                production_pred=prod_result,
                shadow_pred=shadow_result,
                timestamp=datetime.utcnow()
            )
        except Exception as e:
            self.logger.log_shadow_error(str(e))
        
        return prod_result  # Always return production result
```

**Canary progression schedule:**

| Stage | Traffic to New Model | Duration | Gate Criteria |
|-------|---------------------|----------|---------------|
| Shadow | 0% (log only) | 2-3 tournaments | No errors, predictions within expected range |
| Canary | 10% of display output | 2 tournaments | Calibration within 5% of production |
| Expanded | 50% | 2 tournaments | CLV and Brier Score match or beat production |
| Full rollout | 100% | Ongoing | All metrics stable for 4+ tournaments |

#### Pattern 4: Percentage Rollouts with Consistent Assignment

For systems with multiple users or multiple bet types, gradually shift traffic.

```python
import hashlib

def get_model_variant(entity_id: str, rollout_pct: int = 10) -> str:
    """Deterministic assignment — same entity always gets same variant."""
    hash_val = int(hashlib.md5(entity_id.encode()).hexdigest(), 16)
    if (hash_val % 100) < rollout_pct:
        return "new_model"
    return "production_model"
```

---

### 1.3 Model Versioning for Simultaneous Execution

**Concrete versioning scheme for our system:**

```
models/
├── golf_predictor_v2.2.0.pkl        # Previous stable
├── golf_predictor_v2.3.1.pkl        # Current production
├── golf_predictor_v3.0.0_beta.pkl   # Shadow candidate
└── registry.json                     # Version metadata
```

```json
// registry.json
{
  "models": {
    "golf_predictor:v2.3.1": {
      "status": "production",
      "deployed_at": "2026-02-20T10:00:00Z",
      "training_data_cutoff": "2026-02-15",
      "metrics": {
        "brier_score": 0.218,
        "log_loss": 0.641,
        "calibration_error": 0.012
      },
      "artifact_path": "models/golf_predictor_v2.3.1.pkl"
    },
    "golf_predictor:v2.2.0": {
      "status": "fallback",
      "deployed_at": "2026-01-15T10:00:00Z",
      "metrics": {
        "brier_score": 0.225,
        "log_loss": 0.658,
        "calibration_error": 0.018
      },
      "artifact_path": "models/golf_predictor_v2.2.0.pkl"
    },
    "golf_predictor:v3.0.0-beta": {
      "status": "shadow",
      "deployed_at": null,
      "metrics": {},
      "artifact_path": "models/golf_predictor_v3.0.0_beta.pkl"
    }
  },
  "active_version": "golf_predictor:v2.3.1",
  "fallback_version": "golf_predictor:v2.2.0"
}
```

**Rollback is a config change, not a code deployment:**

```python
def rollback_to_fallback():
    """Instant rollback — swap active version in registry."""
    import json
    with open("models/registry.json", "r+") as f:
        registry = json.load(f)
        current = registry["active_version"]
        fallback = registry["fallback_version"]
        
        registry["models"][current]["status"] = "rolled_back"
        registry["models"][fallback]["status"] = "production"
        registry["active_version"] = fallback
        
        f.seek(0)
        json.dump(registry, f, indent=2)
        f.truncate()
    
    # Log the rollback event
    logger.critical(f"ROLLBACK: {current} -> {fallback}")
```

---

### 1.4 Automatic Rollback Triggers

Define concrete thresholds that trigger automatic rollback without human intervention:

```python
ROLLBACK_TRIGGERS = {
    "prediction_error_rate": {
        "threshold": 0.05,       # >5% of predictions throw errors
        "window_minutes": 30,
        "action": "immediate_rollback"
    },
    "calibration_drift": {
        "threshold": 0.03,       # ECE increases by >3% vs baseline
        "window_tournaments": 3,
        "action": "alert_then_rollback"
    },
    "prediction_latency_p99": {
        "threshold_ms": 5000,    # p99 latency > 5 seconds
        "window_minutes": 15,
        "action": "immediate_rollback"
    },
    "brier_score_degradation": {
        "threshold": 0.015,      # Brier score worsens by >0.015
        "window_tournaments": 5,
        "action": "alert_then_rollback"
    }
}
```

**Flag lifecycle management:**
- Remove feature flags within **30 days** of reaching 100% rollout
- Maintain fewer than **20-30 active flags** per service
- Every flag must have a documented owner and planned removal date

---

## 2. Cold Start / Bootstrap Period for Betting Models

### 2.1 The Core Problem

For the first 5-10 tournaments, the golf model has:
- No historical calibration data from its own predictions
- No CLV tracking history
- No Brier Score / Log Loss baseline from live predictions
- No feedback loop data for self-improvement
- No empirical confidence in the model's edge

This is the **cold start problem** — the model can produce predictions, but there's no evidence yet that those predictions are valuable.

**Sources:**
- MDPI Mathematics, "Bayesian Model Selection for Addressing Cold-Start Problems in Partitioned Time Series Prediction" (2024)
- ArXiv 2602.15012, "Cold-Start Personalization via Training-Free Priors from Structured World Models" (2025)
- ArXiv 2405.02412, Transfer Learning for Sports Forecasting
- SciLit, "Uncertainty-Aware Machine Learning for NBA Forecasting in Digital Betting Markets"

---

### 2.2 What To Do During the Bootstrap Period

#### Phase 0: Pre-Launch (Before First Tournament)

**Backtest thoroughly before generating any predictions:**
- Run the model against **at least 2 full seasons** (50+ tournaments) of historical data
- Use strict chronological walk-forward validation — never peek at future data
- Calculate baseline metrics on historical data:
  - Brier Score target: < 0.25 (must beat naive 50/50 baseline)
  - Log Loss target: < 0.693 (must beat constant 50% prediction)
  - Calibration Error (ECE) target: < 0.015

```python
# Pre-launch validation gate
PRE_LAUNCH_REQUIREMENTS = {
    "backtest_tournaments": 50,        # Minimum tournaments in backtest
    "backtest_brier_score": 0.245,     # Must be below this
    "backtest_log_loss": 0.685,        # Must be below this
    "backtest_ece": 0.020,             # Must be below this
    "walk_forward_windows": 10,        # Minimum walk-forward windows
    "parameter_robustness_pct": 0.20,  # ±20% parameter variation still works
}
```

#### Phase 1: Shadow Mode (Tournaments 1-5)

**Generate predictions but take ZERO action. Log everything.**

```python
class BootstrapPhase:
    SHADOW = "shadow"           # Tournaments 1-5: predict only, no bets
    PAPER_TRADING = "paper"     # Tournaments 6-15: track hypothetical bets
    CAUTIOUS_LIVE = "cautious"  # Tournaments 16-25: small real stakes
    FULL_LIVE = "live"          # Tournament 26+: full Kelly fractions
    
    @staticmethod
    def get_phase(tournaments_completed: int) -> str:
        if tournaments_completed < 5:
            return BootstrapPhase.SHADOW
        elif tournaments_completed < 15:
            return BootstrapPhase.PAPER_TRADING
        elif tournaments_completed < 25:
            return BootstrapPhase.CAUTIOUS_LIVE
        return BootstrapPhase.FULL_LIVE
```

What to track during shadow mode:
- Every prediction the model generates
- Closing lines at bet close (for CLV calculation after the fact)
- Actual tournament outcomes
- Model confidence vs. actual results (calibration curve data)

#### Phase 2: Paper Trading (Tournaments 6-15)

**Simulate betting without real money. Track hypothetical P&L.**

```python
class PaperTradingTracker:
    def __init__(self, starting_bankroll: float = 10000.0):
        self.bankroll = starting_bankroll
        self.bets: list[dict] = []
        self.results: list[dict] = []
    
    def place_paper_bet(self, prediction: dict, odds: float, edge: float):
        """Record a hypothetical bet without risking capital."""
        stake = self.calculate_kelly_stake(edge, odds) * 0.25  # Quarter Kelly
        self.bets.append({
            "tournament": prediction["tournament"],
            "player": prediction["player"],
            "market": prediction["market"],
            "model_prob": prediction["probability"],
            "odds": odds,
            "edge_pct": edge * 100,
            "hypothetical_stake": stake,
            "timestamp": datetime.utcnow(),
        })
    
    def record_outcome(self, bet_id: str, won: bool):
        """Record the result and update paper P&L."""
        bet = self.bets[bet_id]
        pnl = bet["hypothetical_stake"] * (bet["odds"] - 1) if won else -bet["hypothetical_stake"]
        self.results.append({"bet_id": bet_id, "won": won, "pnl": pnl})
```

**Minimum paper trading metrics before considering live:**

| Metric | Threshold | Why |
|--------|-----------|-----|
| Paper bets placed | ≥ 100 | Minimum for any statistical significance |
| CLV% (avg) | > 1% negative (beating close) | Proves model finds value pre-close |
| Brier Score | < 0.240 | Better than naive baselines |
| Calibration Error | < 0.015 | Probabilities are trustworthy |
| Win rate at -110 | > 52.4% | Breakeven rate for standard vig |
| Hypothetical ROI | > 0% | Net positive on paper |
| Max drawdown | < 20% of paper bankroll | Risk management works |
| Consecutive losing days | < 15 | Not systematically broken |

---

### 2.3 Prior Selection for Bayesian Components

When the model has no calibration data, Bayesian priors provide the initial beliefs that the model refines with data. Getting these right is critical.

#### DO: Use Weakly Informative Priors

Weakly informative priors embed just enough domain knowledge to prevent absurd predictions while letting data dominate as it accumulates.

```python
# For a golf model's player skill parameter
# We know PGA Tour scoring is roughly N(70, 3)
# A weakly informative prior on skill adjustment:
player_skill_prior = {
    "distribution": "normal",
    "mean": 0.0,        # No prior belief about above/below average
    "std": 2.0,         # Allows ±4 strokes from mean (covers ~95% of PGA range)
}

# For course difficulty adjustment
course_difficulty_prior = {
    "distribution": "normal",
    "mean": 0.0,        # No prior belief about easy/hard
    "std": 3.0,         # Courses vary ~±6 strokes from par historically
}
```

#### DON'T: Use Flat/Uninformative Priors

Stan documentation explicitly warns: "uninformative is usually unwarranted and unrealistic (flat is frequently frivolous and fictional)."

A Gamma(0.5, 0.00001) "reference prior" for scoring rates generates 95% of prior mass on outcomes never seen in sports history — simulating 100+ point score differentials.

#### Prior Predictive Checks

Before fitting to any data, simulate from your priors and verify the generated predictions are plausible:

```python
import numpy as np

def prior_predictive_check(n_simulations: int = 10000) -> dict:
    """Simulate tournament outcomes from priors only. 
    Verify results are plausible before touching any data."""
    
    simulated_scores = []
    for _ in range(n_simulations):
        # Sample from priors
        skill = np.random.normal(0.0, 2.0)
        course = np.random.normal(0.0, 3.0)
        noise = np.random.normal(0.0, 1.5)
        
        # Generate a 4-round tournament score relative to par
        round_score = 70 + skill + course + noise
        simulated_scores.append(round_score * 4)
    
    scores = np.array(simulated_scores)
    return {
        "mean": np.mean(scores),
        "std": np.std(scores),
        "min": np.min(scores),
        "max": np.max(scores),
        "pct_below_240": np.mean(scores < 240),  # Should be very rare
        "pct_above_320": np.mean(scores > 320),   # Should be very rare
    }
    # VERIFY: mean ≈ 280, std ≈ 15-20, no scores below 230 or above 340
```

**Sources:**
- Number Analytics, "Weakly Informative Priors: A Practical Guide" (2025)
- Stan Documentation, "Prior Predictive Checks" (Section 26.5)
- rstanarm documentation, "Prior Distributions for rstanarm Models"
- Andrew Gelman, Stan case study on golf putting model
- DataGolf, "A Predictive Model of Tournament Outcomes on the PGA Tour"

---

### 2.4 Transfer Learning During Cold Start

Even with no predictions from YOUR model, you can bootstrap using domain knowledge:

1. **Import DataGolf baseline predictions** — Use their projections as your initial prior, then measure how much your model deviates over time
2. **Historical scoring distributions** — PGA Tour scoring averages by player, course, and era are well-documented
3. **Strokes Gained baselines** — SG:OTT, SG:APP, SG:ATG, SG:P all have known population distributions
4. **Market-implied probabilities** — Use sportsbook odds as a "wisdom of the crowd" prior; your model's edge is measured against this baseline

```python
# Bootstrap calibration from market
def bootstrap_from_market(market_odds: dict, model_predictions: dict) -> dict:
    """Use market as initial calibration reference during cold start."""
    market_probs = {k: 1/v for k, v in market_odds.items()}
    # Normalize to sum to 1
    total = sum(market_probs.values())
    market_probs = {k: v/total for k, v in market_probs.items()}
    
    # Log divergence from market as initial calibration signal
    divergences = {}
    for player, model_prob in model_predictions.items():
        if player in market_probs:
            divergences[player] = model_prob - market_probs[player]
    
    return {
        "avg_divergence": np.mean(list(divergences.values())),
        "max_divergence": max(divergences.values(), key=abs),
        "correlation": np.corrcoef(
            [model_predictions[p] for p in divergences],
            [market_probs[p] for p in divergences]
        )[0, 1]
    }
```

---

## 3. Go-Live Criteria for Betting Systems

### 3.1 The 4-Stage Framework

Professional quantitative systems follow a structured progression before deploying real capital:

| Stage | Data Source | Broker | Duration | Purpose |
|-------|-----------|--------|----------|---------|
| 1. Backtesting | Historical | Simulated | 2+ seasons | Prove hypothesis |
| 2. Forward Testing | Live | Simulated | 5 tournaments | Validate on unseen data |
| 3. Paper Trading | Live | Demo/Paper | 10+ tournaments | Validate execution & psychology |
| 4. Live Trading | Live | Real | Ongoing | Generate returns |

> **Critical statistic:** Only 5% of backtested strategies survive complete validation to reach live trading. Over 90% of strategies that work in backtests fail with real capital. (AlgoStrategyAnalyzer, 2026)

**Sources:**
- Alpaca Markets, "Paper Trading vs. Live Trading: A Data-Backed Guide" (2026)
- Surmount, "From Signal to Execution: Turning a Quant Thesis into Live Strategy"
- Roboquant, "The 4 Stages"
- AlgoStrategyAnalyzer, "Complete Guide to Validate a Trading Strategy" (2026)
- Microsoft, "ML Model Production Checklist"
- The Next Tick, "Algorithm Testing Methodology"

---

### 3.2 Go-Live Metrics Checklist

Before transitioning from paper to real money, ALL of the following must pass:

#### Tier 1: Hard Gates (Must Pass — No Exceptions)

```python
GO_LIVE_HARD_GATES = {
    # Model Quality
    "paper_trading_tournaments": {
        "minimum": 10,
        "description": "Minimum tournaments with paper predictions tracked"
    },
    "paper_bets_placed": {
        "minimum": 100,
        "description": "Minimum paper bets with recorded outcomes"
    },
    "brier_score_live": {
        "maximum": 0.240,
        "description": "Brier score on live (not backtest) predictions"
    },
    "calibration_error": {
        "maximum": 0.015,
        "description": "Expected Calibration Error on live predictions"
    },
    "log_loss_vs_market": {
        "must_beat": True,
        "description": "Model log loss must be lower than market-implied log loss"
    },
    
    # Edge Verification
    "clv_positive": {
        "minimum_pct": 1.0,
        "description": "Average CLV must exceed 1% (beating closing line)"
    },
    "clv_hit_rate": {
        "minimum_pct": 55.0,
        "description": "Must beat closing line on >55% of bets"
    },
    
    # Risk Management
    "max_drawdown_paper": {
        "maximum_pct": 20.0,
        "description": "Maximum drawdown during paper trading < 20%"
    },
    "paper_roi": {
        "minimum_pct": 0.0,
        "description": "Paper trading ROI must be positive"
    },
    
    # Infrastructure
    "model_rollback_tested": {
        "required": True,
        "description": "Rollback has been tested and works in < 60 seconds"
    },
    "kill_switch_tested": {
        "required": True,
        "description": "Kill switch has been tested and disables betting instantly"
    },
}
```

#### Tier 2: Soft Gates (Strong Recommendations)

```python
GO_LIVE_SOFT_GATES = {
    "paper_trading_months": {
        "recommended": 3,
        "description": "Months of paper trading data"
    },
    "paper_bets_statistical_power": {
        "recommended": 250,
        "description": "250+ bets for robust statistical significance"
    },
    "parameter_robustness": {
        "variation_pct": 20,
        "description": "Model performs with ±20% parameter variation"
    },
    "multiple_market_types_tested": {
        "recommended": True,
        "description": "Tested across outrights, top-10, top-20, matchups"
    },
    "correlation_with_sharp_books": {
        "minimum": 0.85,
        "description": "Model predictions correlate >85% with sharp book lines"
    },
}
```

---

### 3.3 CLV as Primary Go-Live Signal

Closing Line Value is the **single most important metric** for determining if a sports betting model has real edge.

**How to calculate CLV:**

```python
def calculate_clv(placed_odds: float, closing_odds: float) -> float:
    """Calculate CLV percentage.
    
    Negative CLV% = you beat the close (GOOD).
    Example: placed at +200, closed at +180 → you got better odds.
    """
    placed_implied = 1.0 / placed_odds  # Decimal odds
    closing_implied = 1.0 / closing_odds
    
    # Remove vig from closing line for fair comparison
    # (Use pinnacle or trimmed mean of sharp books)
    closing_no_vig = remove_vig(closing_implied)
    
    raw_clv = (closing_no_vig / placed_implied) - 1.0
    return raw_clv  # Negative = you beat the market
```

**Go-live CLV thresholds:**

| Metric | Threshold | Sample Size | Significance |
|--------|-----------|-------------|-------------|
| Average Raw CLV% | > 1-2% beating close | 250+ bets | Strong signal of edge |
| CLV Hit Rate | > 55% | 250+ bets | Consistent market-beating |
| CLV by market segment | Positive in ≥2 segments | 50+ per segment | Not dependent on one market |
| Rolling 100-bet CLV | Stays positive | Ongoing | No regime decay |

**Interpretation matrix:**

| CLV | ROI | Interpretation | Action |
|-----|-----|---------------|--------|
| Positive | Positive | Real edge, running well | Continue / increase stakes |
| Positive | Negative | Real edge, running bad (variance) | Stick with strategy, maintain stakes |
| Negative | Positive | No edge, running hot (lucky) | DO NOT increase stakes — reduce or stop |
| Negative | Negative | No edge, expected outcome | Stop betting, retrain model |

> **Key Insight from WagerProof research:** A 5% yield over 250 bets at 2.00 odds has a 21.5% chance of being skill-based. The same 5% yield over 2,500 bets has less than 1% chance of being pure luck. Sample size is everything.

**Sources:**
- Sports-AI.dev, "Closing Line Value (CLV): Measuring AI Model Performance in Sports Betting"
- WagerProof, "5 Metrics To Validate Betting Models With CLV"
- DRatings, uncertainty quantification methodologies
- Joseph Buchdahl (betting analyst), sample size significance research

---

### 3.4 The 5 Validation Metrics (in Priority Order)

Based on WagerProof's comprehensive analysis, these 5 metrics together determine model readiness:

| # | Metric | What It Measures | Go-Live Threshold | Sample Size Needed |
|---|--------|-----------------|-------------------|--------------------|
| 1 | **CLV** | Edge over market | >1% avg CLV, >55% hit rate | 250-1,000 bets |
| 2 | **Log Loss** | Penalizes overconfidence | Must beat closing line log loss | 1,000+ predictions |
| 3 | **Brier Score** | Probability calibration | < 0.240, BSS > 0 | 1,000+ predictions |
| 4 | **ROI** | Actual profitability | > 0% (positive) | 250+ bets (but luck-sensitive) |
| 5 | **Win Rate** | Consistency | > 52.4% at -110 | 250+ bets |

**Critical finding:** Models selected using calibration metrics (Log Loss, Brier Score) achieved average ROI of **+34.69%**, while models chosen by simple accuracy achieved average ROI of **-35.17%**. Calibration is everything.

> **Recalibration trigger:** If Expected Calibration Error exceeds 0.015, apply Platt Scaling or isotonic regression before going live.

---

### 3.5 Cautious Go-Live: The Graduated Stake Schedule

Even after passing all gates, start with tiny stakes and scale up:

```python
STAKE_GRADUATION_SCHEDULE = {
    "phase_1": {
        "name": "Micro Stakes",
        "tournaments": "1-5 after go-live",
        "max_bet_pct": 0.25,       # 0.25% of bankroll per bet
        "kelly_fraction": 0.125,   # 1/8 Kelly
        "daily_loss_limit_pct": 2.0,
        "description": "Prove live execution matches paper"
    },
    "phase_2": {
        "name": "Small Stakes",
        "tournaments": "6-15 after go-live",
        "max_bet_pct": 0.50,       # 0.5% of bankroll per bet
        "kelly_fraction": 0.25,    # Quarter Kelly
        "daily_loss_limit_pct": 3.0,
        "description": "Build confidence with real capital"
    },
    "phase_3": {
        "name": "Standard Stakes",
        "tournaments": "16-30 after go-live",
        "max_bet_pct": 1.0,        # 1% of bankroll per bet
        "kelly_fraction": 0.50,    # Half Kelly
        "daily_loss_limit_pct": 5.0,
        "description": "Full model operation"
    },
    "phase_4": {
        "name": "Full Stakes",
        "tournaments": "31+ after go-live",
        "max_bet_pct": 2.0,        # 2% of bankroll per bet
        "kelly_fraction": 0.50,    # Half Kelly (never full Kelly)
        "daily_loss_limit_pct": 5.0,
        "description": "Mature operation, model validated"
    }
}
```

> **Never use full Kelly.** Fractional Kelly (25-50%) is standard practice because parameter estimation error in real models means true edge is always overestimated. Half Kelly reduces growth rate by only 25% but cuts variance by 50%.

---

### 3.6 Transition Timeline

Realistic timeline for the golf model specifically:

| Phase | Calendar Period | Tournaments | Cumulative Bets | Status |
|-------|----------------|-------------|-----------------|--------|
| Backtest | Pre-launch | 50+ historical | 0 live | Validation |
| Shadow Mode | Weeks 1-8 | ~5 tournaments | 0 (logging only) | Cold start |
| Paper Trading | Weeks 9-24 | ~10 tournaments | 100-200 paper | Building evidence |
| Go/No-Go Decision | Week 25 | Review all data | — | Gate check |
| Micro Live | Weeks 26-34 | ~5 tournaments | 30-50 real | Proving execution |
| Scale Up | Weeks 35+ | Ongoing | Growing | Full operation |

**Total time from first prediction to full operation: ~8-9 months (approximately 1 full PGA Tour season).**

---

## 4. Background Workers & Deployment Conflicts

### 4.1 The Problem

The golf model runs multiple autonomous background processes:
- **Research agents** collecting data from DataGolf, sportsbooks, weather APIs
- **Data pipeline workers** processing raw data into features
- **Calibration processes** updating model parameters
- **Prediction generators** creating tournament outputs

During deployments (code updates, model version changes, database migrations), these workers can:
- Write stale data to the database
- Corrupt state during schema migrations
- Hold database locks preventing migrations
- Crash mid-task leaving partial state

---

### 4.2 SQLite Concurrent Writer Safety

Since this project uses SQLite, concurrent write safety is critical.

#### Enable WAL Mode (Non-Negotiable)

```python
import sqlite3

def get_safe_connection(db_path: str) -> sqlite3.Connection:
    """Create a SQLite connection with safe concurrency settings."""
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")       # Write-Ahead Logging
    conn.execute("PRAGMA synchronous=NORMAL;")     # Balance safety & speed
    conn.execute("PRAGMA busy_timeout=30000;")     # 30s wait before failing
    conn.execute("PRAGMA wal_autocheckpoint=1000;") # Checkpoint every 1000 pages
    return conn
```

**What WAL mode does:**
- Writers no longer block readers
- Readers no longer block writers
- Only writer-to-writer conflicts require waiting
- Lock duration is minimal (writes go to a `.wal` file)

**Without WAL mode:** Every write acquires an EXCLUSIVE lock, blocking ALL other access. With background workers + migrations, this guarantees `database is locked` errors.

**Sources:**
- SQLite.org, "File Locking and Concurrency in SQLite Version 3"
- pythontutorials.net, "Concurrent Writing with SQLite3 in Python" (2025)
- Roshan Lamichhane, "SQLite Worker: Supercharge Your SQLite Performance" (Medium)
- Emma Typing, "Using multiprocessing and sqlite3 together"

---

### 4.3 Graceful Worker Shutdown During Deployments

#### Signal Handling Pattern

```python
import signal
import threading

class GracefulWorker:
    """Base class for background workers that shut down cleanly."""
    
    def __init__(self):
        self._shutdown_event = threading.Event()
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
    
    def _handle_shutdown(self, signum, frame):
        """Signal handler — set shutdown flag, let current task finish."""
        logger.info(f"Shutdown signal received ({signum}). Finishing current task...")
        self._shutdown_event.set()
    
    @property
    def should_stop(self) -> bool:
        return self._shutdown_event.is_set()
    
    def run(self):
        """Main worker loop — checks for shutdown between tasks."""
        while not self.should_stop:
            task = self.get_next_task()
            if task is None:
                self._shutdown_event.wait(timeout=60)  # Sleep between polls
                continue
            
            try:
                self.process_task(task)
                self.mark_complete(task)
            except Exception as e:
                self.mark_failed(task, error=str(e))
        
        self.cleanup()
        logger.info("Worker shut down cleanly.")
```

#### Deployment Coordination

```python
import os
import time
from pathlib import Path

DEPLOY_LOCK_FILE = Path("tmp/deploy.lock")

class DeploymentCoordinator:
    """Coordinate between deployments and background workers."""
    
    @staticmethod
    def start_deployment():
        """Signal all workers that a deployment is starting."""
        DEPLOY_LOCK_FILE.parent.mkdir(exist_ok=True)
        DEPLOY_LOCK_FILE.write_text(str(time.time()))
    
    @staticmethod
    def finish_deployment():
        """Signal workers that deployment is complete."""
        DEPLOY_LOCK_FILE.unlink(missing_ok=True)
    
    @staticmethod
    def is_deploying() -> bool:
        """Check if a deployment is in progress."""
        return DEPLOY_LOCK_FILE.exists()
    
    @staticmethod
    def wait_for_workers(timeout_seconds: int = 120) -> bool:
        """Wait for all workers to finish their current tasks."""
        worker_pids_file = Path("tmp/worker_pids.json")
        if not worker_pids_file.exists():
            return True
        
        import json
        pids = json.loads(worker_pids_file.read_text())
        
        start = time.time()
        while time.time() - start < timeout_seconds:
            alive = [pid for pid in pids if _is_process_alive(pid)]
            if not alive:
                return True
            time.sleep(2)
        
        return False  # Workers didn't finish in time


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
```

---

### 4.4 Safe Database Migration Pattern

```python
class SafeMigration:
    """Run database migrations safely with background workers."""
    
    def execute(self, migration_sql: str, db_path: str):
        coordinator = DeploymentCoordinator()
        
        # Step 1: Signal deployment starting
        coordinator.start_deployment()
        
        # Step 2: Wait for workers to finish current tasks
        workers_stopped = coordinator.wait_for_workers(timeout_seconds=120)
        if not workers_stopped:
            coordinator.finish_deployment()
            raise RuntimeError("Workers didn't stop in time. Aborting migration.")
        
        # Step 3: Create backup before migration
        import shutil
        backup_path = f"{db_path}.backup.{int(time.time())}"
        shutil.copy2(db_path, backup_path)
        
        # Step 4: Run migration with exclusive access
        conn = sqlite3.connect(db_path, timeout=60)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.executescript(migration_sql)
            conn.execute("PRAGMA integrity_check;")
            conn.commit()
        except Exception as e:
            conn.rollback()
            # Restore from backup
            shutil.copy2(backup_path, db_path)
            raise RuntimeError(f"Migration failed, restored backup: {e}")
        finally:
            conn.close()
        
        # Step 5: Signal deployment complete
        coordinator.finish_deployment()
        
        # Step 6: Clean up old backup after verification
        # (Keep for 24 hours, then delete)
```

---

### 4.5 Worker-Deployment Interaction Matrix

| Scenario | Risk | Mitigation |
|----------|------|-----------|
| Worker writes during schema migration | Data corruption, crash | Deploy lock file, wait for drain |
| Worker reads stale data after code update | Incorrect predictions | Version-stamped data, worker restart |
| Worker holds DB lock blocking migration | Migration timeout | WAL mode, short transactions, busy timeout |
| Worker crashes during shutdown | Partial state | Idempotent tasks, transaction-per-task |
| Two workers write simultaneously | Lock contention | WAL mode, retry with exponential backoff |
| Migration fails, workers resume | Workers hit new partial schema | Backup + restore before releasing lock |

---

### 4.6 Retry Pattern for Lock Contention

```python
import time
import random
import sqlite3

def execute_with_retry(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple = (),
    max_retries: int = 5,
    base_delay: float = 0.5
) -> sqlite3.Cursor:
    """Execute SQL with exponential backoff retry on lock errors."""
    for attempt in range(max_retries):
        try:
            return conn.execute(sql, params)
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                logger.warning(f"DB locked, retry {attempt+1}/{max_retries} in {delay:.1f}s")
                time.sleep(delay)
            else:
                raise
```

---

## 5. Synthesis: Implementation Checklist for Our Golf Model

### 5.1 Pre-Launch Checklist

```
[ ] Backtest passes on 50+ historical tournaments
[ ] Walk-forward validation across 10+ rolling windows
[ ] Brier Score < 0.245 on backtest data
[ ] Log Loss < 0.685 on backtest data
[ ] ECE < 0.020 on backtest data
[ ] Parameter robustness test passes (±20% variation)
[ ] Prior predictive checks generate plausible outputs
[ ] WAL mode enabled on all SQLite connections
[ ] Kill switch implemented and tested
[ ] Model rollback tested (< 60 second recovery)
[ ] Feature flags config file created and documented
[ ] Graceful shutdown handlers on all background workers
[ ] Deploy lock file mechanism implemented
[ ] Shadow mode infrastructure ready (logging, comparison)
[ ] Paper trading tracker built and tested
```

### 5.2 Shadow Mode Checklist (Tournaments 1-5)

```
[ ] All predictions logged with timestamps
[ ] Closing lines captured for CLV calculation
[ ] Actual outcomes recorded
[ ] Calibration curve data accumulating
[ ] Shadow model comparison running (if testing new version)
[ ] No real bets placed (kill switch verified ON)
[ ] Weekly review of prediction quality
```

### 5.3 Paper Trading Checklist (Tournaments 6-15)

```
[ ] Hypothetical bets recorded with full metadata
[ ] CLV calculated for each paper bet
[ ] Running Brier Score and Log Loss tracked
[ ] Paper P&L tracked with Kelly staking
[ ] Max drawdown monitored
[ ] Calibration error computed per-tournament
[ ] Market segment analysis (outright, top-10, matchups)
```

### 5.4 Go-Live Gate Check (After Tournament 15+)

```
[ ] ≥100 paper bets with outcomes
[ ] Average CLV > 1% (beating closing line)
[ ] CLV hit rate > 55%
[ ] Brier Score < 0.240 on live predictions
[ ] ECE < 0.015
[ ] Log Loss beats market baseline
[ ] Paper ROI positive
[ ] Max drawdown < 20%
[ ] Kill switch tested within last 7 days
[ ] Rollback tested within last 7 days
[ ] All background workers have graceful shutdown
[ ] Deploy coordination tested
```

### 5.5 Post-Go-Live Monitoring

```
[ ] Rolling 50-bet CLV tracked and alerted
[ ] Brier Score monitored per-tournament
[ ] Automatic rollback triggers configured
[ ] Stake graduation schedule followed (1/8 Kelly → 1/4 Kelly → 1/2 Kelly)
[ ] Monthly model performance review scheduled
[ ] Calibration rechecked every 10 tournaments
[ ] Feature flag audit every 30 days
```

---

### 5.6 Key Numbers to Remember

| Parameter | Value | Source |
|-----------|-------|--------|
| Minimum paper bets for significance | 100 (basic), 250 (robust), 1000 (definitive) | WagerProof, Soccerwidow |
| CLV threshold for real edge | >1-2% average, >55% hit rate | Sports-AI.dev |
| Brier Score baseline (unskilled) | 0.250 | WagerProof |
| Log Loss baseline (unskilled) | 0.693 | WagerProof |
| ECE recalibration trigger | > 0.015 | WagerProof |
| Strategies surviving backtest→live | 5% | AlgoStrategyAnalyzer |
| ROI confidence at 250 bets (5% yield) | 21.5% skill probability | Joseph Buchdahl |
| ROI confidence at 2500 bets (5% yield) | <1% luck probability | Joseph Buchdahl |
| Paper trading to live transition | 57% within 30 days, 75% within 60 days | Alpaca Markets |
| Feature flag cleanup window | 30 days after 100% rollout | DesignRevision |
| Max active feature flags | 20-30 per service | DesignRevision |
| SQLite busy timeout recommended | 20-30 seconds | pythontutorials.net |
| Progressive delivery incident reduction | 70-90% | DesignRevision |
| Fractional Kelly recommendation | 25-50% of full Kelly | Industry standard |
| Min backtest tournaments | 50+ (2 full seasons) | The Next Tick |
| Walk-forward out-of-sample | 30% of data | The Next Tick |
| Signal consistency correlation | ≥95% across sources | The Next Tick |
| Realistic slippage modeling | 0.02-0.05% | Signal Pilot |
