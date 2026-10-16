# Experience delivery and request audit

Measured 2026-10-14 02:08–02:15 UTC (October 13, 22:08–22:15 EDT).
Source checkout: `/Users/aidannugent/websites/golf-model`; production application:
`/opt/golf-model`; isolated report service: `/opt/golf-evidence/current`.

## Scope and status

The audit used a small number of HTTP GETs, file reads, service metadata reads,
and one bounded read-only SQLite metadata lookup. Audit scripts imported no
application/model modules and ran no initialization commands, grading, migration,
or model jobs. This is not a load test or a percentile benchmark.

**Live change, completed by the parent deployment agent:** Caddy compression
enabled only for the golf virtual host. Caddy configuration validated and Caddy
reloaded successfully; the dashboard and model workers were not restarted.
Preserved configuration:
`/etc/caddy/Caddyfile.pre-experience-20261014T021411Z`.

**Frontend release deployed at 02:32:16 UTC:** legacy snapshot polling/request
coordination, route-scoped requests, bounded reads, deferred telemetry and
selected-pick sharing. Release `matchup-desk-20261013-experience-v2` serves code
commit `aeb35f5`. The [delivery report](2026-10-13-delivery.md) records hashes,
rollback and public verification. No main backend code or service was changed.

## Measurements

| Request | Loopback service time, two samples | Public cold TTFB / total | Payload before Caddy change |
| --- | ---: | ---: | ---: |
| `/api/desk/board?track=champion&mode=upcoming` | 58.64 / 30.77 ms | 0.658 / 1.233 s | 100,017 bytes, uncompressed |
| `/api/desk/board?track=champion&mode=live` | not sampled | 0.612 / 0.612 s | 1,080 bytes, empty live state |
| `/api/market-evidence?lane=dashboard` | 51.97 / 35.23 ms | 0.671 / 0.806 s | 10,710 bytes, uncompressed |
| Existing `/api/live-refresh/status` | 47.11 / 55.42 ms | not sampled publicly | 118,262 decoded bytes |
| Main application HTML `/` | 2.17 / 1.51 ms | 0.684 / 0.684 s | 584 gzip bytes; 1,276 decoded |

A separate four-request curl session reused the public HTTP/2 connection:
the first board took 1.143 seconds including connection setup; the second took
0.240 seconds. Two subsequent evidence requests took 0.271 and 0.292 seconds.
Cold TCP plus TLS cost approximately 0.38–0.49 seconds in these client samples.
These observations distinguish network setup/transfer cost from server work;
they do not establish a global latency distribution.

The host was lightly loaded: load average approximately 0.05. The existing
dashboard process remained PID 774128 with its serving child PID 774129;
the serving child used about 165MiB RSS. The sidecar was about 30MiB RSS.
There was no evidence of a saturated CPU in this measurement window.

### Compression before and after

The golf Caddy host proxied report requests directly to port 8011, bypassing the
main application's GZipMiddleware. The host lacked its own `encode` directive.
Both report endpoints therefore returned uncompressed JSON even to clients
advertising compression. Local compression of the sampled board produced
9,376 bytes from 100,017 bytes, showing substantial repetitive structure.

The parent deployment agent enabled:

```caddyfile
golf.shermandavison.com {
    encode zstd gzip
    # Existing request guards and handlers retained.
}
```

Its post-reload public `curl --compressed` checks measured:

| Endpoint | Pre-change wire bytes | Post-change wire bytes | Reduction |
| --- | ---: | ---: | ---: |
| Upcoming desk board | 100,017 | 9,718 | 90.3% |
| Dashboard evidence | 10,710 | 2,102 | 80.4% |

Both individual post-change cold checks completed in approximately 0.568
seconds. Do not interpret those single samples as a controlled latency
benchmark. Decoded JSON and headers were retained by the deployment agent in
`/tmp/golf-experience-board.json`, `/tmp/golf-experience-evidence.json`, and its
corresponding header captures. Content and `Cache-Control: no-store` remain
unchanged; only transfer encoding changed.

Static assets already had gzip and
`Cache-Control: public, max-age=31536000, immutable`. The sampled entry JS was
75,823 compressed bytes / 240,545 decoded bytes; CSS was 22,242 / 130,304 bytes.
Preserve these asset caching rules. The HTML shell intentionally uses no-store
to discover new asset hashes after releases.

## Request architecture findings

1. **Legacy screens requested overlapping full snapshots.**
   `LiveSnapshotProvider` requested both `/api/live-refresh/summary` and
   `/api/live-refresh/snapshot` every ten seconds. The summary is not a small
   status object: `app.py:get_live_refresh_summary` includes the complete
   snapshot. The snapshot file was 1,143,379 bytes, with both Champion and Lab
   sections. Reading and parsing it once took about 12.3ms. Each legacy request
   may read it again while assembling runtime status.

2. **Worker liveness incorrectly selected the fastest status polling.**
   The provider used `status.running` to choose its 2.5-second interval. A
   healthy long-lived worker remains running between hourly recomputes, so idle
   screens also used that cadence. Status includes a persisted grading report:
   the read-only lookup of `live_refresh_last_auto_grade` showed a
   116,304-byte `last_auto_grade_status`, roughly 98% of the status response.
   `get_live_refresh_status()` also parses the snapshot and reads metadata;
   the application wrapper checks the worker using a `ps` subprocess and
   repeats runtime identity checks. This is unnecessary work for a small
   liveness indicator.

3. **Status cache identities differed across screens.**
   The provider used `['live-refresh-status', manualRefreshPending]`, while
   other tools used `['live-refresh-status']`. This prevents request/cache
   sharing and creates another query when manual refresh changes state.

4. **Unchanged snapshots were repeatedly serialized into browser storage.**
   Snapshot envelope age changes every poll. The persistence effect depended
   on the entire envelope and wrote its large snapshot to both sessionStorage
   and IndexedDB even when the snapshot itself was unchanged.

5. **Read routes still have application lifecycle coupling.**
   The existing status, summary, snapshot, dashboard-state, and past routes
   call `ensure_initialized`. The current snapshot endpoint can also invoke
   embedded runtime startup when explicitly configured. These routes should
   not be treated as intrinsically read-only just because they use GET.
   Additional model-related endpoint probes were avoided after source review.
   The isolated desk/evidence service has no such application imports.
   Removing lifecycle/initialization work from request handlers is a future
   architecture task, not justification to restart the protected application.

6. **The isolated reports are bounded and currently quick.**
   Board requests read a bounded snapshot and derive freshness on every call.
   Evidence uses SQLite URI `mode=ro`, `query_only`, a consistent read
   transaction, row/text/time bounds, and no application initialization.
   Four report slots are shared; excess simultaneous report work receives 503.
   Both routes currently recompute their small projections per request. These
   limits are reasonable safeguards; no production concurrency stress test
   was performed.

7. **The board has a larger DTO than the first screen uses.**
   Rankings account for 94,481 of 100,017 bytes (72 players); picks account for
   4,446 bytes. The desk's field preview renders only the first five rankings.
   Compression removes most transfer cost immediately. A future compact desk
   projection can reduce parsing/memory work further while keeping the full
   player/research endpoints available.

## Frontend change

Owned files:

- `frontend/src/providers/live-snapshot-provider.tsx`
- `frontend/src/providers/live-snapshot-polling.ts`
- Focused polling and provider tests alongside them.

The healthy path now requests one authoritative snapshot. Summary becomes a
fallback only when that contract cannot supply a board. Idle upcoming snapshots
poll every 60 seconds; active live rounds and active/manual refreshes retain
their ten-second snapshot cadence. Status uses 15 seconds while idle and
2.5 seconds only for queued/running/busy/refreshing progress or a manual refresh.
The status resource has one query key across the provider and tools.

A busy-to-idle transition fetches the finished snapshot immediately, rather
than leaving the previous cycle visible for the new idle interval. The
snapshot interval shortens at the server's freshness deadline, based on the
received age and client receipt time instead of assuming synchronized clocks.
Hidden pages stop requests and catch up when visible. Existing invalidation
keys and manual refresh controls remain compatible.

Fallback display context and the last good board are retained when a later
contract hides stale/unavailable rows. The authoritative `snapshot` and
`data_state` still reflect that contract; retained display context is not
promoted into a healthy board. Old fallback error flags stop affecting the
screen when the authoritative response recovers. Browser caches are rewritten
only when snapshot content changes, not for age-only envelope updates.

Verification at this checkpoint: **27 tests passed** across polling/provider
regressions and legacy route gating. Focused ESLint has no errors and only the
existing component/hook export warning in the provider. Integrated verification
and the subsequent frontend deployment are recorded below and above.

### Integrated release verification

After the parallel implementations completed, the full frontend suite passed
**414 tests across 71 files**, along with typecheck, production build and bundle
budget. Entry gzip is 76,107 bytes (budget 79,772); this is the main entry only,
not total route JavaScript. Scoped lint passed for the new sharing, request and
telemetry modules; the provider retains its existing export warning.

The integrated frontend also scopes board/evidence requests to their screens,
cancels work on navigation, bounds GET reads to one ten-second total deadline
with at most one transport retry, and defers optional telemetry until after
render. My card and the shared reader request neither board nor evidence.
Mutating APIs remain single-attempt. Saving cached board quotes is disabled
during revalidation, both in the control and its handler.

The new sharing flow selects up to 32 saved picks, creates a bounded compressed
URL-fragment snapshot and offers recipient-ready text. It preserves original
values and identities, rejects malformed/oversized payloads and requires no
server mutation. Shared cards are read-only and explicitly unverified. Sentry
removes shared fragments from event and transaction metadata. Browser checks
verified selected-only sharing, copy, desktop/mobile/app-panel layout and
light/dark states using labelled local fixtures, not live betting offers.

An independent source review identified stale manual-copy text after changing
the selected subset and cached quotes remaining saveable during revalidation.
Both are fixed and covered by regressions; a second read-only check confirmed
the fixes. Deployment status is recorded in the delivery report.

The independent design review returned **ship**, with no material fixes, after
inspecting final 1440px, 390px and 668px composer/reader captures. The established
design system remains unchanged; the surface brief records the finished sharing
flow. The focused design detector returned no findings.

## Remaining safe priorities

1. Observe requests on a visible legacy screen during normal operation: no healthy summary request,
   idle status 15 seconds, idle upcoming snapshot 60 seconds, active tracking
   unchanged. Confirm manual completion and background/resume behavior.
2. Introduce a small read-only status projection from heartbeat/snapshot
   metadata. Move the historical grading report behind its own on-demand
   detail endpoint. This avoids repeatedly transferring a 116KB report for
   liveness. Keep it in the isolated service until main application startup
   and migration safety are resolved.
3. Consider caching parsed snapshot data in the isolated service by file
   identity/mtime/size. Recalculate freshness and eligibility per request;
   never cache a fresh eligibility decision solely by snapshot ID. An old
   snapshot can become stale without changing its ID.
4. Keep heavy tools route-scoped and defer full history/pick detail until the
   user opens it. The legacy app shell also requests dashboard state and
   grading-season metadata globally; narrower page ownership can reduce this
   remaining fanout without changing model outputs.
5. Keep future evidence caching bounded, explicitly scoped by lane/season and
   database/WAL changes or a short declared TTL. Current evidence latency is
   already low; delivery and request fanout are higher-value first fixes.

No recommendation requires changing predictive models, stored picks/results,
grading history, learned weights, or automatic-learning schedules.
