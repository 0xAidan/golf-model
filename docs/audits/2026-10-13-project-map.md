# Project map — October 13, 2026

This is a source-based map of the system and the October 13–14 read-only audit, not a claim of season profitability or a certification that every optional pipeline is running. Source was inspected without calling providers or running models, migrations, grading, or learning. The new desk/reporting work preserves forecast values and historical records.

## What was built

The project is an always-on golf prediction, price-comparison, research, and settlement system. It combines player performance and course context, turns forecasts into market probabilities, compares those probabilities with bookmaker prices, publishes opportunities, and records outcomes for later evaluation.

- `app.py` serves FastAPI and the React SPA; `frontend/` is React 19, TypeScript, Vite, Tailwind, and shadcn components.
- `src/db.py` manages SQLite (`data/golf.db`); `backtester/dashboard_runtime.py` builds published snapshot sections; `workers/live_refresh_worker.py` maintains refreshes.
- `run_predictions.py` and the service path in `analyze.py` enter `src/services/golf_model_service.py::GolfModelService.run_analysis`.
- `README.md` and `docs/AGENTS_KNOWLEDGE.md` explain intent, but some operational descriptions are stale. For example, the README names The Odds API for placements while the inspected service's `_fetch_odds` calls DataGolf's outright-odds adapter. Runtime source takes precedence.

## Prediction and delivery chain

1. Resolve tour, event, course, tournament format, and confirmed field. Field verification gates published model rows; team-format guards prevent individual-market treatment of team events.
2. `src/datagolf.py` supplies field, rounds, rankings/skill, simulation/decomposition inputs, results, and bookmaker odds. Normalized player identities and stored rounds connect these sources.
3. `src/rolling_stats.py` builds performance windows; `src/course_profile.py` supplies course context. Optional weather and external intelligence add context under their existing settings.
4. `src/strategy_resolution.py` resolves **live weekly registry → research champion → active experiment strategy → defaults**, then maps the selected strategy to runtime weights, market filters, EV thresholds, and sizing.
5. `src/models/composite.py` combines course fit, form, and momentum. Effective weights can come from configuration and database state; a source-code default alone does not identify the live model.
6. `src/value.py` and `src/matchup_value.py` turn forecast inputs into market probabilities and compare them with posted odds. Portfolio/exposure rules then shape the displayed selections.
7. The service records predictions, displayed picks, configuration identity, and ledger/card artifacts. Optional `src/telegram_alerts.py` delivers deduplicated matchup alerts when configured.
8. `backtester/dashboard_runtime.py` publishes Champion sections before slower research enrichment, writing `data/live_refresh_snapshot.json`. The browser should consume that publication rather than start prediction jobs.

## Model families and feature boundaries

| Source | Responsibility |
| --- | --- |
| `src/models/course_fit.py` | Course-specific strokes-gained characteristics, course history/recency, sample confidence, putting shrinkage, and optional external-skill/decomposition/approach blends. |
| `src/models/form.py` | Recent performance windows, skill/rank/simulation inputs, sample confidence, and v5 recency/availability adjustments. |
| `src/models/momentum.py` | Changes across performance windows and existing stability controls. |
| `src/models/v5_probabilities.py` | Uncertainty estimation, matchup shrinkage, and uncertainty-aware three-ball probabilities. |
| `src/matchup_value.py` | Head-to-head probability/value calculation, existing Platt/DataGolf blending, and variant-specific helpers. |
| `src/models/prob_engine_v1/` | Offline/shadow probability-engine research; its flags default off in `feature_flags.yaml`. |
| `src/models/inplay_round_matchup.py`, `src/services/inplay_shadow.py` | Live-round research pricing with separate availability/provenance requirements. |
| `src/models/pair_matchup_v1.py` | Pair/team analytics, gated separately from individual executable markets. |

`src/config.py` declares model version 5.0 and `baseline`/`v5` variants. Its global variant defaults to v5, while `COCKPIT_SNAPSHOT_MODEL_VARIANT` defaults to baseline. Environment, strategy records, and snapshot metadata must identify the actual run; these defaults are not interchangeable.

AI analysis is optional. Existing score adjustments depend on `apply_ai_adjustments`; `src/ai_brain.py::make_betting_decisions` explicitly returns `None`. AI narrative and model output should not be presented as the same source of authority.

## Champion, Challenger, live, and research

- `src/track_registry.py` distinguishes the dashboard/Champion runtime configuration from the lab/Challenger bundle loaded through `src/lab_champion.py` and `src/lab_profile.py`, including `config/lab_matchup_champion_trial327.json`.
- There are several historical meanings of “champion”: runtime registry, research registry, lab bundle, and older rails terminology. Record/configuration hashes are safer identifiers than the label alone.
- Snapshot sections are `live_tournament`, `upcoming_tournament`, `lab_live_tournament`, and `lab_upcoming_tournament`. Lane and event mode are separate dimensions; neither justifies falling back to another lane's data.
- `TRACK_PROMOTION_ENABLED` defaults false, but the runtime strategy resolver can use a research champion when a live record is absent. “Research” therefore is not an unconditional isolation guarantee across the entire preexisting system.
- Live group/player shadow flags and research records can exist without executable quotes. `shadow_only`, `live_bettable`, `market_provenance`, timestamps, and market identity must survive every projection.

## Markets, prices, and saved research

The service's `full`/`matchups-only` modes fetch tournament H2Hs; `round-matchups` fetches round H2Hs and can fall back to tournament markets when coverage is sparse. Preserve `market_type`: a fallback is not an 18-hole matchup. Unknown duration cannot safely be renamed 72-hole.

- `matchup_bets_all_books` preserves available bookmaker alternatives; `matchup_bets` is curated. These are different presentation sets, not independent predictive samples.
- DataGolf `3_balls` odds feed `src/value.py::find_3ball_value_bets` and `value_bets["3ball"]`. Posted rows do not establish historical success, eligibility, or a verified group identity.
- Placement/outright, first-round-leader, and other supported markets retain their original type. Raw-odds absence, no qualifying edge, a pipeline error, and stale data are different states.
- `backtester/dashboard_runtime.py` annotates live-market provenance and bettability. Live 72-hole and group-shadow records must not inherit pre-match eligibility from a familiar market name.
- `frontend/src/features/matchup-desk/market-rows.ts` preserves supplied odds, probabilities, and EV. Save eligibility additionally requires fresh usable source data, the correct pre-match context, and sufficient event/market/round/group identity.
- The desk's local research card saves/removes/restores/exports quote snapshots; it does not place wagers or prove execution. Event, lane, round, group/market, player, and bookmaker remain part of identity.

## Storage, historical truth, and reporting

`src/db.py` includes performance history (`rounds`, metrics), forecast/pick history (`prediction_log`, `picks`, `pick_ledger`, `market_prediction_rows`), settlements (`pick_outcomes`, results), historical prices/predictions, and behavioral state such as weights, calibration, and track configurations.

Current SQLite is only one evidence source. Quarantines, tournament exports, archived cards, backups, and tick artifacts hold additional history. **Numeric tournament IDs were reused across database generations.** Recovery needs verified tour/event/year mapping plus source provenance, not a direct join on local IDs. Preserve conflicting historical answers.

The inspected current database does not contain the full season's pick/outcome history. Older sources contain more evidence, but source completeness, duplicate selection, quote timing, and grading authority still require reconciliation. Neither forecast accuracy nor a positive stored nominal return proves actual wagering profit. Group-market success has not been established by the inspected evidence.

`src/market_evidence.py` provides a separate read-only report: SQLite `mode=ro`, `query_only`, a consistent read transaction, and no `src.db` initialization. It preserves stored profit, excludes conflicting duplicate groups from aggregate metrics, separates void/pending/unknown results, and withholds unsupported CLV claims. Flat-stake ROI averages each included record's stored `profit / stake`; it is not turnover-weighted cash-account ROI or independently verified betting P&L.

See [server/data audit](2026-10-13-server-and-data-audit.md) and [history reconciliation](2026-10-13-history-reconciliation.md) for timestamped counts, recovery evidence, and limitations. The source-only cross-event deduplication repair in `src/official_pick_record.py` prevents an identity omission; it does not recover records already absent or authorize a production migration.

## Existing automation and mutation points

- `src/live_refresh_policy.py` selects off/upcoming/live/settlement windows; refresh settings live in `data/autoresearch_settings.json`. The worker writes snapshots and operational/prediction artifacts.
- `src/learning.py::post_tournament_learn` can ingest results, score/update predictions, update adaptation and course weights, invoke `src/models/weights.py::retune(dry_run=False)`, update calibration, and conditionally update bankroll/CLV/Platt state. It is a mutating workflow, not a report.
- `src/dynamic_blend.py` and adaptation state can change future blend/selection behavior. Repeated settlement therefore needs an idempotency audit before claiming learning quality.
- `backtester/research_cycle.py` defaults automatic application off; enabling `autoresearch_auto_apply_enabled` can update the research champion/baseline. `backtester/model_registry.py` contains separate promotion paths. Existing fallback precedence still matters.
- `backtester/strategy.py` and point-in-time research modules support backtesting, but synthetic historical prices and non-independent samples cannot be treated as executed returns.
- At the server audit, dashboard, agent, and live-refresh services were active. Backup, grading-sweep, and disk-watchdog services had failed. Backup/janitor/retention, grading, integrity, and refresh-watchdog timers existed; exact timings/status belong to the timestamped server audit.
- Repo `deploy/systemd/` also contains autoresearch timer templates. A committed unit file does not prove that timer is installed or enabled on the server.
- The grading sweep incorrectly included a future event, and one provider failure could abort later events. A separate tested source repair was prepared; running it still enters existing settlement/learning behavior and requires its own rollout boundary.

## UI and the new isolated delivery surface

`frontend/src/App.tsx` directs `/`, `/card`, and `/evidence` to the new matchup desk and lazily loads the legacy application elsewhere. Legacy routes retain `/players`, player detail, `/compare`, `/compare/players`, `/eval`, `/results`, `/lab`, `/system`, and research pages; compatibility aliases remain in `frontend/src/app/app-content.tsx`.

`src/operator_read_model.py` projects only the requested field-verified snapshot section, flattens supported value-bet shapes, prefers all-book matchups, and exposes research counts without promoting shadow quotes. Missing/invalid current timestamps fail closed; past replay remains archival. `scripts/serve_matchup_reports.py` serves `/api/desk/board` and `/api/market-evidence` through a small read-only sidecar.

The [desk deployment runbook](../runbooks/matchup-desk-deployment.md) separates frontend/reporting delivery from the legacy backend, model workers, database initialization, and prepared safety patches. [Delivery measurements](../frontend-overhaul/delivery-2026-10-13.md) document bundle changes with a remeasured baseline, rather than treating an older budget number as comparable evidence.

## Why navigation became difficult, and safe next work

The architectural diagnosis is that prediction operations, research experiments, live monitoring, market selection, and historical evaluation accumulated in one route/control system. Overlapping champion labels, multiple modes, heterogeneous quote shapes, and inconsistent empty/stale/error meanings force the user to understand internal implementation before comparing a matchup. This explains navigation friction; it does not establish whether selections make money.

1. Preserve and reconcile historical evidence with immutable source manifests and conflict reports. Establish event/market/lane/price/outcome coverage before ranking supposedly successful niches.
2. Keep matchup discovery focused on opponents, duration/round/group, bookmaker price, original probability/EV, and freshness. Measure quote age, delivery latency, and the time needed to compare/save/export a usable research card.
3. Add append-only evaluation by event, market, model/configuration, quote timing, and bookmaker. Show sample sizes and chronological holdouts; distinguish genuine quoted prices from synthetic backtest prices.
4. Build report-only calibration and error analysis around the frozen forecasts. Propose changes to presentation, coverage, or delivery first; never silently retrain, retune, or promote models to implement “self-improvement.”
5. Address backup capacity, grading isolation, and repeat-learning idempotency as separately reviewed operational changes. The user's model/history freeze must cover runtime state as well as source files.
