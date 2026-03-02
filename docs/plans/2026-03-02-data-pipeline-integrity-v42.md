# Data Pipeline Integrity — v4.2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the six root causes found in the post-Cognizant audit: in-play odds contamination, phantom field players, probability renormalization, timestamp guards, single-snapshot enforcement, and clean backtesting.

**Architecture:** Add a pre-tournament timing gate to `run_predictions.py` that refuses to run after R1 tee time. Filter DG sim probabilities to confirmed-field-only players and renormalize them so they sum correctly. Enforce single-snapshot prediction logging (refuse to overwrite). Re-backtest Cognizant with clean pre-tournament-only data.

**Tech Stack:** Python 3, SQLite, existing `src/` modules.

---

## Context for Implementer

### Root causes (from the audit)

1. **In-play odds contamination**: The pipeline was run 3 times for the Cognizant Classic (Feb 23, Feb 26, Feb 28). Feb 28 was Round 3 — those are live in-play odds, not pre-tournament. All 6 v4.1 "value" bets used R3 in-play odds compared against static pre-tournament DG probabilities.
2. **Phantom field**: DG sim data has 182 players, actual field was 123. 66 phantom players (including Scheffler at 17.9% win prob) absorb 48.6% of outright probability.
3. **No probability renormalization**: After filtering phantoms, DG probabilities sum to ~51.4% for outrights instead of ~100%. The model uses raw deflated probabilities, systematically underestimating actual field players.
4. **No pre-tournament timing gate**: Nothing prevents `run_predictions.py` from executing mid-tournament.
5. **Silent overwrite**: `INSERT OR REPLACE` in `prediction_log` lets later (in-play) runs silently destroy earlier (pre-tournament) data.
6. **Backtest used contaminated data**: The v4.1 backtest script read all prediction_log entries without filtering by timestamp.

### Key files

| File | Role |
|------|------|
| `src/config.py` | Central config; will add timing/field settings |
| `src/value.py` | `_get_dg_probabilities()` — needs field filter + renormalize |
| `src/db.py` | `log_predictions()` — needs overwrite guard |
| `run_predictions.py` | Pipeline entry — needs timing gate |
| `src/datagolf.py` | `get_current_event_info()` — provides start_date |
| `scripts/backtest_v41_cognizant.py` | Needs clean-data rewrite |

---

## Task 1: Pre-Tournament Timing Gate

**Files:**
- Modify: `run_predictions.py` (near line 460, after `start_date` is parsed)
- Modify: `src/config.py` (add new constant)

**Why:** Prevent the pipeline from running after Round 1 has started. The DG schedule API returns `start_date` for the current event. If today >= start_date, the pipeline should warn and require an explicit `--force` flag.

**Step 1: Add config constant**

In `src/config.py`, after `PROBABILITY_SUM_TOLERANCE` (line 194), add:

```python
ALLOW_MID_TOURNAMENT_RUN = False
```

**Step 2: Add timing gate to run_predictions.py**

In `run_predictions.py`, after `start_date` is printed (around line 468), add a check:

```python
from datetime import date, datetime

if start_date:
    try:
        event_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        today = date.today()
        if today >= event_start and not config.ALLOW_MID_TOURNAMENT_RUN:
            force = "--force" in sys.argv
            if not force:
                print(f"\n  ⛔ BLOCKED: Tournament started {start_date}, today is {today}.")
                print("  Running mid-tournament produces in-play odds that corrupt EV calculations.")
                print("  Use --force to override (odds will be tagged as 'in_play').")
                sys.exit(1)
            else:
                print(f"\n  ⚠ WARNING: Running mid-tournament (--force). Odds tagged as in_play.")
                pipeline_ctx["odds_timing"] = "in_play"
        else:
            pipeline_ctx["odds_timing"] = "pre_tournament"
    except ValueError:
        pipeline_ctx["odds_timing"] = "unknown"
else:
    pipeline_ctx["odds_timing"] = "unknown"
```

**Step 3: Verify**

Run `python run_predictions.py` and confirm it either proceeds (if no current event is live) or blocks with the ⛔ message.

**Step 4: Commit**

```bash
git add src/config.py run_predictions.py
git commit -m "feat: add pre-tournament timing gate to prevent mid-event pipeline runs"
```

---

## Task 2: Filter DG Probabilities to Confirmed Field

**Files:**
- Modify: `src/value.py:117-173` (`_get_dg_probabilities`)
- Modify: `src/db.py` (use `get_all_players` for field list)

**Why:** `_get_dg_probabilities()` currently loads ALL sim data — including 66 phantom players not in the field. This must filter to confirmed field only.

**Step 1: Modify `_get_dg_probabilities` to accept and use field filter**

In `src/value.py`, change the function signature and add filtering:

```python
def _get_dg_probabilities(tournament_id: int, field_players: list[str] | None = None) -> dict:
    """
    Get Data Golf pre-tournament probabilities for confirmed field players.

    If field_players is provided, only returns probs for those players.
    Otherwise loads confirmed field from db.get_all_players().
    """
    sim_metrics = db.get_metrics_by_category(tournament_id, "sim")

    if field_players is None:
        field_players = db.get_all_players(tournament_id, confirmed_field_only=True)

    field_set = set(field_players) if field_players else None

    player_probs = {}
    for m in sim_metrics:
        pk = m["player_key"]

        if field_set and pk not in field_set:
            continue

        # ... (rest of existing parsing logic unchanged)
```

**Step 2: Wire field_players through find_value_bets**

The caller `find_value_bets` already knows the composite_results (which are field-filtered). Extract the player keys and pass them:

In `find_value_bets` (line 370-372), change:

```python
    dg_probs = {}
    if tournament_id:
        dg_probs = _get_dg_probabilities(tournament_id)
```

to:

```python
    dg_probs = {}
    if tournament_id:
        field_keys = [r["player_key"] for r in composite_results]
        dg_probs = _get_dg_probabilities(tournament_id, field_players=field_keys)
```

**Step 3: Commit**

```bash
git add src/value.py
git commit -m "feat: filter DG probabilities to confirmed field players only"
```

---

## Task 3: Renormalize DG Probabilities After Field Filter

**Files:**
- Modify: `src/value.py:117+` (`_get_dg_probabilities`)

**Why:** After removing 66 phantom players who absorbed 48.6% of outright probability, the remaining probabilities sum to ~51%. They need to be renormalized so the model's probability estimates reflect the actual field.

**Step 1: Add renormalization logic at the end of `_get_dg_probabilities`**

After building `player_probs` dict and before `return`, add:

```python
    # Renormalize: DG probs include phantom players not in field.
    # After filtering, probs sum to less than expected. Scale up so
    # outright probs sum to ~1.0, placement probs sum to expected values.
    EXPECTED_SUMS = {
        "outright": 1.0, "outright_ch": 1.0,
        "top5": 5.0, "top5_ch": 5.0,
        "top10": 10.0, "top10_ch": 10.0,
        "top20": 20.0, "top20_ch": 20.0,
        "make_cut": None, "make_cut_ch": None,  # skip — depends on cut line
    }

    # Compute current sums per bet type
    sums = {}
    for pk_probs in player_probs.values():
        for bt_key, prob in pk_probs.items():
            sums[bt_key] = sums.get(bt_key, 0.0) + prob

    # Compute scale factors
    scale_factors = {}
    for bt_key, expected in EXPECTED_SUMS.items():
        if expected is None or bt_key not in sums or sums[bt_key] < 0.01:
            continue
        current = sums[bt_key]
        # Only scale up (field filtering removes players, doesn't add them)
        # Cap scale factor at 3x to avoid extreme distortion from tiny fields
        factor = min(expected / current, 3.0) if current < expected else 1.0
        scale_factors[bt_key] = factor

    # Apply scale factors
    if scale_factors:
        for pk in player_probs:
            for bt_key in list(player_probs[pk].keys()):
                if bt_key in scale_factors:
                    player_probs[pk][bt_key] = min(
                        player_probs[pk][bt_key] * scale_factors[bt_key],
                        0.9999,
                    )

    return player_probs
```

**Step 2: Add logging**

Add a debug log line after computing scale_factors:

```python
    if scale_factors:
        logger.info("DG prob renormalization: %s", 
                     {k: f"{v:.2f}x" for k, v in scale_factors.items()})
```

**Step 3: Commit**

```bash
git add src/value.py
git commit -m "feat: renormalize DG probabilities after phantom field filtering"
```

---

## Task 4: Prevent Prediction Log Overwrite (Single-Snapshot)

**Files:**
- Modify: `src/db.py:1084-1098` (`log_predictions`)

**Why:** `INSERT OR REPLACE` lets a mid-tournament pipeline run silently destroy pre-tournament prediction data. Change to `INSERT OR IGNORE` so the first (pre-tournament) snapshot is preserved.

**Step 1: Change INSERT behavior**

In `src/db.py`, `log_predictions()` function (line 1089-1095), change:

```python
    conn.executemany(
        """INSERT OR REPLACE INTO prediction_log
```

to:

```python
    conn.executemany(
        """INSERT OR IGNORE INTO prediction_log
```

**Step 2: Add a function to check if predictions already exist**

After `log_predictions`, add:

```python
def has_predictions(tournament_id: int) -> bool:
    """Check if prediction_log already has entries for this tournament."""
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM prediction_log WHERE tournament_id = ? LIMIT 1",
        (tournament_id,),
    ).fetchone()
    conn.close()
    return row is not None
```

**Step 3: Warn in run_predictions.py when predictions already exist**

In `run_predictions.py`, before calling `log_predictions_for_tournament` (around line 1252), add:

```python
    if db.has_predictions(tid):
        print("\n  ℹ Predictions already logged for this tournament — skipping (single-snapshot rule).")
        print("    To re-log, delete existing entries first: DELETE FROM prediction_log WHERE tournament_id = ?")
    elif value_bets:
```

(and indent the existing block under the `elif`)

**Step 4: Commit**

```bash
git add src/db.py run_predictions.py
git commit -m "feat: single-snapshot prediction logging — refuse to overwrite pre-tournament data"
```

---

## Task 5: Tag Odds with Timing Metadata

**Files:**
- Modify: `src/db.py` — add `odds_timing` column to prediction_log
- Modify: `src/learning.py:131+` (`log_predictions_for_tournament`)
- Modify: `run_predictions.py` — pass timing context

**Why:** Even if we block mid-tournament runs by default, we need to know which odds are pre-tournament vs in-play for any historical analysis. Tag each prediction with its timing context.

**Step 1: Add column migration**

In `src/db.py`, find `ensure_schema()` or the equivalent schema creation. Add an ALTER TABLE to add `odds_timing TEXT` column to `prediction_log` if it doesn't exist:

```python
def _migrate_prediction_log_timing(conn):
    """Add odds_timing column if missing."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(prediction_log)").fetchall()]
    if "odds_timing" not in cols:
        conn.execute("ALTER TABLE prediction_log ADD COLUMN odds_timing TEXT DEFAULT 'unknown'")
        conn.commit()
```

Call this from `get_conn()` or `ensure_schema()`.

**Step 2: Update log_predictions to accept odds_timing**

In `src/learning.py`, `log_predictions_for_tournament`, add `odds_timing` parameter:

```python
def log_predictions_for_tournament(tournament_id: int,
                                   value_bets_by_type: dict,
                                   odds_timing: str = "unknown") -> int:
```

And include it in each prediction dict:

```python
            predictions.append({
                ...existing fields...,
                "odds_timing": odds_timing,
            })
```

**Step 3: Update the INSERT in db.py to include odds_timing**

In `log_predictions()`:

```python
    conn.executemany(
        """INSERT OR IGNORE INTO prediction_log
           (tournament_id, player_key, bet_type, model_prob, dg_prob,
            market_implied_prob, actual_outcome, odds_decimal, profit, odds_timing)
           VALUES (:tournament_id, :player_key, :bet_type, :model_prob, :dg_prob,
                    :market_implied_prob, :actual_outcome, :odds_decimal, :profit, :odds_timing)""",
        predictions,
    )
```

**Step 4: Pass timing from run_predictions.py**

At the `log_predictions_for_tournament` call:

```python
        n_logged = log_predictions_for_tournament(
            tid, value_bets,
            odds_timing=pipeline_ctx.get("odds_timing", "unknown"),
        )
```

**Step 5: Commit**

```bash
git add src/db.py src/learning.py run_predictions.py
git commit -m "feat: tag prediction_log entries with odds_timing metadata"
```

---

## Task 6: Clean Cognizant Backtest (Pre-Tournament Data Only)

**Files:**
- Modify: `scripts/backtest_v41_cognizant.py` → rename to `scripts/backtest_v42_cognizant.py`

**Why:** The v4.1 backtest was fundamentally flawed because it used a mix of pre-tournament and in-play odds. This rewrite uses ONLY Feb 26 (pre-tournament) odds and applies field-filtered + renormalized DG probabilities.

**Step 1: Rewrite the backtest to filter by timestamp**

Key changes to `load_predictions()`:

```python
def load_predictions() -> list[dict]:
    """Load ONLY pre-tournament predictions (earliest timestamp)."""
    conn = get_conn()
    
    # Find the earliest timestamp for this tournament
    earliest = conn.execute(
        "SELECT MIN(created_at) FROM prediction_log WHERE tournament_id = ?",
        (TOURNAMENT_ID,),
    ).fetchone()[0]
    
    if not earliest:
        print("  No predictions found!")
        return []
    
    earliest_date = earliest[:10]  # YYYY-MM-DD
    print(f"  Using predictions from: {earliest_date} (pre-tournament)")
    
    rows = conn.execute(
        """SELECT player_key, bet_type, model_prob, dg_prob,
                  market_implied_prob, odds_decimal
           FROM prediction_log 
           WHERE tournament_id = ? AND created_at LIKE ?""",
        (TOURNAMENT_ID, earliest_date + "%"),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

**Step 2: Apply field filter and renormalization to DG probs**

In `load_dg_probs()`, filter to `ALL_IN_FIELD` and renormalize:

```python
def load_dg_probs() -> dict:
    """Load DG sim probs, filtered to confirmed field and renormalized."""
    # ... existing loading logic ...
    
    # Filter to confirmed field
    filtered = {pk: probs for pk, probs in all_probs.items() if was_in_field(pk)}
    
    # Renormalize
    EXPECTED = {"outright": 1.0, "outright_ch": 1.0,
                "top5": 5.0, "top5_ch": 5.0,
                "top10": 10.0, "top10_ch": 10.0,
                "top20": 20.0, "top20_ch": 20.0}
    
    sums = {}
    for pk_probs in filtered.values():
        for key, prob in pk_probs.items():
            sums[key] = sums.get(key, 0.0) + prob
    
    for pk in filtered:
        for key in list(filtered[pk].keys()):
            expected = EXPECTED.get(key)
            current = sums.get(key, 0)
            if expected and current > 0.01 and current < expected:
                factor = min(expected / current, 3.0)
                filtered[pk][key] = min(filtered[pk][key] * factor, 0.9999)
    
    return filtered
```

**Step 3: Run and compare**

```bash
python scripts/backtest_v42_cognizant.py
```

Compare results:
- v4.0 (contaminated data): 1-22, -16.0u
- v4.1 (still contaminated): 0-6, -6.0u  
- v4.2 (clean pre-tournament data, field-filtered, renormalized): ?

**Step 4: Commit**

```bash
git add scripts/backtest_v42_cognizant.py
git commit -m "feat: clean backtest with pre-tournament-only odds and field-filtered DG probs"
```

---

## Task 7: Update Config Version and Final Verification

**Files:**
- Modify: `src/config.py` (version bump)

**Step 1: Bump version**

```python
MODEL_VERSION = "4.2"
```

**Step 2: Run the full pipeline in dry-run mode**

```bash
python run_predictions.py
```

- If a tournament is live, confirm the ⛔ gate blocks execution
- If no tournament is live, confirm it proceeds normally

**Step 3: Commit all and push as PR**

```bash
git add -A
git commit -m "chore: bump model version to 4.2"
git push -u origin feat/v42-data-pipeline-integrity
```

Create PR summarizing the 6 root causes and the fixes.

---

## Summary of Changes

| Fix | What | Where |
|-----|------|-------|
| Timing gate | Block pipeline after R1 starts | `run_predictions.py`, `config.py` |
| Field filter | DG probs filtered to confirmed field only | `src/value.py` |
| Renormalization | Scale DG probs to correct sums after filter | `src/value.py` |
| Single-snapshot | `INSERT OR IGNORE` prevents overwrite | `src/db.py` |
| Odds tagging | Each prediction tagged pre_tournament/in_play | `src/db.py`, `src/learning.py` |
| Clean backtest | Uses only pre-tournament data + field filter | `scripts/backtest_v42_cognizant.py` |
| Version bump | v4.1 → v4.2 | `src/config.py` |
