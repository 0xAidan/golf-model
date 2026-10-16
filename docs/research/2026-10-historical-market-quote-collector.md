# Historical bookmaker evidence collector

Implemented 2026-10-16. This collector writes a **separate evidence vault**, not `golf.db`, and does not alter existing predictions, prices, scoring, promotions or live model behavior.

## Source contract

[DataGolf's API documentation](https://datagolf.com/api-access) distinguishes historical bookmaker odds from its predictions archive. The collector uses explicit `tour`, numeric `event_id`, calendar `year`, `book`, decimal format and JSON format. Outrights additionally require a market. The historical event list supplies source event identities and availability. Endpoint defaults to recent events are never used. The old synthetic-only `backtester.backfill.backfill_odds` remains separate; DG-Base/DG-CH are rejected as sportsbook request labels.

Supported calls:

- `historical-odds/event-list`
- `historical-odds/outrights`: win, top 5/10/20, make/miss cut
- `historical-odds/matchups`: vendor tournament/round matchup and 3-ball contracts, preserving exact contract labels

The public [archive page](https://datagolf.com/outright-odds-archive) also identifies downloadable bookmaker data. Coverage is established from authenticated responses, not an old static coverage table. No credential or authenticated URL is logged or stored.

## Storage and qualification

`src/historical_market_quotes.py` owns the separate `quotes.sqlite` schema and content-addressed gzip raw responses. Raw hashes cover the original decompressed response bytes. Tables store safe request parameters, HTTP status, acquisition receipts, parser version, exact row JSON pointers, source metadata and original payloads. Repeated identical captures add an acquisition receipt but no duplicate normalized rows. Changed vendor responses remain separate source versions. Existing raw files are verified and never overwritten; evidence tables reject updates/deletes.

Response event ID/year/book/market must match the request. An independent retained catalog must match tour/event/year/name before the analysis exposes an event-bound price comparison. Missing identities, conflicting source versions, missing prices, synthetic books and invalid values remain unqualified. Original vendor IDs are required; no fuzzy player matching occurs in the exact-key reconciliation API.

`vendor_open_close_pct = 100 * (vendor_open / vendor_close - 1)` describes two vendor archive prices. It is not a bet result. `qualified_clv_pct` remains null unless identity, timezone-aware ordered quote times, a sourced market start and an explicit settlement contract are all established. `analyze_quote` accepts an independently verified start only with its source SHA-256 and JSON pointer; callers must establish that referenced evidence. The shipped vault analysis supplies no guessed start context. Naive timestamps remain literal strings. No margin removal, fair-close EV or execution claim is inferred.

Two-sided matchups preserve both players and sides. Three-balls preserve **all three** players and the full contract player set, so they cannot join a two-player forecast. Some vendor round matchups offer a separate categorical `Halve` selection with DG ID zero. Their full raw payloads and three selections are retained as `multi_outcome_matchup`, but they are excluded from price qualification pending a specific contract adapter. ID zero is not converted into a golfer. Numeric vendor outcomes, including 0.5, are preserved without guessing payout or binary meaning.

## Bounded authenticated validation

Active evidence: `data/research/historical-market-quotes-20261016-v3/`. Capture used the existing VPS credential through an SSH read-only API transport; no code was installed remotely and no source database was opened. Requests covered:

- Pinnacle win and matchup markets for 2026 Truist, Masters and Charles Schwab.
- Masters matchups at Bovada, BetOnline, bet365 and DraftKings, matching book labels actually present on recovered cards.
- The PGA historical event list and preserved initial probes.

| Measure | Result |
| --- | ---: |
| Unique response sources | 11 |
| Acquisition receipts | 15 |
| Normalized side/placement observations | 2,987 |
| Event-bound valid price pairs | 2,759 |
| Distinct valid side-contract keys | 2,757 |
| Extra categorical-outcome observations excluded | 228 |
| Qualified CLV pairs | 0 |

All 11 raw response hashes and all 2,987 normalized source pointers/price fields were verified against original bytes; SQLite integrity check passed. `source-validation.json` records the result. All captured quote times lack timezone offsets, no precise market-start source is present, and the 245 outright rows lack an explicit settlement rule. These are useful market observations, not 2,987 wagers or independent trials. Draft v1/v2 normalizations are retained in their earlier directories with explicit supersession sidecars; only v3 is the analysis input.

Recovered Masters card reconciliation is retained in `recovered-card-forecast-candidates.jsonl` and `recovered-card-reconciliation.jsonl`. Eleven source observations contain an explicit bookmaker, stated 2026 header and 72-hole matchup section. Exact full-name pair normalization within that source event produced eight candidate identity bridges, representing **four distinct player/book/entry-price contracts**. Three observations (two distinct contracts) had no exact vendor pair. Source hashes, line numbers, original labels and vendor quote pointers accompany every bridge. No fuzzy aliases were used; these bridges are candidates for identity review, not independent publication proof. Entry-price comparisons use the actual card price, never the vendor opening price. All card CLV remains null because original publication, timing and matching settlement evidence are incomplete.

## Running it

```sh
python scripts/collect_historical_market_quotes.py --vault /path/to/new-vault collect \
  --tour pga --event-id 480 --year 2026 --book pinnacle --market win \
  --matchups --max-requests 3
python scripts/collect_historical_market_quotes.py --vault /path/to/new-vault summary
python scripts/collect_historical_market_quotes.py --vault /path/to/new-vault reconcile \
  --forecasts exact-identity-forecasts.jsonl
```

The local transport uses `DATAGOLF_API_KEY` from the existing environment or repository `.env`. `--ssh-host golf-vps` uses the existing VPS environment without transferring the key. Collection is sequential, bounded before dispatch, spaces requests by two seconds and stops on a rate-limit response. The summary exposes unsuccessful/empty sources separately. A transport failure cannot log a request URL containing the key.

Reconciliation inputs require source hash/pointer, explicit identity provenance, tour/event/year/book/market/player IDs and the original quoted decimal price; matchup opponents must also match. A three-ball additionally requires the exact full contract player set. Conflicting vendor closes remain unresolved. This supports a future event-grouped market residual benchmark; it does not establish profitable superiority, executable historical returns or promotion readiness.

Validation: 27 collector regression cases cover raw fidelity/idempotency, append-only tables, metadata mismatches, synthetic rejection, missing/naive/late timing, three-ball and categorical outcomes, exact original-price joins, conflicting revisions and credential-safe failures. Legacy CLV regression coverage was run alongside it. No commit or deployment was performed.
