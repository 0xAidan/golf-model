# Future market generation controls

The Markets page separates browser visibility from saved generation policy.
Visibility changes only the current browser. Generation policy is shared by
future API, CLI and worker runs; it never removes old forecasts, changes model
weights or places bets. A run already in progress retains its captured revision.

## Operator access

Provision a random `MARKET_GENERATION_API_KEY` in the private, mode-0600 file
`/etc/golf-model/market-generation.env`. The dashboard unit's optional environment
drop-in loads that file. Do not commit credentials or place them in web assets.
`DASHBOARD_API_KEY` is a fallback when the dedicated key is absent. Missing write
authentication makes generation editing unavailable; read-only viewing remains.

In Markets, open Market generation, enter the operator key, select supported
families and explicitly save. The browser does not persist the key. Review the
saved readback and revision. Existing strategy, run-mode and feature restrictions
still apply; enabling a family does not guarantee provider quotes for an event.

Supported generation IDs are `72h`, `18h`, `group`, `outright`, `top5`, `top10`,
`top20` and `frl`. Make-cut, miss-cut and top-15 remain unavailable in the current
generation adapters and cannot be enabled by this control.

## Persistence and API

`GET /api/market-generation-policy` is read-only and reports supported markets,
saved revision, enabled families, policy state and authentication availability.
It returns no credential. A new installation without policy revisions preserves
existing generation behavior. An explicitly empty saved list disables future
market selections while rankings remain available.

Authenticated `PATCH /api/market-generation-policy` accepts only:

```json
{"enabled_markets":["72h","top20"],"expected_revision":"revision-from-GET"}
```

Use `x-api-key` or a bearer credential. A stale revision returns 409 and requires
reloading; unsupported or duplicate IDs are rejected. Missing or corrupt saved
policy state fails closed for new market selections instead of restoring all
markets. No historical forecast is changed.

Policy revisions are immutable, hash-bound JSON under the configured data
directory's `market-generation-policy/revisions/`. Only the current pointer is
atomically replaced after file/directory synchronization. Every accepted change
retains its previous revision. A different data directory must share the same
`GOLF_MARKET_GENERATION_POLICY_DIR` if it is intended to share the same policy.

Rollback the source/UI release using its retained originals. To restore an older
policy, submit that revision's allowlist as a new authenticated change with the
current revision; do not delete revision files or silently rewrite the pointer.
