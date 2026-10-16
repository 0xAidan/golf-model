# Provisional market findings from preserved records

This is a comparison of **stored source records**, prepared October 13, 2026 (local time). It is not a reconciled season record, an execution ledger, or evidence of an expected future return. No model, prediction, source database, outcome, or production setting was changed.

The strongest immediate finding is that dashboard and lab records must remain separate. The examined dashboard records have better stored returns than lab records in both matchup categories, but the apparent advantage of 72-hole over 18-hole markets is not consistent across source generations. Missing history, changed market labels, and changed cohort membership prevent a reliable season conclusion.

## Sources and bounded method

The local comparison used only already preserved artifacts under `/Users/aidannugent/websites/golf-model-preservation/2026-10-13/`:

- `history-evidence-vault.20261014T003000Z.jsonl.gz`: read its first five source generations, stopping after 66,844,397 expanded bytes. Retained only tournaments, picks, and outcomes for analysis; did not parse the millions of export ledger rows. The generations are the verified current snapshot and September 2, 3, 4, and 13 quarantine base files. The quarantine capture excluded WAL and may therefore omit uncheckpointed rows.
- `exports-and-audits.tar.gz`: read only tournament metadata, picks, and outcomes in 17 tournament export folders. Those folders contain 2,878 pick records. They are a separate export cohort and overlap the database generations.
- Derived output: `historical-market-comparison.20261014T004723Z.json`, SHA-256 `71283ce4bfce407bb0d2cebbf161a72523984ea230df56b0dda4fc4ad4e50136`. It includes every generation's market/lane totals and event-level cells.

Joins use pick IDs **within each source only**. Event keys include source generation and local tournament ID; no numeric ID is merged across sources. Four fixture/missing-event records per quarantine generation are excluded from this derived comparison, with counts recorded in the JSON. The current and export cohorts have no such exclusions. All original rows remain preserved. Counts are raw records, potentially repeated or correlated, not independent wagers.

`tournament_matchups` is labeled 72h and `round_matchups` 18h, based on the stored market label. That is not independent verification of the original contract. Generic matchup rows remain unspecified. No group market is inferred from player count or descriptive prose. `cockpit` is displayed as dashboard; lab candidates stay in the lab lane.

## Denominators and settlement limitations

The tables show wins/losses/pushes (W/L/P), voids (V), and ungraded/unresolved records (U). A recorded void authority takes precedence over a binary `hit` field. Where an explicit push label is absent, `hit=0` with zero stored profit is provisionally a zero-return/push record; its settlement interpretation still needs verification. Void and unresolved records never become losses.

`N` includes resolved, nonvoid W/L/P records with positive recorded stake and known recorded profit. Here those eligible rows record one unit each. `Net` is their stored profit sum; `Recorded return` is `100 × sum(profit / recorded stake) / N`, with pushes in the denominator. These are paper/stored-stake calculations. **Actual execution, actual stake, and actual ROI remain unknown.** No profit is reconstructed from prices, no unresolved row is assigned a result, and no fitted selection threshold is used.

## September 13 quarantine generation

This generation has 2,355 pick records; 2,351 remain after the four fixture/missing-event exclusions. Event counts below are source-local and include events with only void records.

| Lane | Market | Records / events | W / L / P | V / U | N | Net units | Recorded return |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Dashboard | 72h | 359 / 20 | 136 / 111 / 39 | 73 / 0 | 286 | +10.8649 | +3.80% |
| Dashboard | 18h | 608 / 12 | 322 / 273 / 7 | 6 / 0 | 602 | −3.2271 | −0.54% |
| Lab | 72h | 387 / 13 | 136 / 132 / 35 | 84 / 0 | 303 | −25.6441 | −8.46% |
| Lab | 18h | 677 / 8 | 346 / 315 / 4 | 12 / 0 | 665 | −63.6165 | −9.57% |

The dashboard 72h subtotal spans 11 positive and eight negative event cells, with one zero-return cell. Dashboard 18h has five positive and six negative cells, plus one void-only event. These are descriptive event counts, not a significance test. Multiple bets on the same golfer or event are correlated.

September 2–4 are overlapping snapshots, not three additional samples. Dashboard 72h recorded return varies from +3.48% to +3.89%; dashboard 18h is −0.84%. Their similar rows must not increase a sample-size claim.

## Selected tournament export cohort

These 17 folders are preserved at potentially different export/reconstruction times. They contain a different event mix and different row sets from the September snapshot. Do not add either table to the other, interpret their difference as model drift, or treat it as a chronological out-of-sample test.

| Lane | Market | Records / events | W / L / P | V / U | N | Net units | Recorded return |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Dashboard | 72h | 379 / 13 | 132 / 124 / 34 | 89 / 0 | 290 | −10.5177 | −3.63% |
| Dashboard | 18h | 633 / 11 | 326 / 285 / 0 | 22 / 0 | 611 | −11.7780 | −1.93% |
| Lab | 72h | 436 / 12 | 156 / 147 / 36 | 97 / 0 | 339 | −26.5648 | −7.84% |
| Lab | 18h | 678 / 7 | 346 / 314 / 0 | 18 / 0 | 660 | −63.4891 | −9.62% |

Dashboard 18h wins 53.4% of its binary win/loss rows while its recorded return is negative. A win-rate badge alone does not communicate the effect of price. The nonvoid 72h grades here have `computed` authority; the 18h grades have `matchup_outcome` authority. Agreement across these different settlement paths has not been established.

Event concentration matters. Dashboard 18h ranges from +11.4911 units at Wyndham to −15.0093 at the Scottish Open in this cohort. The respective lab cells are −5.2570 and −13.5402. This is sufficient reason to show event-level history and lane provenance, but not to choose or exclude named tournaments based on hindsight.

An example of unresolved history is Arnold Palmer: the September generation labels 13 records as 72h with +7.57 units; its export labels 14 as unspecified matchups with +6.57 units. They are retained as separate observations. A source-label change or lost record must not masquerade as a learned market advantage.

## Current preserved snapshot and other markets

The verified current snapshot has only 568 picks across five source-local events. Dashboard 72h has 66 records: 27 W / 28 L / 3 P / 5 V / 3 ungraded, with −5.7197 stored units over 58 eligible records. Dashboard 18h has 49 records: 20 W / 27 L / 0 P / 2 V, with −8.8941 units over 47 eligible records. Most resolved matchup records come from Bank of Utah and Baycurrent. This small recovered slice cannot represent the season.

No explicit group/three-ball market labels were found in the analyzed core picks. This does not establish that the project never generated successful group selections: separate cards, research snapshots, or unexamined ledger payloads may contain them. A group-results claim needs original group membership, book contract, round, quote time, and settlement rules recovered together.

The export cohort's **unspecified** dashboard matchups have 149 records across five events: 76 W / 49 L / 19 P / 5 V, +18.2455 stored units over 144 eligible records. Twenty-nine are imported from `trackRecord_json`, lack model probabilities and book values, and include Arnold Palmer and Cognizant. This is a useful recovery lead, not evidence that they were 72h, 18h, or group contracts.

Placements/other markets are intentionally kept outside the matchup tables. Their exported dashboard subtotal is +47.4850 units over 364 eligible rows, with another 165 void rows. It includes +76.78 at the U.S. Open, +36.28 at Travelers, −44.20 at Bank of Utah, and −35.00 at Baycurrent. That concentration and the mixed market definitions do not support promoting an “obscure market” strategy from the aggregate.

## Bounded group-market recovery check

A further local-only inspection read **52 Markdown files and 188 provenance JSON files** (175 output files plus 13 local-recovery files), totaling 5,238,052 selected payload bytes from the verified `research-cards-output.tar.gz`. This includes the earlier 38 candidate cards/36 distinct hashes. No large ledger was parsed and no server source was queried.

The 22 Markdown files mentioning three-ball/group terms contain **19 “no value plays” placeholders, two “no odds” placeholders, and one team-format exclusion**. They contain zero explicit group selections or same-source settled group results. Exact examples within the archive: `data/local_recovery/md_cards/md cards/masters_tournament_20260408.md`, lines 93–97, says no three-ball value plays; `data/local_recovery/md_cards/md cards/cognizant_classic_20260228.md`, lines 192–196, says no three-ball odds; `output/zurich_classic_of_new_orleans_20260823.md`, line 16, excludes three-ball for the team format. Repeated placeholders are not observations of successful selections.

Of the 188 provenance files, 181 parse as JSON; six are empty and `output/bank_of_utah_championship_provenance_20260930.json` is truncated. Original bytes remain preserved. Neither raw text nor parsed keys/values in these files contains an explicit group/three-ball label; the recorded matchup market labels are round and tournament matchups. The failed files are coverage gaps, not evidence of absent selections.

Per-member hashes, excerpts and parse failures are retained outside git in `group-recovery-inspection.20261014T010819Z.json` and `group-recovery-classification.20261014T010904Z.json`. These bounded sources do not establish group performance. Further discovery should search remaining research/quote payloads for explicit group membership and a linked same-contract settlement; a section heading or three-player prose reference is insufficient.

## What can guide the next iteration

1. **Information delivery:** give matchups first-class 72h and 18h views, show the selected book/price and evidence coverage beside each pick, and keep lab candidates visibly separate. Display wins, losses, zero returns, voids, and pending states independently. Do not attach a full-season success claim to the current recovered database.
2. **Historical reconciliation:** resolve semantic event identity and original contract from preserved sources, retain every conflicting observation, then propose an auditable canonical view. All analyzed round-market picks lack an explicit round field in the core rows; original round identity and pre-start decision time must be recovered before any round policy evaluation. Source-record dates must not substitute for decision timestamps.
3. **Frozen-model shadow evaluation:** predeclare a small set of delivery/selection policies, preserve unchanged model predictions, and evaluate only on subsequently observed events. Split chronologically by whole event, hold out future events, and report event-level uncertainty and coverage. Use existing historical comparisons to find missing data and formulate hypotheses, not to tune thresholds for maximum hindsight profit.
4. **Evidence to capture prospectively:** immutable event identity, market horizon, explicit round/group members, model/config version, original prediction time, book quote/time, lane, displayed-versus-executed status, actual stake only when confirmed, and settlement version/authority. CLV needs matched entry and closing quotes for the same contract; repeated CLV log rows are not independent samples.
5. **Group and other-market discovery:** first identify original contracts and settlement evidence in the preserved cards/research records. Keep such markets “coverage incomplete” until that work is done. Compare each contract class separately under a predeclared shadow protocol. Do not promote changes or modify weights, calibration, probabilities, or historic outcomes.

The underlying outcome-count partitions and source pick totals were checked against the derived JSON. Existing verified artifacts were opened read-only; no server database was queried for this comparison. See [history reconciliation](2026-10-13-history-reconciliation.md) for preservation scope and the recovery boundary.
