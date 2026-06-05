# Frontend Overhaul — Handoff Index

Execution program for the golf-model SPA rebuild. **Do not mark complete without [Definition of Done](./DEFINITION_OF_DONE.md) evidence.**

| Section | Document |
|---------|----------|
| 01 Goals | [01-goals-and-non-negotiables.md](./01-goals-and-non-negotiables.md) |
| 02 Failure lessons | [02-current-state-and-failure-lessons.md](./02-current-state-and-failure-lessons.md) |
| 03 Design system | [03-target-ux-and-design-system.md](./03-target-ux-and-design-system.md) |
| 04 Routes | [04-route-by-route-implementation-spec.md](./04-route-by-route-implementation-spec.md) |
| 05 Rankings contract | [05-rankings-behavior-contract-upcoming-vs-live.md](./05-rankings-behavior-contract-upcoming-vs-live.md) |
| 06 Performance | [06-performance-and-stability-program.md](./06-performance-and-stability-program.md) |
| 07 QA gates | [07-test-strategy-and-quality-gates.md](./07-test-strategy-and-quality-gates.md) |
| 08 Rollout | [08-rollout-and-rollback-plan.md](./08-rollout-and-rollback-plan.md) |
| 09 Evidence | [09-evidence-packet-index.md](./09-evidence-packet-index.md) |
| 11 Monitoring V3 design | [11-monitoring-design-system.md](./11-monitoring-design-system.md) |
| 12 Deslop checklist | [12-deslop-checklist.md](./12-deslop-checklist.md) (signed 2026-06-05) |
| 13 Interaction / perf | [13-interaction-and-performance.md](./13-interaction-and-performance.md) |
| 14 Grading trust | [14-grading-trust-contract.md](./14-grading-trust-contract.md) |
| Prompts | [EXECUTION_PROMPTS.md](./EXECUTION_PROMPTS.md) |
| DoD checklist | [DEFINITION_OF_DONE.md](./DEFINITION_OF_DONE.md) |

## Verification commands

```bash
cd frontend && npm run typecheck
cd frontend && npm run test
cd frontend && npm run build
cd frontend && npm run bundle:budget
SCREENSHOT_MATRIX_VERSION=v3 SCREENSHOT_BASE_URL=http://127.0.0.1:8000 npm run screenshots:matrix:v3   # backend :8000
python3 -m pytest tests/ -v --tb=short
```

Gate log: [verification-2026-06-05.log](./verification-2026-06-05.log) (`feat/monitoring-v3-complete`).
