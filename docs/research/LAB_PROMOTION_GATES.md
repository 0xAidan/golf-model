# Lab promotion gates

Research-driven features are implemented under **`model_variant == "v5"`** (lab / `lab_sandbox`). Nothing listed here promotes changes to the operator dashboard by default.

## Phase gates (pass all that apply before widening exposure)

### P0 — Data integrity foundation

- **Pass:** `evaluate_lab_data_integrity()` reports no blocking failures for representative tournaments; autoresearch data health `ok=True` for chosen years OR documented waiver.
- **Fail:** silent drops of metrics/field without logging; unexplained missing DG skill for large share of field.

### P1 — Core predictive upgrades (recency, variance, field context)

- **Pass:** AB lift vs frozen baseline on **≥2** independent windows for primary KPI (e.g. weighted ROI or calibration error — choose one primary per experiment).
- **Pass:** No CLV collapse vs baseline on matchups (segment table).
- **Fail:** lift on one window only; severe regression on weak-field or major segments.

### P2 — Course shot-fit / structural

- **Pass:** uplift on prespecified course archetypes OR neutral global with no tail harm.
- **Fail:** global regression or instability on courses without profile extensions.

### P3 — Matchup ties / settlement-aware EV

- **Pass:** replay sanity on tie-heavy samples; no contradiction with `src/scoring.py` dead-heat semantics for placement markets.
- **Fail:** EV ordering inversions on synthetic tie scenarios.

### P4 — In-play pressure (shadow)

- **Pass:** `INPLAY_ROUND_MATCHUPS_SHADOW` path only; documented sample counts; no staking path enabled.
- **Fail:** pressure feature affects non-shadow pricing.

## Operator dashboard promotion (explicit)

Promotion of any lab change to **baseline** dashboard (main `/` snapshot) requires:

1. Documented AB + soak period.
2. Explicit change to `COCKPIT_SNAPSHOT_MODEL_VARIANT` or profile merge — **out of scope** for automated lab implementation.
