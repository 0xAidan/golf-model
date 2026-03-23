# Edge tuner report artifact (report-only mode)

When `AUTORESEARCH_AUTO_APPLY` is **not** set (default), **research_cycle** does not write to the research champion registry. Search / Optuna trials may still persist to `output/research/` (ledger, Optuna DB). Operators review **reports** and merge changes into `autoresearch/strategy_config.json` manually.

## JSON shape (recommended for future tooling)

| Field | Meaning |
|----------|--------|
| `generated_at` | ISO 8601 UTC |
| `baseline` | Strategy snapshot (same resolution as live: `resolve_runtime_strategy`) — name, key params |
| `baseline_metrics` | Walk-forward summary: `weighted_roi_pct`, `weighted_clv_avg`, `total_bets`, guardrails |
| `candidate` | Best trial candidate (Optuna) or best proposal (research cycle) |
| `candidate_metrics` | Same metrics as baseline for comparison |
| `delta` | `{ "weighted_roi_pct": ..., "weighted_clv_avg": ... }` |
| `ledger_row` or `trial_id` | Pointer to `output/research/ledger.jsonl` or Optuna trial number |
| `feasible` / `guardrail_passed` | From evaluation |

## Objective alignment

Production success has been **matchup-first, high-EV tight lists** (see `docs/card_grading_report.md` and weekly cards). Scalar / walk-forward objectives should prefer **matchup-relevant** metrics (e.g. ROI on weighted walk-forward with matchup weighting) over generic blended leaderboard sorting alone.

## Environment

| Variable | Default | Effect |
|----------|---------|--------|
| `AUTORESEARCH_AUTO_APPLY` | unset / false | No `set_research_champion` / `approve_proposal` from **research_cycle** |
| `AUTORESEARCH_AUTO_APPLY=1` | — | Restores automatic champion updates when walk-forward rules pass |

Optuna MO/scalar studies do not promote to live registry by design; live promotion remains a separate explicit step.
