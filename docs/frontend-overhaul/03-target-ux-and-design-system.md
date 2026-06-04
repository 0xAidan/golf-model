# 03 — Target UX and Design System

## Visual direction
Operator terminal: flat, grid-aligned, semantic color only. Scan in under 3 seconds per screen.

## Layout (post-overhaul)
- **Desktop:** Fixed 3-column CSS grid — no drag handles.
- **Center column:** Tabbed boards (Top picks | Rankings | Markets | Leaderboard).
- **Left rail:** Tabbed intel sections.
- **Mobile:** Bottom nav + flat dashboard tabs (unchanged entry points).

## Design tokens
Source of truth: `frontend/src/styles/themes.css` + `terminal-visual-v2.css`.

## Shared components
| Component | Path | Use |
|-----------|------|-----|
| `EmptyState` | `components/ui/empty-state.tsx` | Tables, modules |
| `LoadingState` | `components/ui/feedback-state.tsx` | Query boundaries |
| `ErrorState` | `components/ui/feedback-state.tsx` | Failures with retry |
| `ProDataGrid` | `components/ui/pro-data-grid.tsx` | All dense tables |
| `CockpitSegmentTabs` | `components/cockpit/responsive-panels.tsx` | Board switching |

## Interaction replacements (drag → deterministic)
| Before | After |
|--------|-------|
| Column resize handles | Fixed grid proportions |
| Vertical panel drag | Segment tabs |
| Hidden board on desktop | Explicit tab labels + badges |

## Removed
- `react-resizable-panels` usage in cockpit (dependency may remain until cleanup PR).
