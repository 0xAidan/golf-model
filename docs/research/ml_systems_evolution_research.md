# Production ML Systems That Evolve Over Time
## Research Report: Patterns for Self-Improving Prediction Systems

**Date:** 2026-02-28
**Focus:** Small-scale (solo developer, SQLite, weekly cadence) prediction system patterns

---

## Table of Contents

1. [Google's ML System Papers — Anti-Patterns & Rules](#1-googles-ml-system-papers)
2. [Data Flywheel Implementation](#2-data-flywheel-implementation)
3. [Feature Store Pattern](#3-feature-store-pattern)
4. [Model Registry & Experiment Tracking](#4-model-registry--experiment-tracking)
5. [A/B Testing Prediction Models](#5-ab-testing-prediction-models)
6. [Monitoring Prediction Quality Over Time](#6-monitoring-prediction-quality-over-time)
7. [Handling Concept Drift in Sports](#7-handling-concept-drift-in-sports)
8. [Reproducibility in ML Prediction Systems](#8-reproducibility-in-ml-prediction-systems)
9. [Synthesis: Architecture for a Small-Scale Self-Improving Prediction System](#9-synthesis)

---

## 1. Google's ML System Papers

### 1A. "Hidden Technical Debt in Machine Learning Systems" (Sculley et al., NIPS 2015)

**Core thesis:** ML systems accumulate massive hidden maintenance costs. Quick wins from ML are not free — they create ongoing technical debt at the *system level*, not just the code level. The ML code itself is a tiny fraction; the surrounding infrastructure (data collection, feature extraction, monitoring, serving) dominates.

#### Complete Anti-Pattern Taxonomy

**Entanglement (CACE Principle — Changing Anything Changes Everything)**
- In an ML model, no input is truly independent. Adding or removing a single feature changes the behavior of *all* features. You cannot isolate improvements.
- **Small-scale implication:** When you add a new feature to your golf model, you must re-evaluate ALL existing feature weights. Never assume adding a feature is purely additive.

**Correction Cascades**
- When model A's output feeds into model B as input, a small improvement to A can *degrade* B. Stacking models creates fragile chains where improvements are zero-sum.
- **Small-scale implication:** If you have a "course difficulty adjustment" model feeding into a "player performance" model, a change to course difficulty can silently break player performance predictions. Prefer a single unified model over cascaded models when possible.

**Undeclared Consumers**
- Systems or processes that silently consume your model outputs without your knowledge. If you save predictions to a shared file, someone (including your future self) might build on them without tracking that dependency.
- **Small-scale implication:** Document every place your predictions are used. Even in a solo project, your Discord bot output format, your analysis notebooks, and your reporting scripts are all consumers.

**Hidden Feedback Loops**
- *Direct loops:* The model's predictions influence future training data (e.g., if you only track players you predicted would do well, you bias your training set).
- *Indirect loops:* Two systems influence each other through shared data or environments without explicit connection.
- **Small-scale implication:** If you use model predictions to choose which tournaments to analyze more deeply, you create a direct feedback loop. Always collect outcome data for ALL predictions, not just the ones you acted on.

**Data Dependencies (Unstable, Underutilized, Static Analysis)**
- *Unstable data:* External data sources change format, meaning, or availability without notice.
- *Underutilized data:* Legacy features that no longer contribute but add pipeline complexity.
- **Small-scale implication:** The DataGolf API might change field names, add/remove stats, or change calculation methods. Version your raw data snapshots. Regularly audit which features actually matter.

**Glue Code**
- Masses of code to get general-purpose ML packages to work with your specific data. The `utils.py` anti-pattern.
- **Small-scale implication:** Resist the urge to dump transformation logic into catch-all utility files. Create specific, well-named transformation functions.

**Pipeline Jungles**
- Accumulation of data transformations that grow organically into an unmaintainable mess, especially as new data sources are added.
- **Small-scale implication:** Design your data pipeline top-down. When adding a new data source (e.g., strokes gained data), redesign the pipeline to incorporate it cleanly rather than bolting it on.

**Dead Experimental Codepaths**
- Abandoned experiments left in production code behind conditional flags. They rot, interact with live code in unexpected ways, and make debugging nightmarish.
- **Small-scale implication:** When an experiment doesn't work out, DELETE the code. Don't comment it out or hide it behind a flag. Git history preserves it if you need it.

**Configuration Debt**
- Model hyperparameters, feature flags, data source paths, and thresholds scattered across the codebase without centralized management.
- **Small-scale implication:** Use a single, validated configuration file (e.g., YAML or `.env`) for all tunable parameters. Never hardcode thresholds.

**External World Changes**
- The world changes and your model doesn't know. Player injuries, rule changes, course renovations, equipment regulations — none of these show up in your training data distribution metrics.
- **Small-scale implication:** Build explicit signals for known external changes (new season, rule change, course renovation) as features. Monitor prediction quality segmented by time period.

#### Cautionary Tales from the Paper
- Google Play had a stale lookup table for 6 months. Refreshing it alone gave a 2% install rate improvement — more than any other launch that quarter.
- A pipeline was copied from Google Plus "What's Hot" (which intentionally dropped old posts) to Google Plus Stream (where old posts matter). Nobody noticed the data was being dropped.

---

### 1B. Google's "Rules of Machine Learning" (Martin Zinkevich, 43 Rules)

**Core philosophy:** "Do machine learning like the great engineer you are, not like the great machine learning expert you aren't."

#### Most Relevant Rules for a Small-Scale Prediction System

**Phase 0 — Before ML:**
- **Rule #1: Don't be afraid to launch without ML.** Heuristics get you 50% of the way. Start with simple baselines (e.g., "predict a golfer finishes at their scoring average").
- **Rule #2: Design and implement metrics FIRST.** Track everything measurable before building any model. You need historical baselines to know if your model is improving.
- **Rule #3: Choose ML over a complex heuristic.** Simple heuristics are fine. Complex heuristics are unmaintainable. If your heuristic has 15 if/else branches, it's time for ML.

**Phase I — First Pipeline:**
- **Rule #4: Keep the first model simple, get infrastructure right.** The first model provides the biggest boost. A logistic regression with 5 good features beats a neural network with bad infrastructure.
- **Rule #5: Test infrastructure independently from ML.** Make sure data flows correctly before worrying about model accuracy.
- **Rule #7: Turn heuristics into features.** Your domain knowledge (e.g., "links courses favor certain players") should become model features, not hardcoded rules.
- **Rule #8: Know the freshness requirements.** How much does performance degrade with a week-old model? A month-old model? This determines your retraining schedule.
- **Rule #9: Detect problems before exporting models.** Sanity-check on held-out data before any model goes live.
- **Rule #10: Watch for silent failures.** Data sources going stale, feature coverage dropping — these degrade performance gradually and silently.
- **Rule #14: Start with interpretable models.** Linear/logistic regression makes debugging easier because predictions are interpretable as probabilities. Calibration is naturally checkable.

**Phase II — Feature Engineering:**
- **Rule #16: Plan to launch and iterate.** Your current model is not the last model. Design for easy feature addition/removal.
- **Rule #17: Start with directly observed features.** Use raw, observable stats (strokes gained, driving accuracy) before derived or learned features.
- **Rule #21: Feature count scales with data size.** With 1,000 examples, use ~12 features. With 1M examples, use thousands. Don't overparameterize.
- **Rule #22: Clean up unused features.** Features create technical debt. If a feature isn't helping, remove it.
- **Rule #24: Measure the delta between models.** Before A/B testing, compute how different the new model's predictions are from the old model's. Small delta = small impact.
- **Rule #26: Look for patterns in errors, create new features.** When your model gets predictions wrong, study why. The pattern often suggests a missing feature.
- **Rule #33: Test on future data.** If you train on data through January 5th, test on January 6th+. Never shuffle temporal data.

**Phase III — Plateaus:**
- **Rule #38: Don't add features if objectives are misaligned.** If your Brier score is good but your "who to bet on" recommendations are bad, the problem is the objective, not the features.
- **Rule #41: When performance plateaus, add qualitatively new data sources.** Don't refine existing signals endlessly. Add course history, weather data, player psychology indicators — genuinely new information.

---

### 1C. "Reliable Machine Learning" (Google, 2022) — Key Principles

**Core framework:** Apply Site Reliability Engineering (SRE) principles to ML systems.

**Key principles relevant to small-scale:**

1. **ML systems are continuous loops, never "done."** Data collection → training → evaluation → deployment → feedback → repeat. Plan for the loop, not a one-shot pipeline.

2. **Data Management Principles:** Treat data as both vital asset AND critical liability.
   - *Reliability:* Data should be consistently available
   - *Durability:* Data should survive failures (backups, checksums)
   - *Consistency:* Same query should return same result
   - *Version control:* Know what data produced what model
   - *Integrity:* Data should be correct and complete

3. **Model Validity:** Evaluate models through multiple lenses — offline metrics (Brier score), behavioral tests (does it rank known elite players highly?), and production monitoring (does prediction quality hold over time?).

4. **The ML Lifecycle Mental Model:**
   ```
   Define → Develop → Deploy → Monitor → Maintain → (back to Define)
   ```
   Every stage has its own failure modes. Most teams only invest in Develop.

---

## 2. Data Flywheel Implementation

### The Concept

A data flywheel is a closed-loop system where each prediction cycle generates data that improves the next cycle. It converts routine operations — predictions, outcomes, errors — into a self-reinforcing improvement engine.

### The Four-Stage Flywheel (from Tecton)

```
┌─────────┐    ┌─────────┐    ┌──────────┐    ┌─────────┐
│  DECIDE │───>│ COLLECT │───>│ ORGANIZE │───>│  LEARN  │
│ (predict)│    │(outcomes)│    │ (feature │    │(retrain)│
│         │<───│         │<───│  store)  │<───│         │
└─────────┘    └─────────┘    └──────────┘    └─────────┘
```

1. **Decide:** Model generates predictions using latest features
2. **Collect:** System logs actual outcomes (tournament results, player scores)
3. **Organize:** Outcomes are joined with predictions, structured into training data
4. **Learn:** Model is retrained on expanded dataset, new features are engineered from errors

### Implementation Pattern for Weekly Golf Predictions

```python
# Simplified flywheel architecture
class PredictionFlywheel:
    def __init__(self, db_path="golf_model.db"):
        self.db = sqlite3.connect(db_path)

    def predict(self, tournament_id, model_version):
        """Stage 1: Generate predictions and log them"""
        features = self.load_features(tournament_id)
        predictions = self.model.predict(features)
        self.log_predictions(tournament_id, predictions, model_version)
        return predictions

    def collect_outcomes(self, tournament_id):
        """Stage 2: Fetch actual results after tournament"""
        results = self.api.get_tournament_results(tournament_id)
        self.store_outcomes(tournament_id, results)
        self.join_predictions_to_outcomes(tournament_id)

    def organize(self):
        """Stage 3: Build training dataset from prediction-outcome pairs"""
        return self.db.execute("""
            SELECT p.features, p.prediction, o.actual_result,
                   p.prediction - o.actual_result as error,
                   p.model_version, p.tournament_id
            FROM predictions p
            JOIN outcomes o ON p.tournament_id = o.tournament_id
                AND p.player_id = o.player_id
            ORDER BY p.created_at
        """)

    def learn(self):
        """Stage 4: Retrain with expanded data, analyze errors"""
        training_data = self.organize()
        error_analysis = self.analyze_errors(training_data)
        new_model = self.retrain(training_data)
        self.log_model_performance(new_model, error_analysis)
        return new_model
```

### How Netflix Implements Their Flywheel

Netflix's recommendation system captures signals from every user interaction — titles started, completed, explicit ratings — and uses this to continuously refine recommendations. Key architectural decisions:

1. **Two-stage pipeline:** Candidate generation (recall-focused) → Ranking (precision-focused). Each stage can be independently improved.
2. **Foundation model approach:** Rather than many specialized models, they centralized member preference learning into a single foundation model that distributes learnings to specialized models via shared weights/embeddings.
3. **Engagement optimization:** They optimize for real-world engagement (retention, session length, completion) not just prediction accuracy. The flywheel is powered by behavioral outcomes, not predicted accuracy.

### Key Flywheel Metrics to Track

| Metric | What It Measures | Target Trend |
|--------|-----------------|--------------|
| Prediction count | Data volume in flywheel | Growing |
| Outcome join rate | % of predictions with resolved outcomes | > 95% |
| Error distribution | Where the model fails most | Narrowing |
| Retraining improvement | Lift from each retrain cycle | Positive (may diminish) |
| Feature discovery rate | New features found from error analysis | Steady |

### Cautionary Tales
- **Data quality > data quantity.** A flywheel on bad data accelerates in the wrong direction. Validate outcomes before they enter the training set.
- **Outcome delay problem.** In sports, you only learn the ground truth after the tournament ends (days/week delay). Your flywheel naturally operates on a weekly cycle.
- **Survivorship bias.** If you only collect detailed data for tournaments you predicted, you miss learning opportunities from tournaments you skipped.

---

## 3. Feature Store Pattern

### What Problem Does It Solve?

Features (the inputs to your model) tend to become scattered across notebooks, scripts, and ad-hoc SQL queries. A feature store centralizes feature computation, storage, and serving.

### Why This Matters Even at Small Scale

Without a feature store pattern, you end up with:
- Training/serving skew: Features computed differently in training vs. production
- Point-in-time errors: Using future data when computing historical features (data leakage)
- Duplication: Same feature computed multiple ways in different scripts
- No lineage: "Where did this feature come from? How was it calculated?"

### Small-Scale Feature Store with SQLite

You do NOT need Feast or Tecton. For a solo project with SQLite:

```python
# Feature store as a pattern, not a platform
# features.py — single source of truth for all feature definitions

FEATURE_REGISTRY = {
    "sg_total_l12": {
        "description": "Strokes gained total, last 12 rounds",
        "entity": "player",
        "sql": """
            SELECT player_id,
                   AVG(sg_total) as sg_total_l12
            FROM round_scores
            WHERE date >= date(?, '-90 days') AND date < ?
            GROUP BY player_id
        """,
        "version": 2,
        "created": "2026-01-15",
        "deprecated": False,
    },
    "course_history_avg": {
        "description": "Player average score at this course, last 3 years",
        "entity": "player_course",
        "sql": """
            SELECT player_id, course_id,
                   AVG(total_score) as course_history_avg
            FROM round_scores
            WHERE course_id = ?
              AND date >= date(?, '-1095 days') AND date < ?
            GROUP BY player_id, course_id
            HAVING COUNT(*) >= 4
        """,
        "version": 1,
        "created": "2026-02-01",
        "deprecated": False,
    }
}

class FeatureStore:
    def __init__(self, db):
        self.db = db

    def compute_feature(self, feature_name, as_of_date, **params):
        """Compute a feature as of a specific date (point-in-time correct)"""
        feature_def = FEATURE_REGISTRY[feature_name]
        return pd.read_sql(feature_def["sql"], self.db, params=[as_of_date, ...])

    def get_training_features(self, feature_list, as_of_date):
        """Get multiple features, all computed as of the same date"""
        frames = [self.compute_feature(f, as_of_date) for f in feature_list]
        return reduce(lambda a, b: a.merge(b, on="player_id"), frames)

    def log_feature_metadata(self, feature_name, as_of_date):
        """Track which features were used for which predictions"""
        self.db.execute("""
            INSERT INTO feature_log (feature_name, version, as_of_date, computed_at)
            VALUES (?, ?, ?, datetime('now'))
        """, (feature_name, FEATURE_REGISTRY[feature_name]["version"], as_of_date))
```

### Point-in-Time Correctness: The Critical Detail

The most important concept in feature stores. When computing features for a historical training example, you MUST only use data that was available at that point in time.

**Wrong:**
```python
# Uses ALL historical data — includes future information for older examples
avg_sg = df.groupby('player_id')['sg_total'].mean()
```

**Right:**
```python
# Only uses data available as of the prediction date
def compute_sg_as_of(player_id, as_of_date, lookback_days=90):
    return db.execute("""
        SELECT AVG(sg_total) FROM rounds
        WHERE player_id = ? AND date < ? AND date >= date(?, ?)
    """, (player_id, as_of_date, as_of_date, f'-{lookback_days} days'))
```

### Feature Versioning

When you change how a feature is calculated, increment the version:
```
sg_total_l12 v1: Simple average of last 12 rounds
sg_total_l12 v2: Weighted average with recency decay (half-life = 6 rounds)
```

Track which model version used which feature version. This is crucial for debugging regressions.

---

## 4. Model Registry & Experiment Tracking

### The Spectrum of Solutions

| Approach | Complexity | Best For |
|----------|-----------|----------|
| JSON metadata files in Git | Minimal | Solo projects, <10 experiments |
| RuneLog / Trackle | Low | Solo projects, >10 experiments |
| MLflow with SQLite backend | Medium | Solo projects wanting a UI |
| Weights & Biases | High | Teams, complex experiments |

### Recommended: JSON Metadata + Git (Minimum Viable Tracking)

For a solo weekly prediction project, enterprise MLOps is overkill. Here's the minimum viable approach:

```python
import json
from datetime import datetime
import hashlib

def log_model_run(model, features, metrics, predictions, config):
    """Log everything needed to reproduce and evaluate a model run"""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    metadata = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "model_type": type(model).__name__,
        "model_version": config.get("model_version"),
        "features_used": features,
        "feature_versions": {f: FEATURE_REGISTRY[f]["version"] for f in features},
        "hyperparameters": config.get("hyperparameters", {}),
        "training_data": {
            "date_range": config.get("training_date_range"),
            "n_examples": config.get("n_training_examples"),
            "data_hash": config.get("data_hash"),
        },
        "metrics": {
            "brier_score": metrics.get("brier_score"),
            "log_loss": metrics.get("log_loss"),
            "calibration_error": metrics.get("ece"),
            "top_10_accuracy": metrics.get("top_10_accuracy"),
        },
        "prediction_summary": {
            "tournament": config.get("tournament_name"),
            "n_players": len(predictions),
            "mean_prediction": float(predictions.mean()),
            "std_prediction": float(predictions.std()),
        },
        "random_seed": config.get("random_seed"),
        "code_commit": config.get("git_commit_hash"),
    }

    path = f"models/runs/{run_id}.json"
    with open(path, "w") as f:
        json.dump(metadata, f, indent=2)

    return run_id
```

**Directory structure:**
```
models/
├── runs/
│   ├── 20260215_103000.json   # Each run's metadata
│   ├── 20260222_093000.json
│   └── 20260301_100000.json
├── artifacts/
│   ├── model_v12.pkl          # Serialized model objects
│   └── model_v13.pkl
└── comparison.json            # Cross-run comparison summary
```

### When to Graduate to MLflow

Move to MLflow when:
- You have >20 experiments and JSON files get hard to compare
- You want visual comparison of metrics across runs
- You need model artifact versioning beyond simple pickle files

MLflow with SQLite is dead simple:
```python
import mlflow
mlflow.set_tracking_uri("sqlite:///mlflow.db")
mlflow.set_experiment("golf-predictions")

with mlflow.start_run(run_name="v13_added_weather"):
    mlflow.log_params({"model_type": "xgboost", "n_features": 24})
    mlflow.log_metrics({"brier_score": 0.18, "ece": 0.04})
    mlflow.sklearn.log_model(model, "model")
```

### What to Track (Non-Negotiable List)

1. **Data fingerprint:** Hash of training data to detect when data changes
2. **Feature list + versions:** Exactly which features, which version of each
3. **Hyperparameters:** Every tunable setting
4. **Metrics:** Brier score, calibration error, log loss, domain-specific metrics
5. **Random seed:** For reproducibility
6. **Code commit hash:** Which code version produced this model
7. **Prediction distribution:** Mean, std, min, max of predictions — catches silent failures
8. **Training data date range:** Temporal boundaries of training data

---

## 5. A/B Testing Prediction Models

### Shadow Mode: The Right Pattern for Predictions

Shadow mode is the preferred approach for prediction systems (vs. A/B testing which requires user interaction to validate). In shadow mode:

- The **production model** serves all real predictions
- The **shadow model** runs on the same inputs simultaneously
- Shadow predictions are **logged but never shown to users**
- After the outcome is known, both models are evaluated against ground truth

### Implementation: "Behind the API" Pattern

For a solo prediction system, the simplest shadow mode runs both models sequentially:

```python
class ShadowPredictor:
    def __init__(self, production_model, shadow_model, db):
        self.production = production_model
        self.shadow = shadow_model
        self.db = db

    def predict(self, tournament_id, features):
        """Run both models, return only production, log both"""
        prod_predictions = self.production.predict(features)
        shadow_predictions = self.shadow.predict(features)

        self.db.execute("""
            INSERT INTO shadow_log
            (tournament_id, player_id, prod_prediction, shadow_prediction,
             prod_model_version, shadow_model_version, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, ...)

        return prod_predictions  # Only production predictions are used

    def evaluate_shadow(self, tournament_id):
        """After outcomes are known, compare both models"""
        results = self.db.execute("""
            SELECT s.player_id,
                   s.prod_prediction, s.shadow_prediction,
                   o.actual_result
            FROM shadow_log s
            JOIN outcomes o ON s.tournament_id = o.tournament_id
                AND s.player_id = o.player_id
            WHERE s.tournament_id = ?
        """, (tournament_id,))

        prod_brier = brier_score(results.prod_prediction, results.actual_result)
        shadow_brier = brier_score(results.shadow_prediction, results.actual_result)

        return {
            "production_brier": prod_brier,
            "shadow_brier": shadow_brier,
            "improvement": prod_brier - shadow_brier,
            "promote_shadow": shadow_brier < prod_brier,
        }
```

### Shadow Mode Decision Framework

```
Shadow runs for N tournaments (recommend N >= 4-6 for golf)
                    │
           ┌────────┴────────┐
     Shadow better?      Shadow worse?
           │                  │
  Consistent across    Investigate why
  tournament types?    (course type? field
           │           strength? sample size?)
           │                  │
     Yes: Promote        Fix or discard
     No: Keep shadow     shadow model
         running
```

### When to Use A/B Testing Instead

A/B testing (splitting traffic between two models) is appropriate when:
- User behavior is needed to validate the model (e.g., "did the user act on the prediction?")
- You need to measure downstream business impact

For pure prediction accuracy, shadow mode is strictly better because:
- No users are ever exposed to a potentially worse model
- Both models are evaluated on identical inputs (no selection bias)
- Ground truth resolves both models simultaneously

### Promotion Criteria

Don't promote a shadow model based on a single tournament. Establish criteria:

```python
PROMOTION_CRITERIA = {
    "min_tournaments": 4,           # At least 4 weeks of shadow data
    "min_players_scored": 200,      # Meaningful sample size
    "brier_improvement_threshold": 0.005,  # Statistically meaningful improvement
    "no_regression_segments": True,  # Must not regress on any major segment
    "calibration_ece_max": 0.08,    # Must maintain good calibration
}
```

---

## 6. Monitoring Prediction Quality Over Time

### Core Metrics to Track

**Brier Score** (primary metric for probabilistic predictions):
- Measures mean squared error between predicted probabilities and outcomes
- Range: 0 (perfect) to 1 (worst)
- Interpretation: < 0.10 excellent, 0.10–0.20 good, 0.20–0.30 fair, > 0.30 poor
- "Punishes overconfidence and rewards calibration"

**Expected Calibration Error (ECE):**
- Average absolute difference between predicted probabilities and observed frequencies across probability bins
- ECE < 0.05 excellent, 0.05–0.10 acceptable, > 0.10 poor

**Reliability Curves:**
- Plot predicted probability (x-axis) vs. actual frequency (y-axis)
- Perfect calibration = diagonal line
- Deviations reveal systematic biases (e.g., model is overconfident in 60-80% range)

### Dashboard Design for Weekly Prediction Monitoring

```
┌─────────────────────────────────────────────────────┐
│ PREDICTION QUALITY DASHBOARD                         │
├──────────────────────┬──────────────────────────────┤
│ CURRENT TOURNAMENT   │ HISTORICAL TREND             │
│                      │                              │
│ Brier Score: 0.172   │ [Line chart: Brier score     │
│ ECE: 0.043           │  over last 20 tournaments]   │
│ Top-10 Hit Rate: 40% │                              │
│                      │ [Moving average overlay]     │
│ vs. Baseline: +0.02  │                              │
├──────────────────────┼──────────────────────────────┤
│ CALIBRATION CURVE    │ ERROR ANALYSIS               │
│                      │                              │
│ [Reliability diagram]│ Worst misses this week:      │
│                      │ 1. Player X (predicted 15th, │
│                      │    finished 65th)            │
│                      │ 2. Player Y (predicted 50th, │
│                      │    won tournament)           │
│                      │                              │
│                      │ Error by segment:            │
│                      │ - Top 20 OWGR: 0.14 Brier   │
│                      │ - 21-50 OWGR: 0.19 Brier    │
│                      │ - 50+ OWGR: 0.23 Brier      │
├──────────────────────┴──────────────────────────────┤
│ ALERTS                                               │
│ ⚠ Brier score has increased for 3 consecutive weeks │
│ ⚠ Calibration degraded in 30-50% confidence range   │
│ ✓ No data staleness detected                         │
└─────────────────────────────────────────────────────┘
```

### Alerting Rules (Simple Implementation)

```python
class PredictionMonitor:
    ALERT_RULES = {
        "brier_absolute": {
            "threshold": 0.25,
            "message": "Brier score exceeds 0.25 — model may be degraded"
        },
        "brier_trend": {
            "consecutive_increases": 3,
            "message": "Brier score increased 3 consecutive tournaments"
        },
        "calibration_drift": {
            "ece_threshold": 0.10,
            "message": "Calibration error exceeds 0.10 — recalibration needed"
        },
        "data_staleness": {
            "max_age_days": 14,
            "message": "Training data is more than 14 days old"
        },
        "prediction_distribution_shift": {
            "mean_shift_threshold": 0.05,
            "message": "Prediction mean shifted significantly — check input data"
        }
    }

    def check_alerts(self, current_metrics, historical_metrics):
        alerts = []
        if current_metrics["brier_score"] > self.ALERT_RULES["brier_absolute"]["threshold"]:
            alerts.append(self.ALERT_RULES["brier_absolute"]["message"])

        recent_brier = [m["brier_score"] for m in historical_metrics[-3:]]
        if all(recent_brier[i] < recent_brier[i+1] for i in range(len(recent_brier)-1)):
            alerts.append(self.ALERT_RULES["brier_trend"]["message"])

        return alerts
```

### Segmented Monitoring

Track metrics separately by:
- **Player tier:** Top-20 OWGR vs. mid-tier vs. lower-ranked
- **Course type:** Links vs. parkland vs. desert
- **Season phase:** Early season, major season, FedEx Cup playoffs
- **Field strength:** Strong fields vs. weak fields
- **Recency of player data:** Players with recent form data vs. returning from injury

This reveals WHERE the model degrades, not just THAT it degrades.

### Tools for Small Scale

**Evidently AI** (open-source Python):
```python
from evidently import Report
from evidently.presets import DataDriftPreset

report = Report(metrics=[DataDriftPreset()])
report.run(reference_data=training_features, current_data=new_features)
report.save_html("drift_report.html")
```

For a solo project, a simple approach is to compute metrics in your prediction script and append them to a SQLite table, then build a Streamlit dashboard.

---

## 7. Handling Concept Drift in Sports

### Types of Concept Drift in Golf

| Drift Type | Example | Detection Speed |
|-----------|---------|----------------|
| **Sudden** | Major rule change (anchored putting ban, distance rollback) | Fast — known date |
| **Gradual** | Player aging, game evolving toward distance | Slow — spans months/years |
| **Recurring** | Seasonal patterns, course-rotation effects | Periodic — predictable |
| **Incremental** | Course modifications, green speeds trending faster | Very slow — spans years |

### Golf-Specific Drift Sources

1. **Rule changes:** Equipment regulations, course setup changes (e.g., USGA distance rollback discussions)
2. **Player development:** Young players emerging, veterans declining
3. **Meta shifts:** The game increasingly favors power/distance over accuracy
4. **Course modifications:** Lengthened holes, new bunkers, green recontouring
5. **Field composition changes:** Tournament prestige shifts, LIV Golf player pool changes
6. **Data source changes:** New stats becoming available (ShotLink improvements), API field changes

### Detection Methods

**Page-Hinkley Test** — Best for sudden drift:
- Monitors cumulative deviation from running mean
- Triggers when deviation exceeds threshold
- Available in `scikit-multiflow`:
```python
from skmultiflow.drift_detection import PageHinkley

ph = PageHinkley(min_instances=30, delta=0.005, threshold=50)

for error in prediction_errors:
    ph.add_element(error)
    if ph.detected_change():
        print(f"Drift detected at observation {ph.n_samples}")
        # Trigger investigation / retraining
```

**ADWIN (Adaptive Windowing)** — Best for gradual drift:
- Maintains a variable-length window of recent observations
- Automatically shrinks when distribution changes detected
- No need to set window size manually
```python
from skmultiflow.drift_detection import ADWIN

adwin = ADWIN(delta=0.002)

for error in prediction_errors:
    adwin.add_element(error)
    if adwin.detected_change():
        print("Gradual drift detected")
        # Consider retraining with recent data weighted more heavily
```

**Conformal Martingales** — Best for statistical rigor:
- The `online-cp` Python package provides conformal test martingales for drift detection
- Tests exchangeability assumption — if data is no longer exchangeable with training data, drift is occurring
- More theoretically grounded than heuristic approaches

**Simple Rolling Window Comparison** — Best for small-scale:
```python
def detect_drift_simple(metrics_history, window_size=8, threshold=1.5):
    """Compare recent window to historical baseline using simple statistics"""
    if len(metrics_history) < window_size * 2:
        return False, "Insufficient data"

    recent = metrics_history[-window_size:]
    historical = metrics_history[:-window_size]

    recent_mean = np.mean(recent)
    hist_mean = np.mean(historical)
    hist_std = np.std(historical)

    z_score = (recent_mean - hist_mean) / (hist_std / np.sqrt(window_size))

    if abs(z_score) > threshold:
        return True, f"Drift detected: z={z_score:.2f}"
    return False, f"No drift: z={z_score:.2f}"
```

### Adaptation Strategies

**Strategy 1: Sliding Window Retraining**
- Always train on the most recent N tournaments only
- Pro: Automatically adapts to gradual drift
- Con: Loses long-term patterns, may overfit to recent noise

**Strategy 2: Weighted Retraining**
- Train on all data but weight recent data more heavily
- Use exponential decay: weight = exp(-λ × age_in_weeks)
- Pro: Balances historical patterns with recent trends
- Con: Requires tuning the decay parameter

**Strategy 3: Ensemble with Recency Split**
- Model A: Trained on all historical data (captures stable patterns)
- Model B: Trained on recent 6 months only (captures recent trends)
- Final prediction: Weighted average, with Model B weighted more heavily when drift detected
- Pro: Best of both worlds
- Con: More complexity to maintain

**Recommended for Golf (Strategy 2 + explicit drift signals):**
```python
def compute_sample_weights(dates, reference_date, half_life_weeks=26):
    """Exponential decay weights — half-life of 6 months"""
    age_weeks = (reference_date - dates).dt.days / 7
    weights = np.exp(-np.log(2) * age_weeks / half_life_weeks)
    return weights / weights.sum()

# Plus explicit features for known drift sources
DRIFT_FEATURES = [
    "is_post_rule_change",       # Binary: after a known rule change
    "season_phase",              # Categorical: early/mid/late/playoffs
    "weeks_since_course_change", # If course was recently modified
    "field_strength_index",      # Captures field composition drift
]
```

---

## 8. Reproducibility in ML Prediction Systems

### The Reproducibility Stack

```
Level 1: Code Reproducibility     → Git (version control)
Level 2: Data Reproducibility     → DVC or data snapshots
Level 3: Environment Reproducibility → requirements.txt / poetry.lock
Level 4: Execution Reproducibility → Random seeds + deterministic settings
Level 5: Result Reproducibility   → All of the above + model artifact storage
```

### Random Seed Management

```python
import random
import numpy as np
import os

def set_global_seed(seed: int = 42):
    """Set all random seeds for reproducibility"""
    random.seed(seed)
    np.random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)

    # If using scikit-learn, pass random_state to every estimator
    # If using XGBoost, set seed parameter
    # If using PyTorch/TensorFlow, set their seeds too

    return seed

# Store the seed with every model run
MODEL_SEED = set_global_seed(42)
```

**Critical: pass `random_state` explicitly to every stochastic operation:**
```python
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor

X_train, X_test = train_test_split(X, y, random_state=42)
model = RandomForestRegressor(n_estimators=100, random_state=42)
```

### Data Versioning for Small Scale

**Option A: Manual Snapshots (Simplest)**
```
data/
├── snapshots/
│   ├── 2026-02-15/          # Weekly snapshot
│   │   ├── player_stats.csv
│   │   ├── tournament_results.csv
│   │   └── manifest.json    # Hash + row counts + date range
│   ├── 2026-02-22/
│   └── 2026-03-01/
└── current/                  # Symlink to latest snapshot
```

```python
import hashlib

def snapshot_data(df, name, snapshot_dir):
    """Save a data snapshot with integrity metadata"""
    data_hash = hashlib.sha256(pd.util.hash_pandas_object(df).values.tobytes()).hexdigest()

    df.to_csv(f"{snapshot_dir}/{name}.csv", index=False)

    manifest = {
        "name": name,
        "hash": data_hash,
        "rows": len(df),
        "columns": list(df.columns),
        "date_range": {
            "min": str(df['date'].min()) if 'date' in df.columns else None,
            "max": str(df['date'].max()) if 'date' in df.columns else None,
        },
        "created_at": datetime.now().isoformat(),
    }
    return manifest
```

**Option B: DVC (When Data Gets Large)**
```bash
# Initialize DVC in your project
dvc init

# Track your data files
dvc add data/player_stats.csv
git add data/player_stats.csv.dvc .gitignore
git commit -m "Track player stats v1"

# When data updates
dvc add data/player_stats.csv
git add data/player_stats.csv.dvc
git commit -m "Player stats updated for week of 2026-03-01"

# Roll back to any previous version
git checkout HEAD~2 data/player_stats.csv.dvc
dvc checkout
```

### Environment Reproducibility

```bash
# Pin exact dependency versions
pip freeze > requirements.txt

# Or better, use a lock file approach
# pyproject.toml + poetry.lock
```

### The Complete Reproducibility Record

Every prediction run should store:

```json
{
  "run_id": "20260228_100000",
  "reproducibility": {
    "git_commit": "abc123def",
    "git_dirty": false,
    "python_version": "3.11.5",
    "random_seed": 42,
    "data_snapshot": "2026-02-22",
    "data_hash": "sha256:e3b0c44298...",
    "requirements_hash": "sha256:d7a8fbb307...",
    "model_artifact": "models/artifacts/model_v13.pkl",
    "feature_versions": {
      "sg_total_l12": 2,
      "course_history_avg": 1,
      "recent_form_index": 3
    }
  },
  "can_reproduce": true,
  "reproduction_command": "python predict.py --run-id 20260228_100000 --replay"
}
```

---

## 9. Synthesis: Architecture for a Small-Scale Self-Improving Prediction System

### Design Principles (Derived from Research)

1. **Start simple, add complexity only when plateau'd** (Google Rule #4, #41)
2. **Log everything, decide later what matters** (Google Rule #2)
3. **The flywheel is the product, not the model** (Netflix pattern)
4. **Point-in-time correctness is non-negotiable** (Feature store pattern)
5. **Shadow test before promoting** (Shadow mode pattern)
6. **Monitor segments, not just aggregates** (Calibration research)
7. **Make drift detection automatic** (ADWIN/Page-Hinkley)
8. **Every run must be reproducible** (Seed + data + code versioning)

### Recommended Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    WEEKLY PREDICTION CYCLE                     │
│                                                              │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐ │
│  │  DATA     │──>│ FEATURE  │──>│ PREDICT  │──>│ PUBLISH  │ │
│  │  INGEST   │   │  STORE   │   │ (shadow  │   │ (discord │ │
│  │ (API +    │   │ (SQLite  │   │  mode)   │   │  + logs) │ │
│  │  scrape)  │   │  + code) │   │          │   │          │ │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘ │
│       │                              │               │       │
│       v                              v               v       │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐               │
│  │  DATA     │   │ EXPERIMENT│   │ MONITOR  │               │
│  │  VERSION  │   │  TRACKER  │   │ (alerts  │               │
│  │ (snapshot │   │ (JSON +   │   │  + drift │               │
│  │  + hash)  │   │  SQLite)  │   │  detect) │               │
│  └──────────┘   └──────────┘   └──────────┘               │
│                                      │                       │
│                    ┌─────────────────┘                       │
│                    v                                         │
│  ┌──────────────────────────────────────────┐               │
│  │           FEEDBACK FLYWHEEL               │               │
│  │                                          │               │
│  │  Outcomes collected → Joined to preds    │               │
│  │  → Error analysis → Feature discovery    │               │
│  │  → Model retrained → Shadow tested       │               │
│  │  → Promoted if better                    │               │
│  └──────────────────────────────────────────┘               │
└──────────────────────────────────────────────────────────────┘
```

### What NOT to Do (Anti-Pattern Summary)

| Anti-Pattern | What It Looks Like | What to Do Instead |
|-------------|--------------------|--------------------|
| Pipeline jungle | 12 scripts called in sequence via bash | Single orchestrated pipeline |
| Glue code everywhere | 500-line utils.py | Specific, named transformation functions |
| No outcome tracking | Predictions made but never evaluated | Always log predictions + join to outcomes |
| Feature leakage | Using future data in training | Point-in-time feature computation |
| Configuration chaos | Hardcoded thresholds everywhere | Single config file, validated at startup |
| Dead experiments | Commented-out model variants in production | Delete dead code, Git preserves history |
| Silent staleness | Model trained on 6-month-old data | Staleness alerts in monitoring |
| Overengineering | Kubernetes + Feast + MLflow for 1 model | SQLite + JSON + Git |
| No calibration tracking | Only tracking accuracy | Brier score + ECE + reliability curves |
| Survivor bias in flywheel | Only analyzing tournaments you predicted | Collect outcomes for ALL events |

### Technology Stack Recommendation

| Component | Tool | Rationale |
|-----------|------|-----------|
| Database | SQLite | Single file, zero config, sufficient for weekly cadence |
| Feature store | Python code + SQLite | Feature definitions in code, data in SQLite |
| Experiment tracking | JSON metadata in Git | Minimal overhead, version-controlled |
| Model artifacts | Pickle files + Git LFS | Simple serialization |
| Data versioning | Weekly snapshots with hashes | DVC if data exceeds ~1GB |
| Drift detection | Simple rolling stats + ADWIN | Page-Hinkley for sudden drift |
| Monitoring | SQLite metrics table + Streamlit | Or simple HTML reports |
| Shadow testing | Python class comparing two models | No infrastructure needed |
| Reproducibility | Seeds + snapshots + git commits | Full traceability without enterprise tools |

---

## Sources

1. Sculley, D., et al. "Hidden Technical Debt in Machine Learning Systems." NIPS 2015. https://papers.nips.cc/paper/5656
2. Zinkevich, M. "Rules of Machine Learning: Best Practices for ML Engineering." Google. https://developers.google.com/machine-learning/guides/rules-of-ml
3. Chen, C., et al. "Reliable Machine Learning." O'Reilly, 2022.
4. McAteer, M. "Nitpicking Machine Learning Technical Debt." 2020. https://matthewmcateer.me/blog/machine-learning-technical-debt/
5. Gude, A. "Machine Learning Deployment: Shadow Mode." 2020. https://alexgude.com/blog/machine-learning-deployment-shadow-mode/
6. Tecton. "Managing the Flywheel of Machine Learning Data." https://tecton.ai/blog/managing-the-flywheel-of-machine-learning-data
7. Netflix Technology Blog. "Foundation Model for Personalized Recommendation." https://netflixtechblog.com/foundation-model-for-personalized-recommendation
8. Feast Documentation. https://docs.feast.dev
9. DVC Documentation. https://dvc.org/doc
10. Evidently AI. https://evidentlyai.com
11. "AI Model Calibration for Sports Betting: Brier Score & Reliability." https://www.sports-ai.dev/blog/ai-model-calibration-brier-score
12. Eliades et al. "Using inductive conformal martingales for addressing concept drift." PMLR, 2021.
13. "PGA TOUR Win Probability Model Powered by AWS." https://aws.amazon.com/blogs/media/pga-tour-win-probability-model-powered-by-aws
14. MLflow Documentation. https://mlflow.org/docs/latest/tracking.html
15. RuneLog. https://alexgonzalezc.dev/runelog/
