# Phase 1 — Information Architecture & Routes

## Operator mental model

| Nav item | Question it answers |
|----------|---------------------|
| **Dashboard** | What should I bet on with the production model right now? |
| **Lab** | What does the research model show, and how does it differ? |
| **Players** | Who is this player and what does the model think? |
| **Results** | How did our picks perform? Grade events and review track record. |
| **System** | Is the data fresh? What's the pipeline health? |

Dashboard and Lab remain **first-class lanes** — never merged under a generic "Models" toggle.

## Target routes

| Route | Status | Behavior |
|-------|--------|----------|
| `/` | Primary | Dashboard command center |
| `/lab` | Primary | Lab command center |
| `/players` | Primary | Player directory |
| `/results` | **New** | Grading + track record hub |
| `/system` | **New** | Diagnostics + data health hub |
| `/grading` | Alias | Redirect or render Results (grading tab) |
| `/track-record` | Alias | Redirect or render Results (track record tab) |
| `/research/diagnostics` | Alias | Redirect or render System |
| `/matchups` | Legacy | → `/?tab=full-picks` |
| `/lab/picks` | Legacy | → `/lab?tab=full-picks` |
| `/cockpit-lab` | Legacy | → `/lab` |

## Dashboard page sections (top → bottom)

1. Event command header — event, course, field, mode, lane badge, freshness
2. Trust/status strip — healthy, stale, degraded, split-brain, team event
3. Actionable plays — matchups first, secondary markets second
4. Rankings — readable table with live/upcoming column sets
5. Market diagnostics — funnel, reason codes when no plays
6. Player insight drawer — on row click
7. Results preview — latest graded event link

## Lab page sections (top → bottom)

1. Lab command header — lab lane badge, fallback warnings
2. Dashboard vs Lab comparison (when APIs support)
3. Lab actionable plays
4. Lab rankings
5. Research diagnostics (expandable)
6. Lab past/results preview

## Test ID preservation

- `monitoring-shell`, `monitoring-shell-main`, `monitoring-shell-drawer` — shell
- `nav-prediction`, `nav-lab-board`, `nav-players` — navigation
- `cockpit-tab-rankings` — board tabs (migrate to `model-section-rankings` with alias)
- `lab-board-banner`, `lab-board-prod-fallback-banner` — lab trust
