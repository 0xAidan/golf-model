# 05 — Rankings Behavior Contract (Upcoming vs Live)

## Column builders
| Mode | Builder | Columns |
|------|---------|---------|
| **Upcoming** | `buildUpcomingRankingsColumns` | #, Player, Composite, Form, Course fit, Momentum, SG Traj |
| **Live** | `buildLiveRankingsColumns` | Model now, Player, Start (model), Model Δ, Pos, Start pos, Pos Δ, To par, SG Traj, Composite |
| **Past** | `buildUpcomingRankingsColumns` | Same as upcoming (pre-tee-off replay semantics) |

## Data hydration rules
| Tab | Primary snapshot section | Fallback | Row source |
|-----|-------------------------|----------|------------|
| `upcoming` | `upcoming_tournament` | `live_tournament` → `legacy_tournament` | `rankings[]` only (never `live_player_board`) |
| `live` | `live_tournament` | `upcoming_tournament` → `legacy_tournament` | `live_player_board` when present, else `rankings[]` |

## Live row contract (E4–E6, E14, E17)

Each competitive live ranking row should expose:

| Field | Source | Notes |
|-------|--------|-------|
| `finish_state` | DB `rounds.fin_text` merged with in-play `current_pos` | `CUT`, `MC`, `MDF`, `WD`, `DQ`, `DNS` are inactive |
| `start_rank` | Frozen pre-tee-off or first live baseline | Stable within event |
| `current_rank` | Point-in-time model rank | Excludes inactive players when `exclude_cut_players` |
| `rank_delta` | `start_rank - current_rank` | Positive = improved |
| `momentum_trend` | Composite model and/or fresh live `round_sg_total` | Mapped into SG Traj on live board |
| `momentum_direction` | `hot` / `cold` / `neutral` | Derived from trend |
| `live_stats_*` | Section-level freshness metadata | See below |
| `market_provenance` | Matchup / value rows | `round_matchups`, `tournament_matchups`, `3_balls`, `outright`, `player_market` |
| `live_bettable` | Market availability gate | `true` only with current book line on supported live market |
| `last_seen_tick` | Snapshot id for bettable rows | Current refresh tick |

Eliminated players (`finish_state` inactive) are listed in `eliminated_players[]` without competitive rank numbers.

## Live point-in-time ranking formula (E5)

Inputs:

1. **Pre-tournament composite** — baseline skill from the verified field model.
2. **Data Golf in-play win probability** — when present, `adjusted = composite + 25 × win_prob`.
3. **Total-to-par** — when win prob missing, `adjusted = composite + 0.12 × (field_median_ttp − player_ttp)`.
4. **Fresh live stats** (E17) — when `live_stats_fresh`, add `+ 1.5 × round_sg_total` and `+ 0.02 × thru`.
5. **Finish state** — inactive players excluded when live mode is active.

Fallback: when no tournament signal exists (flat scores, no win prob), return pre-tournament composite ordering with source `live_point_in_time_pre_tournament_fallback`.

Walk-forward integrity: live ranks never use final tournament results from future rounds.

## Live model modes (E17)

| `live_model_mode` | Meaning |
|-------------------|---------|
| `full_live_stats` | Fresh in-play SG/score/thru stats accepted |
| `leaderboard_only` | Leaderboard / win prob only; stats disabled or missing |
| `stale_live_stats` | Stats present but outside freshness TTL |
| `no_live_stats` | No usable in-play stat rows |

## Market availability (E14)

- `is_new_since_last_snapshot` — row key first appeared vs previous snapshot.
- `is_new_live_opportunity` — new **and** `live_bettable=true` (badge must not imply book availability alone).
- 72-hole `tournament_matchups` are never `live_bettable` during live windows when gating is enabled.
- Actionable live matchups use `hydrateSnapshotMatchups()` which returns only `live_bettable` rows when `active=true`.

## Secondary markets (E15–E16, shadow-first)

- `live_groups_shadow` — 3-ball group probabilities; `shadow_only=true` until display flag + book line.
- `live_player_markets_shadow` — outright / placement from in-play win prob; shadow until book-verified.
- Gated by `LIVE_GROUPS_SHADOW`, `LIVE_GROUPS_DISPLAY_ENABLED`, `LIVE_PLAYER_MARKETS_SHADOW`, `LIVE_PLAYER_MARKETS_DISPLAY_ENABLED`.

## UI labeling
- Upcoming title: **Power rankings**
- Live title: **Power rankings** + baseline labels from section
- Past title: **Pre-tee-off rankings**
- When hydration uses fallback section, show `hydration_source` banner in workspace.
- When `live_model_mode !== full_live_stats`, show degraded-mode notice from `live_stats_warning`.

## Automated tests (required)
- `cockpit-columns.test.ts`: upcoming columns exclude live-only headers; live columns include Model Δ / Pos Δ / SG Traj.
- `prediction-board.test.ts`: upcoming hydration never uses `live_player_board`; live board preserves `momentum_trend`.
- `prediction-workspace-page.test.tsx`: live mode renders live columns; upcoming renders model-centric columns.
- `tests/test_live_refresh_runtime.py`: cut exclusion, point-in-time rank movement, live stats modes.
- `tests/test_live_market_availability.py`: 72-hole fallback not live bettable.
- `tests/test_live_stats_ingestion.py`: parser + freshness TTL.

## Backend note
Upcoming rankings may be empty when `eligibility.verified === false` (`dashboard_runtime.py`). UI must show eligibility warning, not a silent empty grid.
