# Data Golf research index — taxonomy

**Companion:** [datagolf_enumeration.md](datagolf_enumeration.md) (how URLs are discovered; sitemap check; Analytics sidebar mechanics).

**CSV:** [datagolf_article_index.csv](datagolf_article_index.csv) — one row per URL; fill `summary_bullets` and `proposed_change` in your own words.

## `model_dimensions` (tag rows with one or more)

| ID | Typical code touchpoints |
|----|--------------------------|
| `data_ids` | `src/datagolf.py`, `src/player_normalizer.py`, rolling/backfill |
| `skill_sg_decomposition` | SG category weighting, `src/models/form.py` |
| `course_fit` | `src/models/course_fit.py`, course profiles |
| `form_recency` | `src/models/form.py` |
| `momentum` | `src/models/momentum.py` |
| `field_strength_tours` | Multi-tour / field quality |
| `simulation_variance` | `src/models/v5_probabilities.py`, `src/models/prob_engine_v1/` |
| `live_pressure` | Live / leaderboard pressure |
| `odds_market_efficiency` | `src/value.py`, `src/dynamic_blend.py`, calibration |
| `matchups_ties` | `src/matchup_value.py`, `src/matchups.py` |
| `calibration_grading` | `src/calibration.py`, `src/scoring.py` |
| `betting_ops` | `src/kelly.py`, `src/portfolio.py`, `src/clv.py` |
| `multiple` | Cross-cutting — split after reading |

## Lab vs cockpit (implementation)

- **Lab:** `/cockpit-lab`, profile `lab_sandbox` → `src/lab_profile.resolve_lab_model_variant` (typically **`v5`** in `profiles.yaml`).
- **Cockpit:** `COCKPIT_SNAPSHOT_MODEL_VARIANT` in `src/config.py` (typically **`baseline`**).

Research-driven code changes from this index should target **`v5` / lab** paths or variant-gated branches; do not change baseline cockpit behavior in the same pass unless explicitly intended.

## `source_family`

| Value | Meaning |
|-------|---------|
| `A` | `datagolfblogs.ca` (e.g. old blogs directory) |
| `B` | **`datagolf.com/blog`** — primary tagged listing (“load more”) for the Analytics feed |
| `C` | Root slugs, `/model-talk/`, `/viz-blog/`, optional `/blog-home/` extras — not a substitute for `/blog` |
| `D` | Expand later (other hosts / tools docs) |
