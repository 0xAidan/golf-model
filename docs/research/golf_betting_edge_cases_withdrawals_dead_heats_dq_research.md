# Research Report: Golf Betting Edge Cases — Withdrawals, Dead Heats, and DQs

**Compiled:** 2026-02-28  
**Scope:** Deep research on handling WD, DQ, and dead heat edge cases in golf betting models  
**Purpose:** Inform EV calculations, sportsbook rule handling, and prediction model design

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Sportsbook-by-Sportsbook Withdrawal Rules](#2-sportsbook-by-sportsbook-withdrawal-rules)
3. [Dead Heat Mathematical Formulas and Examples](#3-dead-heat-mathematical-formulas-and-examples)
4. [WD/DQ Probability Data and Modeling](#4-wddq-probability-data-and-modeling)
5. [Incorporating Edge Cases into EV Calculations](#5-incorporating-edge-cases-into-ev-calculations)
6. [Practical Code and Formula Examples](#6-practical-code-and-formula-examples)
7. [Sources](#7-sources)

---

## 1. Executive Summary

Golf betting models must account for three critical edge cases that materially affect expected value:

| Edge Case | Impact on EV | Model Action Required |
|-----------|--------------|------------------------|
| **Pre-tournament WD** | Bets voided/refunded | Model can ignore (no financial impact) |
| **Mid-tournament WD** | Bets typically lose (matchup: opponent wins) | Incorporate WD probability into matchup EV |
| **Dead heat** | Payout reduced proportionally | Simulate with ties; apply stake division to placement bets |
| **DQ** | Treated like WD at most books | Same as WD for modeling |

**Key findings:**
- **Withdrawal rules vary significantly by sportsbook** — FanDuel voids if player doesn't complete 3 holes; DraftKings stands once player tees off; BetMGM cancels bets placed between last round and withdrawal.
- **Dead heat frequency is material** — Estimates suggest 20–30% of Top 10 bets encounter dead heat; Top 20 and FRL markets see higher rates.
- **Simulating without ties yields incorrect EV** — DataGolf research shows break-even implied probabilities differ meaningfully when ties are excluded vs. included with dead-heat rules.
- **BetMGM pays ties in full** for some finishing position markets (at worse odds); most books use stake division.

---

## 2. Sportsbook-by-Sportsbook Withdrawal Rules

### 2.1 Pre-Tournament vs. Mid-Tournament Withdrawal

| Timing | Outcome |
|--------|---------|
| **Before tournament / before teeing off** | All bets **voided and refunded** |
| **After teeing off (Rounds 1–2)** | Withdrawal = **missed cut** → most bets **lose** |
| **After cut (Rounds 3–4)** | Make-cut bets stand; matchups where opponent missed cut stand; if both playing, withdrawal = **lose** |
| **Matchup: opponent withdraws** | You **win** if your player continues |

### 2.2 DraftKings

- **Action threshold:** Bets stand once players **tee off**
- **Withdrawal settlement:** Player completing **most holes** wins; if tied on holes, **lowest score** wins
- **3-ball / 2-ball:** If one player WD/DQ during round, other player(s) deemed winner
- **Dead heat:** Standard stake division

[Action Network](https://www.actionnetwork.com/golf/betting-rules-withdraw-disqualified), [Betting on Golf](https://betting-on-golf.com/dead-heat-guide/)

### 2.3 FanDuel

- **Action threshold:** Player must complete **3 holes** for bets to stand
- **Withdrawal before 3rd hole:** All bets **voided**
- **Withdrawal after 3 holes:** Standard rules (loss / opponent wins)
- **Dead heat:** Stake division

[Action Network](https://www.actionnetwork.com/golf/betting-rules-withdraw-disqualified)

### 2.4 BetMGM

- **Make/Miss Cut:** If player WD at any stage after starting → **loser**
- **Top 5/10/20:** If player does not start → cancelled; if starts then WD → **loser**
- **Tournament Match Bets:** If one player DQ/WD before cut or after both made cut → other player wins. If both WD before cut → cancelled. If both WD after cut → cancelled.
- **2-Ball / 3-Ball:** Once player has teed off, bets **stand** regardless of subsequent WD/DQ. If one WD/DQ during round → other player wins. Dead heat rules apply to 3-ball.
- **Mythical 2/3 Balls:** If one player WD/DQ during specified round → other player wins
- **Futures:** Cancelled/refunded if player WD **before** event start; stand once player tees off
- **Between-round withdrawal:** All bets on that golfer placed **between when they last played and when they withdrew** are **cancelled**
- **Dead heat:** Stake division; some "including ties" markets pay full odds at worse prices

[BetMGM Golf Rules](https://help.co.betmgm.com/en/sports-help/sports-house-rules/golf-wager-types-and-rules), [Action Network](https://www.actionnetwork.com/golf/betting-rules-withdraw-disqualified)

### 2.5 PointsBet

- **Action threshold:** Tee off
- **Withdrawal after teeing off:** **Loser** (not void)

[Action Network](https://www.actionnetwork.com/golf/betting-rules-withdraw-disqualified)

### 2.6 Bovada

- **Withdrawal after teeing off:** Wagers **losers** on all markets

[Bovada Golf Betting Rules](https://www.bovada.lv/help/common-faq/golf-betting-rules)

### 2.7 Bet365

- **Outright bets:** 36 holes minimum for action in 72-hole events
- **General void rules:** Abandoned events, incorrect participant info, technical errors, rule changes
- **Specific golf WD rules:** Less documented; follow standard "withdrawal = loss" for most markets

[Bet365 Void Rules](https://sportingaz.com/bet365-void-bet-rules/), [Odds Portal](https://www.oddsportal.com/reviews/bet365/golf/)

### 2.8 Summary Table: Matchup Bet Withdrawal Handling

| Sportsbook | When Bets Stand | WD = Void or Loss? |
|------------|-----------------|--------------------|
| DraftKings | Tee off | Loss (most holes / lowest score wins) |
| FanDuel | 3 holes completed | Void if <3 holes; loss otherwise |
| BetMGM | Tee off | Stand; opponent wins if one WD |
| PointsBet | Tee off | Loss |
| Bovada | Tee off | Loss |

---

## 3. Dead Heat Mathematical Formulas and Examples

### 3.1 Stake Division Method (Standard in US)

**Formula:**

```
Payout = (Stake × Winning_Positions / Total_Tied_Players) × (Decimal_Odds)
Return  = Payout + (Stake × Winning_Positions / Total_Tied_Players)
```

Or equivalently:

```
Winning_Stake = Stake × (Positions_Available / Tied_Players)
Return = Winning_Stake × (Odds + 1)
Profit = Return - Stake
```

**Break-even condition (2-way tie, 1 position):** At decimal odds 2.0, a dead heat yields zero profit. Below 2.0, a "winning" bet can be a net loss.

### 3.2 Reduction Factor

The **dead heat reduction factor** is:

```
Reduction_Factor = Winning_Positions / Total_Tied_Players
```

- 2-way tie for 1 position: 1/2 = 0.5  
- 3-way tie for 1 position: 1/3 ≈ 0.333  
- 4-way tie for 1 position: 1/4 = 0.25  
- 6-way tie for 3 positions: 3/6 = 0.5  

### 3.3 Worked Examples

**Example 1: Top 10, 3-way tie for 10th**

- Stake: $100, Odds: +180 (decimal 2.80)
- 3 players share 1 position → 1/3 of stake wins
- Winning portion: $33.33 × 2.80 = $93.33
- **Net result: $93.33 - $100 = -$6.67 (loss despite "winning" bet)**

**Example 2: Top 10, 4-way tie for 10th**

- Stake: $100, Odds: +200 (decimal 3.00)
- 4 players share 1 position → 1/4 of stake wins
- Winning portion: $25 × 3.00 = $75
- **Net result: $75 - $100 = -$25 (loss)**

**Example 3: Top 5, 6-way tie for 3rd**

- Stake: $50, Odds: +350 (decimal 4.50)
- 6 players share 3 positions → 3/6 = 0.5 of stake wins
- Winning portion: $25 × 4.50 = $112.50
- **Net result: $112.50 - $50 = +$62.50 (profit)**

**Example 4: FRL, 4-way tie for lead**

- Stake: $25, Odds: +4000 (decimal 41.00)
- 4 players share 1 position → 1/4 of stake wins
- Winning portion: $6.25 × 41.00 = $256.25
- **Net result: $256.25 - $25 = +$231.25 (profit)**

### 3.4 Odds Reduction Method (Some UK Books)

Some books reduce odds instead of stake:

```
Effective_Odds = Stated_Odds × (Winning_Positions / Total_Tied_Players)
```

For 2-way tie at +200: effective odds = +100. Outcomes are broadly similar to stake division.

### 3.5 Dead Heat Frequency by Market

| Market | Relative Dead Heat Frequency |
|--------|------------------------------|
| Top 5 | Lower |
| Top 10 | Medium (20–30% of bets affected) |
| Top 20 | Higher |
| FRL / Round Leader | High (single-round scoring clusters) |

[Betting on Golf](https://betting-on-golf.com/dead-heat-guide/), [PGA Tour](https://www.pgatour.com/article/news/betting-dfs/2024/01/04/dead-heat-understanding-how-ties-can-impact-your-golf-bets-and-profits)

---

## 4. WD/DQ Probability Data and Modeling

### 4.1 Historical WD/DQ Rates

- **PGA Tour withdrawals have decreased over time** (since FedEx Cup era, ~2007)
- Pre-tournament WD: ~45 instances in 22 events (2013–14) → ~94 projected for full season
- In-round WD: ~41 instances in 22 events (2013–14)
- Perception of "withdrawal epidemic" is not supported by data

[Golf Digest](https://www.golfdigest.com/story/fact-check-are-pros-really-wit)

### 4.2 Modeling WD/DQ in Predictions

Standard golf prediction models (DataGolf, KenPom-style) focus on **finish position among players who complete**; they do not explicitly model WD/DQ as a separate component. To incorporate WD/DQ:

1. **Estimate per-player WD rate** from historical data (starts vs. withdrawals)
2. **Condition matchup EV** on opponent WD: `EV = P(win) × (odds - 1) - P(loss) - P(opponent WD) × stake` when your player wins if opponent WD
3. **For placement bets:** WD = automatic loss → reduce effective win probability by `P(WD)`

### 4.3 DataGolf Methodology Note

DataGolf models use:
- Adjusted strokes-gained, 2-year + recent form
- Simulation with predicted + random component
- **Integer scores** (rounded) to produce ties — critical for dead heat accuracy

[DataGolf](https://datagolf.com/predictive-model-methodology/), [DataGolf Model Talk](https://datagolf.com/model-talk/who-cares-about-ties-part-2)

---

## 5. Incorporating Edge Cases into EV Calculations

### 5.1 Matchup Bets (Ties Void)

From DataGolf Model Talk, with `win_1`, `win_2`, `tie`:

**Break-even implied probability (ties void):**
```
1/odds_1 = win_1 / (win_1 + win_2)
```
The tie probability does **not** appear in this formula, but **how you model ties matters**: simulating without ties (e.g. continuous scores) overestimates break-even probability. Use integer/rounded scores.

### 5.2 Matchup Bets (Dead Heat Rules)

**Break-even implied probability (dead heat on ties):**
```
1/odds_1 = win_1 + tie/2
```
Ties are split 50/50 between players.

### 5.3 Placement Bets (Top 5/10/20)

1. **Simulate with ties** — Do not use continuous distributions; ties must be possible
2. **Apply dead heat reduction** to each simulated outcome where your player ties at the threshold
3. **Effective EV:**
   ```
   EV = Σ [ P(outcome_i) × Payout(outcome_i, dead_heat_rules) ] - 1
   ```
   where `Payout` uses the stake division formula

### 5.4 WD Probability Adjustment

For placement bets:
```
P_effective(place) = P(place | complete) × (1 - P(WD))
```
For matchups, if opponent WD → you win:
```
EV = P(you_win) × (odds - 1) + P(opponent_WD) × (odds - 1) - P(you_lose) × 1 - P(you_WD) × 1
```
(Simplify based on sportsbook rules; some books void if you WD before action threshold.)

---

## 6. Practical Code and Formula Examples

### 6.1 Dead Heat Payout Calculator (Python)

```python
def dead_heat_payout(
    stake: float,
    decimal_odds: float,
    tied_players: int,
    positions_available: int = 1
) -> tuple[float, float]:
    """
    Returns (total_return, profit).
    positions_available: e.g. 1 for "tied for 10th" in Top 10, 3 for "6-way tie for 3rd" in Top 5.
    """
    reduction_factor = positions_available / tied_players
    winning_stake = stake * reduction_factor
    total_return = winning_stake * decimal_odds
    profit = total_return - stake
    return total_return, profit


# Example: Top 10, 3-way tie for 10th, $100 at +180
ret, profit = dead_heat_payout(100, 2.80, 3, 1)
# ret ≈ 93.33, profit ≈ -6.67
```

### 6.2 Effective Odds After Dead Heat (for EV)

```python
def effective_decimal_odds(
    stated_decimal_odds: float,
    tied_players: int,
    positions_available: int = 1
) -> float:
    """Effective odds after dead heat reduction."""
    reduction = positions_available / tied_players
    return 1 + (stated_decimal_odds - 1) * reduction
```

### 6.3 Matchup EV with Tie Rules (Pseudocode)

```python
# win_A, win_B, tie from simulation
def matchup_ev(win_A: float, win_B: float, tie: float, odds_A: float, ties_void: bool) -> float:
    if ties_void:
        # Push on tie
        return win_A * (odds_A - 1) - win_B * 1  # tie contributes 0
    else:
        # Dead heat: tie pays half
        return win_A * (odds_A - 1) + tie * (odds_A / 2 - 0.5) - win_B * 1
```

### 6.4 Placement Bet EV with Dead Heat (Conceptual)

```python
# For each simulation outcome where player finishes Top 10:
# - If outright 1-9: full payout
# - If tied for 10th with n others: apply reduction factor 1/(n+1)
# Sum over all outcomes
def placement_ev(prob_by_outcome: dict, odds: float, stake: float) -> float:
    ev = 0
    for (outcome, prob) in prob_by_outcome.items():
        if outcome == "miss":
            ev -= prob * stake
        else:
            # outcome is (position, n_tied) e.g. (10, 3) for 3-way tie for 10th
            pos, n_tied = outcome
            reduction = 1 / n_tied if pos == 10 else 1  # simplify
            payout = stake * reduction * (odds + 1)
            ev += prob * (payout - stake)
    return ev
```

---

## 7. Sources

- [Action Network – Golf Betting Rules When a Player Withdraws, Gets Disqualified](https://www.actionnetwork.com/golf/betting-rules-withdraw-disqualified)
- [Action Network – What Happens to My Golf Bets if the Tournament Doesn't Finish?](https://www.actionnetwork.com/education/what-happens-to-my-golf-bets-if-the-tournament-doesnt-finish)
- [BetMGM – Golf Wager Types and Rules](https://help.co.betmgm.com/en/sports-help/sports-house-rules/golf-wager-types-and-rules)
- [Betting on Golf – Dead Heat Rules: Complete Payout Guide](https://betting-on-golf.com/dead-heat-guide/)
- [Betfair – Dead Heat Rules](https://support.betfair.com/app/answers/detail/403-exchange-what-happens-if-there-is-a-dead-heat)
- [Betfair – Dead Heat Calculator](https://betting.betfair.com/golf/dead-heat-calculator.html)
- [Bovada – Golf Betting Rules](https://www.bovada.lv/help/common-faq/golf-betting-rules)
- [DataGolf – Model Talk: Who cares about ties? Part II](https://datagolf.com/model-talk/who-cares-about-ties-part-2)
- [DataGolf – Predictive Model Methodology](https://datagolf.com/predictive-model-methodology/)
- [Golf Digest – Fact Check: Are pros really withdrawing more often?](https://www.golfdigest.com/story/fact-check-are-pros-really-wit)
- [PGA Tour – Dead heat: Understanding how ties can impact your golf bets](https://www.pgatour.com/article/news/betting-dfs/2024/01/04/dead-heat-understanding-how-ties-can-impact-your-golf-bets-and-profits)
- [Smarkets – Dead heat calculator](https://help.smarkets.com/hc/en-gb/articles/360002522132-Dead-heat-calculator)
- [SportingAZ – Bet365 Void Bet Rules](https://sportingaz.com/bet365-void-bet-rules/)
