# 04 — Route-by-Route Implementation Spec

| Route | Primary surface | Overhaul focus |
|-------|-----------------|----------------|
| `/` | Tabbed cockpit workspace | Grid layout, tabbed boards, upcoming/live rankings split |
| `/matchups` | Picks page | PageHeader, FilterBar, diagnostics collapse |
| `/lab` | Lab workspace + research aside | Lane banners, same cockpit patterns |
| `/lab/picks` | Lab picks tables | Lane labeling, log CTA |
| `/players` | Profile + field list | Collapsible sections, KPI strip |
| `/grading` | Event accordion | Records grid, season chart |
| `/track-record` | KPI + accordion | Pick-level expand |
| `/research/*` | Research pages | PageHeader consistency |

## Global shell (all routes)
- Event headline, Live/Upcoming/Past switcher, snapshot chip, grade, refresh
- Sidebar: Workspace / Records / Research
- Command menu (⌘K)

## data-testid preservation
All existing test IDs must remain. New: `cockpit-tab-*`, `hydration-fallback-banner`, `data-grid-loading`.
