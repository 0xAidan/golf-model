# Bet Correlation, Portfolio Management & Variance Research

> Research conducted 2026-02-28. Sources: academic papers, professional betting forums, quantitative finance resources, golf-specific research.

---

## Table of Contents
1. [Correlated Bets Within a Single Tournament](#topic-1-correlated-bets-within-a-single-tournament)
2. [Per-Player Exposure Across Markets](#topic-2-per-player-exposure-across-markets)
3. [Portfolio Construction for Sports Betting](#topic-3-portfolio-construction-for-sports-betting)
4. [Variance Simulation and Probability of Ruin](#topic-4-variance-simulation-and-probability-of-ruin)
5. [Pre-Committed Stopping Rules](#topic-5-pre-committed-stopping-rules)
6. [Implementation Formulas & Code](#appendix-implementation-formulas--code)

---

## TOPIC 1: Correlated Bets Within a Single Tournament

### How Correlated Are 15 Matchups at the Same Tournament?

**Answer: Moderately correlated, with correlation driven by shared environmental factors.**

When you bet 15 head-to-head matchups at the same golf tournament, the outcomes are NOT independent. They share systematic risk factors:

1. **Weather/tee-time draw correlation**: Research on the U.S. Masters found that atmospheric conditions (wet-bulb temperature + wind speed) explain **over 44% of variance in mean scores**. At the 2016 Open Championship at Royal Troon, the scoring differential between tee-time waves reached **3.2 strokes** — morning players averaged 73.4 vs afternoon players at 75.3. If multiple of your matchup selections are in the same tee-time wave, a weather shift helps or hurts them simultaneously.

2. **Course condition shifts**: Pin positions, green speeds, and firmness change across rounds. A course playing "easy" on Thursday morning benefits all morning-wave players, creating positive correlation across any matchups involving those players.

3. **Scoring environment correlation**: When conditions are benign, the entire field shoots low, compressing the distribution. This systematically favors the weaker player in matchups (they can keep pace when conditions are easy). Conversely, difficult conditions expand the distribution and favor stronger players. This creates a hidden directional bet across all your matchups.

### Quantifying the Correlation

While exact pairwise correlation between golf matchups hasn't been published, we can estimate:

- **Same tee-time wave, same round**: Correlation ≈ 0.15-0.30 (players face identical conditions)
- **Opposite tee-time waves**: Correlation ≈ 0.05-0.10 (shared course but different conditions)
- **Full tournament matchups**: Correlation ≈ 0.05-0.15 (weather effects partially cancel over 4 rounds, but course-fit advantages persist)
- **Matchups sharing a player**: Correlation ≈ 0.60-0.80 (if Player A appears in two matchups, those are extremely correlated)

### Key Risk: Systemic Blow-Up Scenarios

The danger isn't moderate correlation on any single pair — it's that **all 15 matchups can go wrong simultaneously** when:
- An unexpected weather shift benefits the wrong tee-time wave
- Course setup changes dramatically between rounds
- A "birdie-fest" day compresses the field and upsets expected matchup outcomes
- Your model systematically overvalues a player archetype that underperforms in specific conditions

**Rule of thumb**: Treat 15 matchups at the same tournament as roughly equivalent to **8-10 truly independent bets** for risk-sizing purposes, not 15.

---

## TOPIC 2: Per-Player Exposure Across Markets

### The Core Problem

If you bet Scottie Scheffler in:
- A head-to-head matchup vs. Rory McIlroy
- Outright to win (+800)
- Top 5 finish (-120)

These three bets are **extremely correlated** — they essentially all need Scheffler to play well. If Scheffler has a bad week (misses cut, equipment issue, illness), you lose ALL THREE bets simultaneously.

### Measuring Per-Player Exposure

**Total Player Exposure** = Sum of all stakes on bets where that player's performance determines the outcome.

For golf specifically:
| Bet Type | Correlation to "Player plays well" |
|---|---|
| Outright win | ~1.0 (perfect correlation) |
| Top 5 | ~0.90-0.95 |
| Top 10 | ~0.80-0.90 |
| Top 20 | ~0.65-0.80 |
| H2H matchup (win) | ~0.70-0.85 (depends on opponent quality) |
| Make/miss cut | ~0.50-0.70 |

### Exposure Limits — Rules of Thumb

Based on professional syndicate practices and portfolio theory:

| Limit Type | Recommended Cap |
|---|---|
| **Single player, all markets** | 3-5% of bankroll maximum |
| **Single tournament, all bets** | 10-15% of bankroll maximum |
| **Single "idea" (e.g., course plays hard)** | 5-8% of bankroll |
| **Any single bet** | 0.5-2% of bankroll |

### Implementation Approach

Calculate an **effective exposure matrix**:

```
Effective Exposure to Player X = Σ (stake_i × correlation_i)
```

Where `correlation_i` is how much bet `i` depends on Player X performing well.

**Example**: $100 on Scheffler outright + $200 on Scheffler matchup + $150 on Scheffler Top 5
- Effective Scheffler exposure ≈ $100×1.0 + $200×0.75 + $150×0.93 = **$389.50**
- If bankroll is $5,000, that's 7.8% — exceeds the 5% single-player cap

### The Right Approach

Expert bettors recommend: **Use different players for different market types** rather than stacking the same player across matchup + outright + top finish. If you believe in Scheffler, pick your highest-edge market for him and use different players for other markets.

---

## TOPIC 3: Portfolio Construction for Sports Betting

### Professional Syndicate Approach

Professional betting syndicates manage risk like hedge funds:

1. **Diversification across bet types**: Spread capital across matchups, outrights, top finishes, and props
2. **Diversification across events**: Don't put all capital into one tournament
3. **Correlation-aware sizing**: Size bets based on how they interact, not in isolation
4. **Strict exposure caps**: Per-player, per-event, per-"idea" limits

### The "Exposure Bucket" Framework

From professional betting forums, the recommended approach:

1. **Before betting, group bets into "exposure buckets"** based on shared drivers:
   - Same player performing well
   - Same tee-time wave benefiting from conditions
   - Same course-fit thesis (e.g., "bombers dominate this week")
   - Same weather prediction being correct

2. **Set a cap per bucket** (5-8% of bankroll max)

3. **Size the bucket first, then distribute across bets within it**

### Maximum Exposure Rules of Thumb

| Rule | Threshold |
|---|---|
| Max single bet | 1-2% of bankroll |
| Max per player across all markets | 3-5% of bankroll |
| Max per tournament (all bets combined) | 10-15% of bankroll |
| Max per "idea"/exposure bucket | 5-8% of bankroll |
| Max per week (if betting multiple tournaments) | 15-20% of bankroll |

### Volatility Targeting

Professional approach from sports-ai.dev:
- Track realized daily/weekly PnL standard deviation
- If volatility exceeds target (e.g., 4% of bankroll weekly), proportionally scale ALL stakes downward by `target_vol / realized_vol`
- Set per-market and per-league caps to avoid hidden correlation spikes

### Drawdown Triggers (Automatic Risk Reduction)

| Drawdown Level | Action |
|---|---|
| -10% | Review model calibration, tighten edge thresholds |
| -15% | Halve Kelly fraction |
| -20% | Reduce to minimum bet sizes, run full diagnostics |
| -25% | Freeze new bet types, comprehensive model review |
| -30% | Suspend betting, complete system audit |

### Goal Hierarchy (in order)

1. **Survival** — avoid ruin at all costs
2. **Variance discipline** — emotional and capital stability
3. **Compounding efficiency** — maximize long-run log growth

---

## TOPIC 4: Variance Simulation and Probability of Ruin

### Probability of Ruin at Various Kelly Fractions

From Chin & Ingenoso's academic paper on risk formulas for proportional betting, the key results:

#### Instantaneous Risk of Ruin (Non-Resizing Kelly Equivalent)

| Kelly Fraction (k) | Risk of Ruin |
|---|---|
| 1.00 (full Kelly) | **13.53%** |
| 0.50 (half Kelly) | **1.83%** |
| 0.40 | **0.67%** |
| 0.35 | **0.33%** |
| 0.30 | **0.13%** |
| 0.25 (quarter Kelly) | **0.03%** |
| 0.20 | **~0.00%** |

**Formula**: `P(ruin) = exp(-2/k)` where k is the Kelly fraction.

#### Probability of Ever Being "Halved" (Reaching 50% of Starting Bankroll)

The probability of EVER losing half your bankroll:

| Kelly Fraction | P(ever halved) |
|---|---|
| Full Kelly (k=1) | **50%** |
| Half Kelly (k=0.5) | **12.5%** (= 0.5^3) |
| Third Kelly (k=0.33) | **3.1%** (= 0.5^5) |
| Quarter Kelly (k=0.25) | **0.8%** (= 0.5^7) |

**Formula**: `P(ever reaching fraction a of bankroll) = a^(2/k - 1)`

At half Kelly, the probability of reaching any fraction `a` of your bankroll is `a³`. So:
- P(losing 50%) = 0.5³ = 12.5%
- P(losing 70%) = 0.3³ = 2.7%
- P(losing 80%) = 0.2³ = 0.8%

At quarter Kelly, it becomes `a⁷`:
- P(losing 50%) = 0.5⁷ = 0.78%
- P(losing 70%) = 0.3⁷ = 0.02%

### Growth Rate vs. Kelly Fraction Tradeoff

**Formula**: `G(f) ≈ r + f×K - f²×K/2`

Where f is the Kelly fraction and K is the edge.

| Kelly Fraction | % of Optimal Growth | Variance Reduction |
|---|---|---|
| 1.00 (full) | 100% | 0% |
| 0.75 | ~94% | 25% |
| 0.50 (half) | ~75% | 50% |
| 0.33 (third) | ~56% | 67% |
| 0.25 (quarter) | ~44% | 75% |

**Key insight**: Half Kelly gives you 75% of the growth rate but cuts variance in half. Quarter Kelly gives 44% growth but cuts variance by 75%. The tradeoff is extremely favorable for fractional Kelly.

### Expected Maximum Drawdown

From Noma et al.'s simulation research (100,000 scenarios):

**For Full Kelly (p=0.55, even money):**
| Number of Bets | Median Max Drawdown |
|---|---|
| 30 | ~38% |
| 100 | ~65% |
| 500 | ~85% |
| 1,000 | ~90% |
| 10,000 | ~97% |
| 100,000 | ~100% |

**For Half Kelly:**
| Number of Bets | Median Max Drawdown |
|---|---|
| 30 | ~20% |
| 100 | ~40% |
| 500 | ~55% |
| 1,000 | ~60% |
| 10,000 | ~85% |

**Critical finding**: The relationship between bet size and max drawdown is **convex** for large numbers of bets. Reducing from full Kelly to 80% Kelly barely reduces drawdown. You need to cut to 40-50% Kelly to see meaningful drawdown reduction over 1,000+ bets.

### Expected Losing Streaks

For a bettor with 55% win rate over 1,000 bets:
- **Expected longest losing streak**: ~15-16 losses in a row
- **P(10 consecutive losses during 1,000 bets)**: ~25%
- **P(5 consecutive losses in 54 bets)**: ~1.85%

**Formula**: `Expected Longest Losing Run (ELLR) = log(n) / -log(1 - SR)`

Where n = number of bets, SR = strike rate.

For golf-specific markets with lower hit rates (e.g., outrights at ~10-15% hit rate):
- Expected longest losing streak over 100 outright bets: **~40-60 consecutive losses**
- This is normal and expected — not a sign of a broken model

### Monte Carlo Simulation Approach

**Implementation steps:**
1. Load historical betting data (stakes, odds, actual results)
2. Calculate real-world stats: total bets, turnover, actual profit, ROI, max drawdown
3. Run 100,000+ simulations:
   - For each simulation, replay all bets
   - For each bet: generate random number r ∈ [0,1]
   - If r ≤ (1/odds), mark as win; otherwise loss
   - Track simulated profit and max drawdown
4. Compute distribution of outcomes: percentiles, worst case, probability of hitting various drawdown levels

**Key outputs to track:**
- P(profitable after N bets)
- P(max drawdown exceeds X%)
- Expected return (mean across simulations)
- Median final bankroll
- 5th percentile final bankroll (worst reasonable case)

### Bankroll Sizing Recommendations

| Approach | Minimum Bankroll (in units) |
|---|---|
| Conservative (1% per bet) | 100 units |
| Standard (2% per bet) | 50 units |
| Professional (fractional Kelly) | 100-200 units |
| Golf-specific (high variance outrights) | 200+ units |

**For a golf model placing ~15-25 bets per tournament across 40 tournaments/year (600-1,000 bets/year):**
- Minimum recommended bankroll: **200 units**
- Comfortable bankroll: **300-500 units**
- Where 1 unit = your standard flat bet size

---

## TOPIC 5: Pre-Committed Stopping Rules

### The Core Question: When Should You Conclude Your Model Has No Edge?

This is fundamentally a statistical hypothesis testing problem:
- **H₀**: Model has no edge (expected ROI ≤ 0 after vig)
- **H₁**: Model has a genuine edge of size δ

### Sample Size Requirements by Metric

#### Using Win/Loss Results Only (Noisy, Requires Large Samples)

| True Edge | Bets for 95% Confidence | Bets for 99% Confidence |
|---|---|---|
| 1% edge | ~10,000+ | ~15,000+ |
| 3% edge | ~3,000-5,000 | ~5,000-8,000 |
| 5% edge | ~1,500-2,500 | ~2,500-4,000 |
| 10% edge | ~500-1,000 | ~1,000-1,500 |

For golf matchups at roughly even money: a 55% win rate (5% edge) requires approximately **1,030 bets** to have 99% confidence you're winning more than losing.

#### Using Closing Line Value (CLV) — Much More Efficient

CLV is dramatically more sample-efficient because it measures continuous increments rather than binary outcomes:

| Consistent CLV Edge | Approximate Bets for Statistical Significance |
|---|---|
| 5% CLV | ~50 bets |
| 3% CLV | ~100-150 bets |
| 2% CLV | ~200-300 bets |
| 1% CLV | ~500+ bets |

**Critical caveat**: CLV is most reliable in high-liquidity markets. Golf outright markets have lower liquidity than NFL spreads, so CLV significance thresholds should be treated with caution. Golf matchup markets at major books may be more reliable for CLV analysis.

#### ROI Stabilization by Odds Range

From empirical research on sample sizes:

**Low Odds (1.20-1.60):**
- 1,000 bets: ROI fluctuates -6% to +8%
- 2,000 bets: ROI fluctuates -2% to +5%
- 3,000+ bets: ROI stabilizes at +1% to +4%

**Medium Odds (1.70-2.30):**
- Fastest ROI accumulation, most manageable variance
- ROI stabilizes faster than low or high odds

### Sequential Testing Framework (SPRT)

Rather than fixing a sample size in advance, use **Sequential Probability Ratio Testing (SPRT)**:

**Setup:**
- H₀: Model edge = 0%
- H₁: Model edge = target_edge (e.g., 3%)
- Choose α (Type I error, e.g., 0.05) and β (Type II error, e.g., 0.10)

**Decision thresholds:**
- Accept H₁ (model has edge) when: Λₙ ≥ (1-β)/α = 18
- Accept H₀ (no edge) when: Λₙ ≤ β/(1-α) = 0.105
- Continue sampling otherwise

**Advantages:**
- Allows checking after every bet without inflating false positive rate
- On average requires fewer samples than fixed-sample tests
- Naturally adapts to the true effect size

### Recommended Stopping Rules for a Golf Model

#### Pre-commit to these thresholds before launching:

**Phase 1: Validation (First 100-200 bets)**
- Track CLV on every bet
- If mean CLV is negative after 100 bets, investigate model deeply
- If mean CLV is significantly negative (< -3%) after 150 bets, strong evidence of no edge

**Phase 2: Confirmation (200-500 bets)**
- Track both CLV and actual results
- If CLV is positive but results are negative, continue (variance is expected)
- If both CLV and results are negative after 300 bets, model likely has no edge

**Phase 3: Steady State (500+ bets)**
- CLV should be converging to a stable positive number
- Actual ROI should be trending toward CLV
- If ROI is still significantly negative after 500 bets AND CLV is flat/negative, conclude no edge

#### Red Flags That Suggest Stopping Earlier

1. **No CLV improvement over 100+ bets** — you're not beating the closing line at all
2. **Systematic bias**: Model consistently overvalues or undervalues the same player archetype
3. **Edge only exists in backtesting, not live**: Backtest shows +5% ROI but live shows -3% after 200 bets
4. **CLV positive but declining**: Edge is being priced out by the market

#### The p-Value Approach

After N bets at win rate w with expected fair rate w₀:

```
z = (w - w₀) / sqrt(w₀ × (1 - w₀) / N)
```

| z-score | p-value | Interpretation |
|---|---|---|
| > 2.0 | < 0.023 | Strong evidence of edge |
| 1.5 - 2.0 | 0.023 - 0.067 | Suggestive of edge |
| 1.0 - 1.5 | 0.067 - 0.159 | Inconclusive |
| < 1.0 | > 0.159 | No evidence of edge |
| < -1.5 | - | Evidence model is losing |

### The "Peeking Problem"

If you check results after every tournament (not just at pre-committed checkpoints), your false positive rate inflates:

```
α_inflated = 1 - (1 - α)^k
```

Where k is the number of times you peek. With α=0.05 and 20 peeks (20 tournaments):
- Inflated false positive rate: `1 - 0.95^20 = 64%`

**Solution**: Use sequential testing methods (SPRT) or pre-commit to specific checkpoint sample sizes (100, 300, 500, 1000 bets).

---

## APPENDIX: Implementation Formulas & Code

### A. Simultaneous Kelly for Multiple Independent Bets (Python)

From emiruz.com, a clean implementation:

```python
import numpy as np
from scipy.optimize import minimize

def kelly_simultaneous(odds: np.ndarray, probs: np.ndarray, fraction: float = 1.0) -> np.ndarray:
    """
    Compute Kelly-optimal fractions for multiple simultaneous independent bets.
    
    Args:
        odds: Net odds for each bet (e.g., 1.2 means win $1.20 per $1 risked)
        probs: Win probability for each bet
        fraction: Kelly fraction (0.25 = quarter Kelly, 0.5 = half Kelly)
    
    Returns:
        Optimal fraction of bankroll to bet on each wager
    """
    def neg_growth(F):
        return -np.prod(
            ((1 + (F / fraction) * odds) ** probs) * 
            ((1 - (F / fraction)) ** (1 - probs))
        )
    
    result = minimize(
        fun=neg_growth,
        x0=np.zeros(len(odds)),
        bounds=[(0, 1) for _ in odds],
        constraints={'type': 'ineq', 'fun': lambda F: 1 - np.sum(F)}
    )
    return result.x
```

### B. Multivariate Kelly with Covariance (Portfolio Approach)

For correlated bets, use the portfolio formulation:

```python
import numpy as np

def kelly_portfolio(expected_returns: np.ndarray, cov_matrix: np.ndarray) -> np.ndarray:
    """
    Multivariate Kelly criterion using mean-variance framework.
    
    f* = Σ⁻¹ × μ
    
    Args:
        expected_returns: Expected edge for each bet (e.g., [0.03, 0.05, 0.02])
        cov_matrix: Covariance matrix of bet returns
    
    Returns:
        Optimal fraction of bankroll for each bet
    """
    precision_matrix = np.linalg.inv(cov_matrix)
    kelly_fractions = precision_matrix @ expected_returns
    return np.maximum(kelly_fractions, 0)  # No short selling in betting
```

### C. Probability of Drawdown (Chin & Ingenoso Formula)

```python
import math

def prob_ever_reaching_fraction(target_fraction: float, kelly_fraction: float) -> float:
    """
    Probability of EVER losing down to target_fraction of your bankroll
    when betting kelly_fraction of Kelly.
    
    P(a) = a^(2/k - 1)
    
    Example: prob_ever_reaching_fraction(0.5, 0.5) = 0.125 (12.5%)
             meaning 12.5% chance of ever being halved at half Kelly
    """
    a = target_fraction
    k = kelly_fraction
    return a ** (2.0 / k - 1.0)

def prob_reach_goal_before_drawdown(drawdown_level: float, goal_multiple: float, kelly_fraction: float) -> float:
    """
    Probability of reaching goal_multiple of bankroll BEFORE losing to drawdown_level.
    
    P(a,b) = (1 - a^(1-2/k)) / (b^(1-2/k) - a^(1-2/k))
    """
    a = drawdown_level
    b = goal_multiple
    k = kelly_fraction
    exp = 1.0 - 2.0 / k
    return (1.0 - a ** exp) / (b ** exp - a ** exp)

def risk_of_ruin_non_resizing(kelly_fraction: float) -> float:
    """
    Kelly-equivalent risk of ruin (non-resizing approximation).
    P(ruin) = exp(-2/k)
    """
    return math.exp(-2.0 / kelly_fraction)
```

### D. Monte Carlo Bankroll Simulation

```python
import numpy as np
from dataclasses import dataclass

@dataclass
class SimulationResult:
    mean_final_bankroll: float
    median_final_bankroll: float
    p5_final_bankroll: float
    p95_final_bankroll: float
    mean_max_drawdown: float
    median_max_drawdown: float
    prob_profitable: float
    prob_ruin: float  # Below 10% of starting bankroll

def monte_carlo_bankroll(
    edges: np.ndarray,          # Expected edge per bet (e.g., 0.03 for 3%)
    odds: np.ndarray,           # Decimal odds per bet
    stake_fraction: float,      # Fraction of bankroll per bet (e.g., 0.01 for 1%)
    initial_bankroll: float = 1000.0,
    n_simulations: int = 100_000,
    ruin_threshold: float = 0.10,  # 10% of starting = "ruin"
) -> SimulationResult:
    """
    Monte Carlo simulation of bankroll trajectory.
    """
    n_bets = len(edges)
    win_probs = 1.0 / odds + edges  # Convert odds + edge to win probability
    
    final_bankrolls = np.zeros(n_simulations)
    max_drawdowns = np.zeros(n_simulations)
    
    for sim in range(n_simulations):
        bankroll = initial_bankroll
        peak = initial_bankroll
        max_dd = 0.0
        
        for i in range(n_bets):
            stake = bankroll * stake_fraction
            if np.random.random() < win_probs[i]:
                bankroll += stake * (odds[i] - 1)
            else:
                bankroll -= stake
            
            if bankroll > peak:
                peak = bankroll
            dd = (peak - bankroll) / peak
            if dd > max_dd:
                max_dd = dd
            
            if bankroll <= 0:
                break
        
        final_bankrolls[sim] = bankroll
        max_drawdowns[sim] = max_dd
    
    return SimulationResult(
        mean_final_bankroll=np.mean(final_bankrolls),
        median_final_bankroll=np.median(final_bankrolls),
        p5_final_bankroll=np.percentile(final_bankrolls, 5),
        p95_final_bankroll=np.percentile(final_bankrolls, 95),
        mean_max_drawdown=np.mean(max_drawdowns),
        median_max_drawdown=np.median(max_drawdowns),
        prob_profitable=np.mean(final_bankrolls > initial_bankroll),
        prob_ruin=np.mean(final_bankrolls < initial_bankroll * ruin_threshold),
    )
```

### E. Expected Longest Losing Streak

```python
import math

def expected_longest_losing_streak(n_bets: int, win_rate: float) -> float:
    """
    Expected longest losing run over n_bets.
    ELLR = log(n) / -log(1 - win_rate)
    """
    loss_rate = 1.0 - win_rate
    return math.log(n_bets) / -math.log(loss_rate)

# Examples for golf betting:
# Matchups (55% win rate, 500 bets/year): ~11 losses in a row
# Outrights (10% hit rate, 100 bets/year): ~20 losses in a row
# Top 10 (30% hit rate, 200 bets/year): ~15 losses in a row
```

### F. CLV-Based Edge Significance Test

```python
import numpy as np
from scipy import stats

def clv_significance_test(clv_values: list[float]) -> dict:
    """
    Test whether mean CLV is significantly different from zero.
    
    Args:
        clv_values: List of CLV percentages for each bet
    
    Returns:
        Dict with t-statistic, p-value, and interpretation
    """
    n = len(clv_values)
    mean_clv = np.mean(clv_values)
    se = np.std(clv_values, ddof=1) / np.sqrt(n)
    t_stat = mean_clv / se
    p_value = 1 - stats.t.cdf(t_stat, df=n-1)  # One-sided test
    
    if p_value < 0.01:
        interpretation = "Strong evidence of edge"
    elif p_value < 0.05:
        interpretation = "Moderate evidence of edge"
    elif p_value < 0.10:
        interpretation = "Weak evidence of edge"
    else:
        interpretation = "No significant evidence of edge"
    
    return {
        "n_bets": n,
        "mean_clv": mean_clv,
        "standard_error": se,
        "t_statistic": t_stat,
        "p_value": p_value,
        "interpretation": interpretation,
    }
```

---

## Summary: Key Numbers to Remember

| Metric | Value |
|---|---|
| **Recommended Kelly fraction** | 0.25 - 0.50 (quarter to half Kelly) |
| **Max single bet** | 1-2% of bankroll |
| **Max per-player exposure** | 3-5% of bankroll |
| **Max per-tournament exposure** | 10-15% of bankroll |
| **Risk of ruin at half Kelly** | 1.83% |
| **Risk of ruin at quarter Kelly** | 0.03% |
| **P(ever halved) at half Kelly** | 12.5% |
| **P(ever halved) at quarter Kelly** | 0.78% |
| **Half Kelly growth vs full** | 75% of optimal |
| **Quarter Kelly growth vs full** | 44% of optimal |
| **Min bets to prove edge (CLV)** | ~50-150 bets |
| **Min bets to prove edge (results)** | ~1,000-3,000 bets |
| **Expected losing streak (55% WR, 1000 bets)** | ~15-16 in a row |
| **Recommended bankroll for golf model** | 200-500 units |
| **Drawdown trigger: reduce stakes** | -15% |
| **Drawdown trigger: freeze/audit** | -25% |

---

## Sources

- Chin, W. & Ingenoso, M. (2006). "Risk Formulae for Proportional Betting." DePaul University. (condor.depaul.edu/~wchin/riskpaper.pdf)
- Whitrow (2007). "Algorithms for Optimal Allocation of Bets on Many Simultaneous Events." JRSS Series C.
- Noma, E., Bai, Y., & Worlikar, M. (2013). "How Kelly Bet Size and Number of Bets Affect Max Drawdown."
- emiruz.com (2025). "Kelly Fractions for Independent Simultaneous Bets."
- McGinnis, W. (2026). "Bankroll Management with Keeks: Fractional Kelly."
- BettingIsCool (2026). "From Drawdown Nightmares to Monte Carlo Sims."
- sports-ai.dev (2024). "AI Bankroll Management: Kelly, Fractional & Risk Controls."
- betting-forum.com (2025). "Staking Beyond Flat & Kelly: Portfolio Thinking."
- EdgeSlip (2025). "CLV Betting: The Definitive Guide to Closing Line Value and ROI."
- Pinnacle Odds Dropper (2025). "Closing Line Value" (Joseph Buchdahl research).
- bet-pga.com (2026). "PGA Matchup Betting Strategy Guide."
- Golf Science Journal (2023). "Forecasters of Success: Atmospheric Conditions and Golfer Performance."
- Springer (2023). "Effect of Weather Conditions on Scores at the United States Masters."
- Fried Egg Golf. "Which Tee Times Got the Worst of the Draw at the Open?"
- Betlab.club. "How Betting Odds and Sample Size Impact ROI."
- Thorp, E.O. (2000). "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market."
- Boyd et al. (Stanford). "Risk-Constrained Kelly Gambling." (web.stanford.edu/~boyd/papers/pdf/kelly.pdf)
