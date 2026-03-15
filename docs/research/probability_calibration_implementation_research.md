# Probability Calibration Implementation Research

> Research conducted 2026-02-28. Focused on practical implementation details, pitfalls, and code for a sports betting pipeline with small-sample golf predictions.

---

## Table of Contents

1. [Isotonic Regression for Binary Outcomes in Small Samples](#1-isotonic-regression-for-binary-outcomes-in-small-samples)
2. [Closing Line Value (CLV) Implementation](#2-closing-line-value-clv-implementation)
3. [Empirical Bayes Shrinkage for Golf Predictions](#3-empirical-bayes-shrinkage-for-golf-predictions)
4. [Implementing the Hedge/EWA Algorithm](#4-implementing-the-hedgeewa-algorithm)
5. [ADWIN Drift Detection Practical Usage](#5-adwin-drift-detection-practical-usage)
6. [Fractional Kelly with Confidence Intervals](#6-fractional-kelly-with-confidence-intervals)

---

## 1. Isotonic Regression for Binary Outcomes in Small Samples

### Minimum Sample Size

**Hard threshold: ~1,000 calibration samples for isotonic regression. Below 500, use Platt scaling (sigmoid) instead.**

The scikit-learn documentation recommends isotonic regression only when you have "substantially more than 1000 samples" for calibration. The reasoning: isotonic regression is non-parametric (piecewise constant, monotonically increasing function fitted via the Pool Adjacent Violators Algorithm), so it has many degrees of freedom and can overfit with limited data.

For context on what "enough data" means in sports betting:
- ~1,000 samples gives a **3% margin of error** at 95% confidence for binary probability estimation
- ~882 matches (5 seasons of Swiss Super League) produces predictions within a **3.3% confidence interval**
- For golf specifically, if you're predicting top-10 finishes (~15-20% base rate), you'd need ~300-500 events minimum before isotonic calibration is reliable

### What Goes Wrong at Small N

1. **Step-function artifacts**: Isotonic regression produces discontinuous step functions. With 50-100 calibration points, you get wild jumps between adjacent predicted probabilities (e.g., 0.12 predicted -> 0.08 calibrated, 0.13 predicted -> 0.25 calibrated)
2. **Zero calibration error illusion**: IR achieves zero calibration error on its training set by acting as an adaptive binning procedure. This is meaningless at small N — it's just memorizing the calibration set
3. **Negative probability risk with some methods**: The additive de-vigging approach can produce negative probabilities for longshots; isotonic regression won't fix this if the inputs are garbage

### Cross-Validation Strategy for Calibration

Use `CalibratedClassifierCV` from scikit-learn with proper separation of training and calibration data:

```python
from sklearn.calibration import CalibratedClassifierCV

# METHOD 1: Let sklearn handle the CV splits (recommended for small data)
# Trains base model on each CV training fold, calibrates on test fold
calibrated = CalibratedClassifierCV(
    base_estimator,
    method='isotonic',   # or 'sigmoid' if N < 1000
    cv=5,                # 5-fold CV
    ensemble=True        # average predictions across all folds
)
calibrated.fit(X, y)

# METHOD 2: Pre-fit model, separate calibration set
# Use when you want manual control over the split
base_estimator.fit(X_train, y_train)
calibrated = CalibratedClassifierCV(
    base_estimator,
    method='sigmoid',    # safer for small calibration sets
    cv='prefit'
)
calibrated.fit(X_calibration, y_calibration)  # MUST be disjoint from training
```

**Critical rule**: Training data and calibration data MUST be disjoint. If you calibrate on training data, you get optimistically biased probabilities.

### Recommendation for Golf Pipeline

Given golf's inherently small sample sizes (150-200 players per event, ~40 events/year):

- **Use Platt scaling (sigmoid)** as the default calibration method — it has only 2 parameters (a, b in the sigmoid) and is much more robust at N < 1000
- **Switch to isotonic regression** only when you accumulate 2+ years of out-of-sample predictions (1000+ calibration points)
- **Alternative: Smooth isotonic regression** (combines parametric and non-parametric) for better generalization — available via custom implementation but not in sklearn out of the box

### Pitfalls

| Pitfall | Consequence | Mitigation |
|---------|------------|------------|
| Calibrating on training data | Overconfident probabilities | Always use held-out or CV-based calibration |
| Using isotonic with N < 500 | Overfitting, step-function artifacts | Fall back to Platt scaling |
| Ignoring base rate | Calibration bins with 0-2 samples give meaningless ECE | Use at least 10 bins with ≥30 samples each |
| Not checking calibration curve visually | Can't catch systematic issues | Plot reliability diagrams every time |

---

## 2. Closing Line Value (CLV) Implementation

### The CLV Formula

CLV measures whether you got better odds than the market's final assessment. Using decimal odds:

```python
def calculate_clv(bet_odds_decimal: float, closing_odds_decimal_novig: float) -> float:
    """
    CLV as a percentage.
    Positive = you beat the closing line (good).
    Negative = market moved against you (bad).
    
    bet_odds_decimal: the decimal odds at which you placed the bet
    closing_odds_decimal_novig: the de-vigged closing decimal odds
    """
    return (bet_odds_decimal / closing_odds_decimal_novig) - 1

# Example: bet at 2.20, closing no-vig odds are 2.00
clv = calculate_clv(2.20, 2.00)  # = 0.10 = +10% CLV (excellent)

# Example: bet at 2.20, closing no-vig odds are 2.40
clv = calculate_clv(2.20, 2.40)  # = -0.083 = -8.3% CLV (bad)
```

**Key insight from Joseph Buchdahl**: CLV requires far fewer bets to demonstrate statistical significance than profit/loss analysis. While P&L might need thousands of bets to prove skill, CLV can show significance in as few as **50-65 bets**. This is because CLV varies in small continuous increments (std dev ~0.1) vs binary P&L outcomes (std dev ~1.0).

### CLV Statistical Significance

Per Buchdahl's analysis:
- **50 bets**: Sufficient to detect a consistent 5% CLV edge at statistical significance
- **100-500 bets**: Recommended range for confident CLV analysis depending on edge size
- **1,000 bets at 1.95 odds with +5% yield**: Bayes Factor of 13.7 (strong but not decisive evidence of skill)

### De-Vigging Methods Implementation

You MUST de-vig (remove the bookmaker's margin) before computing CLV. Pinnacle's closing odds are the gold standard benchmark but still contain ~2% vig.

#### Method 1: Multiplicative (simplest, decent baseline)

```python
def devig_multiplicative(odds: list[float]) -> list[float]:
    """Divide each implied prob by the booksum. Simplest method."""
    implied = [1.0 / o for o in odds]
    booksum = sum(implied)
    return [p / booksum for p in implied]
```

#### Method 2: Power Method (recommended by Pinnacle Odds Dropper)

```python
from scipy.optimize import brentq

def devig_power(odds: list[float]) -> list[float]:
    """
    Raise implied probs to power k such that they sum to 1.
    Accounts for favorite-longshot bias.
    Never produces negative probabilities.
    """
    implied = [1.0 / o for o in odds]
    
    def objective(k):
        return sum(p ** k for p in implied) - 1.0
    
    k = brentq(objective, 0.0, 100.0)
    fair_probs = [p ** k for p in implied]
    return fair_probs
```

#### Method 3: Shin Method (academic gold standard)

```python
import shin

# For a 3-outcome market (e.g. Home/Draw/Away)
probs = shin.calculate_implied_probabilities([2.6, 2.4, 4.3])
# [0.373, 0.405, 0.222]

# For a 2-outcome market: equivalent to additive method, analytical solution
probs = shin.calculate_implied_probabilities([1.5, 2.74])
# [0.651, 0.349]

# Full diagnostics
result = shin.calculate_implied_probabilities(
    [2.6, 2.4, 4.3], full_output=True
)
# result.z = 0.017 (estimated insider trading proportion)
# result.iterations = 426
```

For **golf outright markets** (100+ outcomes), Shin's iterative method works but may take more iterations. The `shin` package uses a Rust backend for performance.

#### Method 4: Differential Margin Weighting (Buchdahl's method)

```python
def devig_buchdahl(odds: list[float]) -> list[float]:
    """
    Buchdahl's differential margin weighting.
    Margin applied proportionally to the odds themselves.
    Greater margin on longshots.
    """
    n = len(odds)
    implied = [1.0 / o for o in odds]
    margin = sum(implied) - 1.0
    fair_odds = [n * o / (n - margin * o) for o in odds]
    return [1.0 / fo for fo in fair_odds]
```

#### Using `penaltyblog` for All Methods

```python
import penaltyblog as pb

odds = [2.7, 2.3, 4.4]

# Multiplicative (simplest)
result = pb.implied.calculate_implied(odds, method="multiplicative")

# Power method
result = pb.implied.calculate_implied(odds, method="power")

# Shin method
result = pb.implied.calculate_implied(odds, method="shin")

# Buchdahl's differential margin weighting
result = pb.implied.calculate_implied(odds, method="differential_margin_weighting")

# Odds ratio (Cheung)
result = pb.implied.calculate_implied(odds, method="odds_ratio")

# Logarithmic
result = pb.implied.calculate_implied(odds, method="logarithmic")
```

### Empirical Comparison of De-Vigging Methods

Using 380 EPL 2024/25 matches scored by Ranked Probability Score (lower = better):

| Method | RPS |
|--------|-----|
| Multiplicative | 0.19724 |
| Logarithmic | 0.19730 |
| Odds Ratio | 0.19730 |
| Shin | 0.19731 |
| Additive | 0.19736 |
| Differential Margin Weighting | 0.19736 |
| Power | 0.19739 |

**The differences are negligible in efficient markets.** For golf outrights (less efficient, more outcomes), the choice may matter more. The Power method or Shin method are generally recommended because they handle the favorite-longshot bias inherent in longshot-heavy markets like golf.

### Tracking CLV Without Closing Line Data

When you don't have access to Pinnacle's closing odds:
1. **Use Pinnacle's pre-match odds as a proxy** — Buchdahl confirms these are "good enough"
2. **Track your own implied probability vs market probability at bet time** — this gives you a "model CLV" (how much your model differs from the market)
3. **Use services like Pinnacle Odds Dropper** — they track and store closing odds for you
4. **Record the odds at bet time AND closest-to-close odds** you can capture — even a few hours before close is useful

### Pitfalls

| Pitfall | Consequence | Mitigation |
|---------|------------|------------|
| Computing CLV with vigged odds | Understates true CLV by ~1-2% | Always de-vig before CLV calculation |
| Using soft book closing odds | Unreliable benchmark (not efficiently priced) | Use Pinnacle only |
| Small sample CLV analysis (< 50 bets) | Can't distinguish luck from skill | Wait for 50+ bets minimum |
| Ignoring line movement direction | Miss the signal in steam moves | Track opening → closing direction |

---

## 3. Empirical Bayes Shrinkage for Golf Predictions

### The Core Idea

When you have players with different numbers of rounds, raw strokes gained averages are unreliable for low-sample players. Empirical Bayes shrinks everyone toward the population mean, with the amount of shrinkage inversely proportional to sample size.

### For Binary Outcomes (Win Probability): Beta-Binomial Approach

Following David Robinson's batting average method, applied to golf win probability:

```python
import numpy as np
from scipy.stats import beta as beta_dist
from scipy.optimize import minimize

def fit_beta_prior(successes: np.ndarray, totals: np.ndarray, 
                   min_total: int = 20) -> tuple[float, float]:
    """
    Fit a beta prior from the population data.
    Filter to players with enough observations for stable estimation.
    
    Returns (alpha0, beta0) hyperparameters.
    """
    mask = totals >= min_total
    rates = successes[mask] / totals[mask]
    
    # Method of moments (quick and dirty, usually close enough)
    mean_rate = rates.mean()
    var_rate = rates.var()
    
    # Solve for alpha, beta from mean and variance of beta distribution
    # mean = alpha / (alpha + beta)
    # var = alpha*beta / ((alpha+beta)^2 * (alpha+beta+1))
    common = mean_rate * (1 - mean_rate) / var_rate - 1
    alpha0 = mean_rate * common
    beta0 = (1 - mean_rate) * common
    
    return alpha0, beta0

def shrink_win_rates(wins: np.ndarray, starts: np.ndarray,
                     alpha0: float, beta0: float) -> np.ndarray:
    """
    Apply empirical Bayes shrinkage to win rates.
    
    Formula: (wins + alpha0) / (starts + alpha0 + beta0)
    
    Players with few starts get pulled toward the prior mean.
    Players with many starts barely change.
    """
    return (wins + alpha0) / (starts + alpha0 + beta0)

# Example: Golf top-10 rates
# Player A: 3 top-10s in 5 starts (60% raw rate)
# Player B: 15 top-10s in 50 starts (30% raw rate)
# Population prior: alpha0=3, beta0=17 (mean ~15%)

alpha0, beta0 = 3.0, 17.0  # typical for top-10 rates

player_a_shrunk = (3 + alpha0) / (5 + alpha0 + beta0)   # = 0.24 (shrunk from 0.60)
player_b_shrunk = (15 + alpha0) / (50 + alpha0 + beta0)  # = 0.257 (barely changed from 0.30)
```

### For Continuous Outcomes (Strokes Gained): James-Stein Approach

For continuous metrics like SG:Total, SG:OTT, SG:APP, etc., use the James-Stein estimator:

```python
import numpy as np

def james_stein_shrinkage(
    estimates: np.ndarray,
    sample_sizes: np.ndarray,
    variance_per_round: float = 3.0  # typical SG:Total variance per round
) -> np.ndarray:
    """
    James-Stein shrinkage for continuous outcomes.
    Requires k >= 4 estimates (the JS estimator only dominates MLE for 3+ dimensions).
    
    estimates: array of per-player SG averages
    sample_sizes: array of number of rounds per player
    variance_per_round: assumed within-player variance of SG per round
    """
    k = len(estimates)
    if k < 4:
        return estimates  # JS doesn't help with fewer than 4 estimates
    
    grand_mean = np.average(estimates, weights=sample_sizes)
    
    # Squared distance from grand mean, weighted by precision
    deviations = estimates - grand_mean
    precisions = sample_sizes / variance_per_round
    
    # Shrinkage factor: B = 1 - (k-3) / sum((x_i - x_bar)^2 * n_i / sigma^2)
    weighted_ss = np.sum(deviations**2 * precisions)
    shrinkage_factor = max(0, 1 - (k - 3) / weighted_ss)
    
    shrunk = grand_mean + shrinkage_factor * deviations
    return shrunk

# Better version: per-player shrinkage based on sample size
def bayesian_shrinkage_sg(
    player_means: np.ndarray,
    player_n_rounds: np.ndarray,
    population_mean: float = 0.0,
    population_variance: float = 1.5,  # between-player SG variance
    within_variance: float = 3.0       # within-player round-to-round variance
) -> np.ndarray:
    """
    Bayesian shrinkage for SG estimates.
    Each player gets shrunk individually based on their sample size.
    
    Posterior mean = (n * x_bar / sigma_w^2 + mu_0 / sigma_b^2) / 
                     (n / sigma_w^2 + 1 / sigma_b^2)
    
    This simplifies to a weighted average of player mean and population mean.
    """
    precision_data = player_n_rounds / within_variance
    precision_prior = 1.0 / population_variance
    
    weight_data = precision_data / (precision_data + precision_prior)
    
    posterior_means = weight_data * player_means + (1 - weight_data) * population_mean
    return posterior_means

# Example:
# Player with 4 rounds, SG:Total avg = +2.5
# Population mean = 0, between-player var = 1.5, within-player var = 3.0
weight = (4/3.0) / (4/3.0 + 1/1.5)  # = 1.33 / (1.33 + 0.67) = 0.667
shrunk_sg = 0.667 * 2.5 + 0.333 * 0.0  # = 1.67 (shrunk from 2.5)

# Player with 40 rounds, SG:Total avg = +2.5
weight = (40/3.0) / (40/3.0 + 1/1.5)  # = 13.33 / (13.33 + 0.67) = 0.952
shrunk_sg = 0.952 * 2.5 + 0.048 * 0.0  # = 2.38 (barely changed)
```

### Key Numbers for Golf SG Shrinkage

- **Between-player SG:Total variance**: ~1.0-2.0 (across the PGA Tour population)
- **Within-player round-to-round SG:Total variance**: ~3.0-4.0 (a player's variance from round to round)
- **Breakeven sample size**: When n ≈ within_var / between_var ≈ 3.0/1.5 = 2 rounds, data and prior are weighted equally
- **At 10 rounds**: ~77% weight on data, 23% on prior
- **At 20 rounds**: ~87% weight on data, 13% on prior
- **At 50 rounds**: ~95% weight on data, 5% on prior (barely shrunk)

### Pitfalls

| Pitfall | Consequence | Mitigation |
|---------|------------|------------|
| Assuming same prior for all players | Rookies and veterans have different priors | Use hierarchical model (separate priors by experience tier) |
| Not accounting for course effects | Raw SG includes course difficulty | Use course-adjusted SG or include course as a covariate |
| Using career-long data | Player skill changes over time | Weight recent rounds more heavily (exponential decay) |
| Setting variance parameters by guess | Badly calibrated shrinkage | Estimate from data using MLE or method of moments |
| Ignoring the selection bias | Players who make cuts have inflated SG | Account for missed cuts (often not in SG datasets) |

---

## 4. Implementing the Hedge/EWA Algorithm

### What It Does

The Exponentially Weighted Average (EWA) / Hedge algorithm maintains a portfolio of models and weights them by past performance. Bad models get down-weighted exponentially. This is ideal for combining multiple golf prediction models (e.g., SG model, course history model, recent form model).

### River ML Implementation

```python
from river import ensemble, linear_model, preprocessing, metrics, optim

# Define your base models (experts)
models = [
    linear_model.LinearRegression(optimizer=optim.SGD(0.01)),
    linear_model.LinearRegression(optimizer=optim.RMSProp()),
    linear_model.LinearRegression(optimizer=optim.AdaGrad()),
]

# Create the EWA ensemble
ewa = ensemble.EWARegressor(
    models=models,
    learning_rate=0.005  # controls how fast bad models get down-weighted
)

# Optionally wrap with preprocessing
pipeline = preprocessing.StandardScaler() | ewa

# Online learning loop
metric = metrics.MAE()
for x, y in data_stream:
    y_pred = pipeline.predict_one(x)
    metric.update(y, y_pred)
    pipeline.learn_one(x, y)

print(f"Running MAE: {metric.get()}")
```

### Learning Rate Selection

The `learning_rate` parameter (η) controls how aggressively the algorithm updates weights:

- **η = 0.5** (default): Very aggressive. Bad models get eliminated quickly. Good when one model is clearly best.
- **η = 0.005-0.05**: Conservative. Weights change slowly. Better for non-stationary environments where the "best" model changes over time.
- **η → 0**: Equal weighting forever (ignores performance). Not useful.

**For golf predictions** (non-stationary, seasonal, course-dependent):
- Start with **η = 0.01-0.05**
- The optimal regret bound learning rate is η = sqrt(8 * ln(N) / T) where N = number of models, T = number of rounds
- For 5 models over 200 events: η ≈ sqrt(8 * ln(5) / 200) ≈ 0.25 (this is theoretical; in practice, use 0.05-0.1)

### Cold Start Problem

With no historical data, all models start with equal weights. Strategies:

```python
# Strategy 1: Warm-start with backtested performance
# If you have backtested each model, initialize weights proportional to performance
initial_weights = [0.5, 0.3, 0.2]  # based on backtest MAE
# River doesn't support direct weight initialization, so you'd need to
# feed in synthetic data to "warm up" the weights

# Strategy 2: Conservative equal weighting with slow learning
ewa = ensemble.EWARegressor(
    models=models,
    learning_rate=0.01  # very slow update = stays near equal weighting longer
)

# Strategy 3: Run all models independently for first K events, then switch to EWA
MIN_EVENTS = 10
if events_seen < MIN_EVENTS:
    prediction = np.mean([m.predict_one(x) for m in models])
else:
    prediction = ewa.predict_one(x)
```

### Custom EWA for Non-River Use Cases

If your models aren't River-compatible (e.g., they're batch sklearn models):

```python
import numpy as np

class SimpleEWA:
    """Hedge/EWA for combining arbitrary model predictions."""
    
    def __init__(self, n_models: int, learning_rate: float = 0.05):
        self.n_models = n_models
        self.eta = learning_rate
        self.log_weights = np.zeros(n_models)  # log-space for numerical stability
    
    def predict(self, model_predictions: np.ndarray) -> float:
        """Weighted average prediction."""
        weights = self._get_weights()
        return np.dot(weights, model_predictions)
    
    def update(self, model_predictions: np.ndarray, true_value: float):
        """Update weights based on each model's loss."""
        losses = (model_predictions - true_value) ** 2
        self.log_weights -= self.eta * losses
        # Normalize to prevent overflow
        self.log_weights -= self.log_weights.max()
    
    def _get_weights(self) -> np.ndarray:
        weights = np.exp(self.log_weights)
        return weights / weights.sum()
    
    @property
    def weights(self) -> np.ndarray:
        return self._get_weights()

# Usage
ewa = SimpleEWA(n_models=3, learning_rate=0.05)

for event in events:
    preds = np.array([model_a.predict(event), model_b.predict(event), model_c.predict(event)])
    combined = ewa.predict(preds)
    
    # After observing outcome:
    ewa.update(preds, actual_outcome)
    print(f"Model weights: {ewa.weights}")
```

### Pitfalls

| Pitfall | Consequence | Mitigation |
|---------|------------|------------|
| Learning rate too high | One bad prediction permanently kills a model's weight | Use η ≤ 0.1 for non-stationary environments |
| Learning rate too low | Takes forever to identify the best model | Start higher (0.1), decay over time |
| Models that are correlated | Ensemble doesn't gain diversity | Ensure models use different features/methodologies |
| Not normalizing predictions | Model with larger scale dominates loss | Standardize all model outputs before EWA |
| Cold start with few events | Equal weighting may be far from optimal | Use warm-start from backtest if available |

---

## 5. ADWIN Drift Detection Practical Usage

### How ADWIN Works

ADWIN maintains an adaptive sliding window that automatically shrinks when drift is detected. It splits the window into two sub-windows (W₀ = older data, W₁ = newer data) and checks whether their means differ significantly.

### River Implementation

```python
from river import drift

# Basic setup
adwin = drift.ADWIN(
    delta=0.002,           # significance level (default)
    clock=32,              # check every 32 points (default)
    max_buckets=5,         # bucket compression (default)
    min_window_length=5,   # minimum subwindow size (default)
    grace_period=10        # don't check until 10 points (default)
)

# Feed in your model's prediction errors (or any metric you want to monitor)
for i, prediction_error in enumerate(errors_stream):
    adwin.update(prediction_error)
    
    if adwin.drift_detected:
        print(f"Drift at index {i}! Window stats: mean={adwin.estimation:.4f}, "
              f"width={adwin.width}, variance={adwin.variance:.4f}")
        # Trigger retraining or model switch
```

### Delta Parameter Tuning Guide

| Delta | Behavior | Use Case |
|-------|----------|----------|
| 0.0002 | Very sensitive, many detections | When you need to catch small shifts immediately |
| 0.002 (default) | Balanced sensitivity | Good starting point for most applications |
| 0.01 | Less sensitive | When false positives are costly (e.g., unnecessary retraining) |
| 0.05 | Very tolerant | Only detect major distribution shifts |
| 0.1+ | Almost never fires | Essentially disabling drift detection |

**For golf predictions**: Start with **delta=0.01** (less sensitive than default). Golf has inherent week-to-week variance that isn't drift — it's just noise. A more tolerant delta prevents reacting to normal variance.

### When ADWIN Fires False Positives

1. **High-variance data**: If your metric naturally has high variance (golf prediction errors do), ADWIN fires more often. Increase `min_window_length` and `delta`.
2. **Seasonal patterns**: If performance is seasonal (e.g., better on certain course types), ADWIN reads seasonal shifts as drift. Consider de-seasonalizing your error metric first.
3. **Small grace period**: With `grace_period=10`, early outliers can trigger false drift. For golf, set `grace_period=20-30`.
4. **Correlated data**: ADWIN assumes independent observations. Predictions within a tournament are correlated. Feed in per-tournament aggregate errors, not per-player.

### Alternatives to ADWIN for Small Samples

**Page-Hinkley Test** (also in River):
```python
from river import drift

ph = drift.PageHinkley(
    min_instances=30,    # minimum observations before detecting
    delta=0.005,         # magnitude of allowed changes
    threshold=50.0,      # cumulative sum threshold for detection
    alpha=0.9999         # forgetting factor for old data
)

for i, val in enumerate(data_stream):
    ph.update(val)
    if ph.drift_detected:
        print(f"Page-Hinkley: drift at {i}")
```

Page-Hinkley advantages over ADWIN:
- Better for detecting **gradual** drift (ADWIN excels at sudden shifts)
- `min_instances=30` is a natural guard against small-sample false positives
- The `alpha` forgetting factor lets old data decay naturally

**KSWIN (Kolmogorov-Smirnov Windowing)**: Detects distributional changes beyond just mean shifts — also catches variance changes and shape changes. Better for golf where the error distribution shape might change.

### Practical Integration Pattern

```python
from river import drift

class DriftAwarePredictor:
    def __init__(self, model, delta=0.01, grace_period=25):
        self.model = model
        self.adwin = drift.ADWIN(delta=delta, grace_period=grace_period)
        self.drift_count = 0
        self.last_drift_idx = None
    
    def predict_and_update(self, x, y_true, idx):
        y_pred = self.model.predict(x)
        error = abs(y_pred - y_true)
        
        self.adwin.update(error)
        
        if self.adwin.drift_detected:
            self.drift_count += 1
            self.last_drift_idx = idx
            self._handle_drift()
        
        return y_pred
    
    def _handle_drift(self):
        """Decide what to do when drift is detected."""
        # Option 1: Retrain on recent data only
        # Option 2: Increase learning rate temporarily
        # Option 3: Switch to a backup model
        # Option 4: Log and continue (monitor but don't act)
        pass
```

### Pitfalls

| Pitfall | Consequence | Mitigation |
|---------|------------|------------|
| Feeding per-prediction errors (not aggregated) | Too many correlated signals, false positives | Aggregate to per-event level |
| Default delta (0.002) in noisy domain | Constant false alarms | Increase to 0.01-0.05 for golf |
| Retraining on every drift detection | Instability, thrashing | Require 2+ consecutive detections, or use a cooldown period |
| Not logging drift events | Can't debug or learn from patterns | Log timestamp, window stats, and context |
| Ignoring ADWIN's `estimation` attribute | Missing useful mean-tracking info | Use it for monitoring dashboards |

---

## 6. Fractional Kelly with Confidence Intervals

### The Core Problem

The Kelly Criterion assumes you know the true probability exactly. You don't. When you use estimated probabilities, you systematically overbat because you're betting on noise.

### Basic Kelly Formula

```python
def kelly_fraction(p_win: float, decimal_odds: float) -> float:
    """
    Standard Kelly fraction for a binary bet.
    
    p_win: estimated probability of winning
    decimal_odds: decimal odds offered (e.g., 2.0 for even money)
    
    Returns fraction of bankroll to wager.
    Negative = don't bet.
    """
    b = decimal_odds - 1  # net fractional odds
    q = 1 - p_win
    f = (p_win * b - q) / b
    return max(0, f)

# Example: 55% win prob at 2.0 decimal odds
f = kelly_fraction(0.55, 2.0)  # = (0.55*1 - 0.45)/1 = 0.10 = bet 10% of bankroll
```

### Fractional Kelly Under Parameter Uncertainty (Baker & McHale)

Baker & McHale showed the optimal fraction depends on your uncertainty (σ) about the probability estimate:

```python
import numpy as np
from scipy.stats import beta as beta_dist
from scipy.integrate import quad
from scipy.optimize import minimize_scalar

def optimal_kelly_fraction(
    p_estimated: float,
    sigma_p: float,
    decimal_odds: float
) -> float:
    """
    Compute the optimal Kelly fraction accounting for uncertainty
    in the probability estimate.
    
    p_estimated: point estimate of win probability
    sigma_p: standard deviation of your probability estimate
    decimal_odds: offered decimal odds
    
    Uses Baker & McHale's framework with a Beta distribution prior.
    """
    b = decimal_odds - 1  # net odds
    
    # Convert mean and variance to beta distribution parameters
    variance = sigma_p ** 2
    if variance >= p_estimated * (1 - p_estimated):
        return 0.0  # variance too high, don't bet
    
    common = p_estimated * (1 - p_estimated) / variance - 1
    alpha = p_estimated * common
    beta_param = (1 - p_estimated) * common
    
    # Find optimal shrinkage factor k
    def neg_expected_utility(k):
        if k <= 0 or k >= 1:
            return 0
        
        def integrand(q):
            if q <= 0 or q >= 1:
                return 0
            f = (q * (b + 1) - 1) / b  # Kelly fraction at true prob q
            if f <= 0:
                return 0
            bet = k * f
            if bet >= 1 or bet <= 0:
                return 0
            pdf = beta_dist.pdf(q, alpha, beta_param)
            utility = p_estimated * np.log(1 + b * bet) + (1 - p_estimated) * np.log(1 - bet)
            return pdf * utility
        
        result, _ = quad(integrand, 0.01, 0.99, limit=100)
        return -result
    
    result = minimize_scalar(neg_expected_utility, bounds=(0.01, 0.99), method='bounded')
    optimal_k = result.x
    
    # Apply shrinkage to the point-estimate Kelly
    base_kelly = kelly_fraction(p_estimated, decimal_odds)
    return optimal_k * base_kelly

# Example scenarios:
# High confidence (σ=0.02): bet close to full Kelly
frac = optimal_kelly_fraction(0.55, 0.02, 2.0)  # k ≈ 0.85-0.95

# Moderate confidence (σ=0.10): significant shrinkage  
frac = optimal_kelly_fraction(0.55, 0.10, 2.0)  # k ≈ 0.3-0.5

# Low confidence (σ=0.20): barely bet
frac = optimal_kelly_fraction(0.55, 0.20, 2.0)  # k ≈ 0.05-0.15
```

### Simplified Fractional Kelly Rules of Thumb

When you don't want to run the full optimization:

```python
def simple_fractional_kelly(
    p_estimated: float,
    decimal_odds: float,
    confidence_level: str = "moderate"  # "high", "moderate", "low"
) -> float:
    """
    Simplified fractional Kelly with fixed fractions.
    
    Half Kelly (k=0.5): ~75% of optimal growth, 50% less variance
    Quarter Kelly (k=0.25): ~44% of optimal growth, 75% less variance
    """
    fractions = {
        "high": 0.5,      # Half Kelly — you have strong model + data
        "moderate": 0.33,  # Third Kelly — typical for model-based betting
        "low": 0.25,       # Quarter Kelly — uncertain edge
    }
    
    k = fractions[confidence_level]
    base_f = kelly_fraction(p_estimated, decimal_odds)
    return k * base_f
```

### When Kelly Says Bet But the CI Includes Zero

This is the critical case. Your point estimate says you have edge, but the confidence interval includes zero (no edge).

```python
def kelly_with_ci_check(
    p_estimated: float,
    p_lower_ci: float,  # lower bound of 95% CI
    p_upper_ci: float,  # upper bound of 95% CI
    decimal_odds: float,
    min_edge_threshold: float = 0.02  # require at least 2% edge
) -> dict:
    """
    Kelly bet sizing with confidence interval validation.
    """
    implied_prob = 1.0 / decimal_odds
    
    # Point estimate edge
    edge = p_estimated - implied_prob
    
    # Lower CI edge
    edge_lower = p_lower_ci - implied_prob
    
    # Decision logic
    if edge <= 0:
        return {"action": "NO_BET", "reason": "No edge at point estimate", "fraction": 0}
    
    if edge_lower > min_edge_threshold:
        # Even the lower CI shows meaningful edge — full fractional Kelly
        fraction = kelly_fraction(p_estimated, decimal_odds) * 0.5
        return {"action": "BET", "reason": "Edge robust at 95% CI", "fraction": fraction}
    
    if edge_lower > 0:
        # Edge exists at lower CI but is small
        fraction = kelly_fraction(p_estimated, decimal_odds) * 0.25
        return {"action": "SMALL_BET", "reason": "Edge fragile but positive", "fraction": fraction}
    
    if edge > min_edge_threshold:
        # Point estimate has edge but CI includes zero
        # Use very conservative fraction OR track as a "paper bet"
        fraction = kelly_fraction(p_estimated, decimal_odds) * 0.10
        return {"action": "TINY_BET_OR_PAPER", "reason": "CI includes zero", "fraction": fraction}
    
    return {"action": "NO_BET", "reason": "Edge too small and uncertain", "fraction": 0}
```

### Bankroll Management Framework

```python
class BankrollManager:
    """Practical bankroll management with fractional Kelly."""
    
    def __init__(
        self,
        initial_bankroll: float,
        max_fraction: float = 0.05,     # never bet more than 5% on one bet
        max_daily_exposure: float = 0.20, # never have more than 20% at risk
        kelly_multiplier: float = 0.33,   # use 1/3 Kelly
        min_bet_fraction: float = 0.005,  # minimum 0.5% to bother placing
    ):
        self.bankroll = initial_bankroll
        self.max_fraction = max_fraction
        self.max_daily_exposure = max_daily_exposure
        self.kelly_multiplier = kelly_multiplier
        self.min_bet_fraction = min_bet_fraction
        self.daily_exposure = 0.0
    
    def size_bet(self, p_estimated: float, decimal_odds: float) -> float:
        """Returns dollar amount to bet, or 0."""
        raw_kelly = kelly_fraction(p_estimated, decimal_odds)
        adjusted = raw_kelly * self.kelly_multiplier
        
        # Apply caps
        adjusted = min(adjusted, self.max_fraction)
        
        # Check daily exposure
        remaining_exposure = self.max_daily_exposure - self.daily_exposure
        adjusted = min(adjusted, remaining_exposure)
        
        # Below minimum threshold? Don't bother.
        if adjusted < self.min_bet_fraction:
            return 0.0
        
        bet_amount = adjusted * self.bankroll
        self.daily_exposure += adjusted
        return round(bet_amount, 2)
    
    def update_bankroll(self, profit_loss: float):
        self.bankroll += profit_loss
    
    def reset_daily(self):
        self.daily_exposure = 0.0
```

### Pitfalls

| Pitfall | Consequence | Mitigation |
|---------|------------|------------|
| Using full Kelly | Catastrophic drawdowns (50%+ drops) | Always use fractional (0.25-0.5x) |
| Not capping bet size | One "sure thing" ruins bankroll | Hard cap at 5% of bankroll per bet |
| Ignoring correlation between bets | True exposure is higher than sum of individual bets | Track correlated bets as a group |
| Betting when CI includes zero | Betting on noise | Require lower CI > 0 or use 10% Kelly |
| Not adjusting fraction with bankroll | Constant dollar sizing ignores bankroll growth/decline | Recalculate fraction each bet based on current bankroll |
| Compounding estimation errors | p estimate wrong → Kelly fraction wrong → bankroll damaged | Use Bayesian p updates + fractional Kelly simultaneously |

---

## Summary: Quick Reference

### What to Use When (Sample Size Guide)

| Technique | Min Samples | Sweet Spot | What to Monitor |
|-----------|-------------|------------|-----------------|
| Isotonic Regression | 1000+ | 5000+ | Calibration curve shape |
| Platt Scaling | 100+ | 500+ | Sigmoid fit quality |
| CLV Analysis | 50+ bets | 200+ bets | Mean CLV, t-statistic |
| Empirical Bayes (binary) | 30+ players | 100+ players | Prior fit (alpha, beta) |
| Empirical Bayes (continuous) | 4+ estimates | 50+ estimates | Between/within variance ratio |
| EWA/Hedge | 10+ events | 50+ events | Weight distribution, regret |
| ADWIN Drift | 30+ observations | 100+ observations | False positive rate |
| Kelly Fraction | N/A (formula) | 100+ bets for bankroll path | Drawdown, Sharpe ratio |

### Python Packages to Install

```bash
pip install scikit-learn   # CalibratedClassifierCV, IsotonicRegression
pip install shin           # Shin method de-vigging
pip install penaltyblog    # All de-vigging methods + metrics
pip install river          # EWARegressor, ADWIN, PageHinkley
pip install scipy          # Beta distribution, optimization
pip install keeks          # Kelly criterion utilities
```

### Red Flags That Something Is Wrong

1. **Calibration ECE improving but Brier score worsening** → you're overfitting the calibration set
2. **Positive CLV but negative P&L for 200+ bets** → your de-vigging method may be wrong, or you're measuring CLV incorrectly
3. **EWA weights collapsing to one model** → learning rate too high, or one model is overfit to recent data
4. **ADWIN firing every week** → delta too low for your domain's natural variance
5. **Kelly recommending > 10% of bankroll** → your edge estimate is almost certainly wrong
6. **Shrinkage making all players identical** → prior variance is set too low relative to data variance
