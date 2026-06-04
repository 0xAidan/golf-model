# Execution Prompts (ready to paste)

## UI Overhaul Agent

```
You own Workstream 1 (UI overhaul/design system).

Non-negotiables:
- Preserve route pathways and core functionality.
- Remove draggable resize handles and replace with clean deterministic interaction patterns.
- Implement a materially different polished UI on `/`, `/matchups`, `/players`, `/lab`, `/lab/picks`.
- Do not change backend API contracts.

Primary files:
- frontend/src/pages/prediction-workspace-page.tsx
- frontend/src/components/cockpit/workspace.tsx
- frontend/src/components/cockpit/cockpit-resizable-stack.tsx
- frontend/src/lib/cockpit-columns.tsx
- frontend/src/styles/themes.css
- frontend/src/styles/terminal-base.css
- frontend/src/components/ui/*

Required outputs:
1) Refactored UI architecture and components.
2) Explicit replacement of drag interactions with tabs/toggles/presets.
3) Before/after screenshot matrix.
4) Verification logs for typecheck/test/build.

Do not claim done without all outputs.
```

## Bug + Performance Agent

```
You own Workstream 2 (stability/performance/rankings correctness).

Non-negotiables:
- Restore upcoming rankings behavior expected before regression.
- Keep new live table behavior for live only.
- Make fallback/stale states explicit in UI.
- Improve or at minimum not regress runtime responsiveness.

Primary files:
- frontend/src/App.tsx
- frontend/src/lib/prediction-board.ts
- frontend/src/lib/api.ts
- frontend/src/hooks/use-prediction-tab.ts

Required outputs:
1) Upcoming/live table behavior contract enforced in code and tests.
2) Performance instrumentation baseline vs treatment.
3) Snapshot/rankings failure-state UX improvements.
4) Verification logs for typecheck/test/build.

Do not claim done without objective measurements and passing tests.
```

## Integration + QA Agent

```
You own Workstream 3/4 (QA, regression, accessibility, integration release gate).

Responsibilities:
- Execute route-by-route parity checks.
- Run screenshot matrix and produce evidence packet.
- Validate rankings behavior split (upcoming restored, live-only new behavior).
- Run accessibility checks and compile unresolved issues.
- Enforce anti-shortcut quality gates before merge/deploy recommendation.

Primary artifacts:
- frontend/scripts/capture-screenshot-matrix.mjs
- test logs, build logs, screenshot outputs
- PR checklist with pass/fail evidence links

Hard rule:
- If any mandatory gate fails, status must be BLOCKED, not DONE.
```
