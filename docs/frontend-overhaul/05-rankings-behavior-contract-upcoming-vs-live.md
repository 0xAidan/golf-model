# 05 — Rankings Behavior Contract (Upcoming vs Live)

## Column builders
| Mode | Builder | Columns |
|------|---------|---------|
| **Upcoming** | `buildUpcomingRankingsColumns` | #, Player, Composite, Form, Course fit, Momentum, SG Traj |
| **Live** | `buildLiveRankingsColumns` | Model now, Player, Start (model), Model Δ, Pos, Start pos, Pos Δ, To par, Composite |
| **Past** | `buildUpcomingRankingsColumns` | Same as upcoming (pre-tee-off replay semantics) |

## Data hydration rules
| Tab | Primary snapshot section | Fallback | Row source |
|-----|-------------------------|----------|------------|
| `upcoming` | `upcoming_tournament` | `live_tournament` → `legacy_tournament` | `rankings[]` only (never `live_player_board`) |
| `live` | `live_tournament` | `upcoming_tournament` → `legacy_tournament` | `live_player_board` when present, else `rankings[]` |

## UI labeling
- Upcoming title: **Power rankings**
- Live title: **Power rankings** + baseline labels from section
- Past title: **Pre-tee-off rankings**
- When hydration uses fallback section, show `hydration_source` banner in workspace.

## Automated tests (required)
- `cockpit-columns.test.ts`: upcoming columns exclude live-only headers; live columns include Model Δ / Pos Δ.
- `prediction-board.test.ts`: upcoming hydration never uses `live_player_board`; fallback section recorded.
- `prediction-workspace-page.test.tsx`: live mode renders live columns; upcoming renders model-centric columns.

## Backend note
Upcoming rankings may be empty when `eligibility.verified === false` (`dashboard_runtime.py`). UI must show eligibility warning, not a silent empty grid.
