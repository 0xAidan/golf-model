# Frontend verification — 2026-10-16

Local verification after the Rankings, Models and Performance reviewer fixes and the populated-market navigation change. No deployment, commits, production backend startup or live write requests were performed.

## Results

| Check | Command | Result |
| --- | --- | --- |
| Full unit/component suite | `npm --prefix frontend test` | 74 files, 488 tests passed; exit 0. |
| TypeScript | `npm --prefix frontend run typecheck` | Passed; exit 0. Rechecked after test configuration edits. |
| Production build | `npm --prefix frontend run build` | Passed; exit 0. |
| Entry bundle budget | `npm --prefix frontend run bundle:budget` | Passed. 76,226 gzip bytes; baseline 75,973; maximum 79,772 (+5%). Raw entry 241,245 bytes. |
| Accessibility | `PLAYWRIGHT_BASE_URL=http://127.0.0.1:5398 PLAYWRIGHT_SKIP_WEBSERVER=1 PLAYWRIGHT_BROWSER_CHANNEL=chrome npm --prefix frontend run test:a11y` | 7 tests passed, 21.5 seconds; zero critical axe violations on Rankings, Models, Performance, Lab, Players, Results and Compare. |
| Test configuration lint | `cd frontend && npx eslint e2e/a11y-monitoring.spec.ts playwright.config.ts` | Passed; exit 0. |

## Accessibility test isolation and repairs

The initial unchanged accessibility command failed all five tests before page load: its expected bundled Chromium executable `chromium_headless_shell-1223` was absent. No browser installation or download was required. `PLAYWRIGHT_BROWSER_CHANNEL=chrome` now selects the installed local Chrome through an optional configuration field; the default bundled-browser behavior remains unchanged.

The old root readiness check expected the superseded matchup headline. It now waits for the actual Rankings heading and reload button. Models and Performance were added to the existing axe checks. The accessibility spec requires a loopback base URL and intercepts every API request whose method is not GET, HEAD or OPTIONS with HTTP 405. It ran against the existing local read-only preview, with Playwright's backend web-server startup disabled.

## Withheld research state

During this verification the public learning report was `schema_version: 2`, `state: insufficient_data`, with empty source counts and explicit identity-repair reasons. The current learning-history report was `state: unavailable` with no runs. Models rendered its preserved original-model access and run-history section successfully under the axe check; the focused component suite also covers insufficient, malformed and error reports. This does not validate a corrected challenger evaluation, which is a separate publication step.

## Diagnostics and limits

The passing Vitest suite printed `ECONNREFUSED` requests to the happy-dom default `localhost:3000` and an aborted-fetch teardown diagnostic. These did not produce test failures. The build printed the existing large legacy chart-chunk warning and Node module-registration deprecation. Playwright printed Node deprecation and color-environment warnings.

The accessibility suite preserves its existing criterion of **zero critical** violations; it is not a claim of zero violations at every severity. Browser captures and design disposition remain the parent task's independent checks. No live placement, optimizer start, grading, pipeline trigger, retention, or mutation workflow was exercised.

## Subsequent v2 snapshot binding check

After the full verification above, a narrow projection guard was added for the corrected producer contract. V2 current-field projections now additionally require a resolved event, matching tour, an integer calendar year consistent with a valid official calendar-start date, and the exact captured snapshot timestamp. If the board supplies an explicit event year, it must agree. An explicit board tour takes precedence over the observed-tour eligibility value. No year is inferred from the capture date. V1 behavior, event-ID checks, field membership and model-hash checks remain in place.

The subsequent focused workspace/settings run passed **47 tests**, including 12 additional identity-binding cases. Typecheck and scoped ESLint passed. The full 488-test result above predates this narrow guard; the parent explicitly requested focused verification rather than repeating the full suite. The production build was repeated for the guard.

## Final finish evidence

The final reviewer cleared all seven scored fixes. The corrected, independently
reviewed model report is now present in the local build (one valid run, one
observed week; five invalidated runs remain preserved privately). A final skip-link
capture obstruction was fixed with the same unfocused clipping rule already
used in Markets. Browser keyboard verification confirmed the first Tab target
becomes visible on focus. Final build and bundle budget pass: 76,234 gzip bytes
against 79,772. No second detector was run. DESIGN.md and its sidecar were derived
from the finished source and ten final captures by a fresh documenter.
