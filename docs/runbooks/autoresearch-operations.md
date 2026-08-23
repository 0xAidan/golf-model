# Runbook — Autoresearch Operations

**Audience:** the operator (no assumptions). Every command below is copy-pasteable on the VPS (`root@204.168.147.6`, app root `/opt/golf-model`).
**Control plane:** [`docs/research/PROGRAM.md`](../research/PROGRAM.md) — read it first; it defines what the loop may and may not do.

---

## 1. What runs where

| Piece | Where | Schedule |
|---|---|---|
| Nightly fast-tier cycle | `golf-autoresearch.timer` -> `workers/autoresearch_orchestrator.py` | 02:30 UTC daily (+ up to 10 min jitter) |
| Weekly deep cycle | `golf-autoresearch-deep.timer` -> same script `--weekly` | Sundays 04:00 UTC |
| Manual single cycle | CLI, on demand | whenever you want |

The nightly cycle: mutates the strategy config within declared ranges, evaluates candidates on the frozen 13-event search window, keeps/discards mechanically, confirms survivors on the last 3 events, and stages promotion-ready dossiers. **It never promotes anything and never touches your dashboard model.**

## 2. First-time enablement (after deploy)

```bash
cd /opt/golf-model
systemctl enable --now golf-autoresearch.timer golf-autoresearch-deep.timer
systemctl list-timers | grep autoresearch   # confirm next run times
```

To stop the loop entirely:

```bash
systemctl disable --now golf-autoresearch.timer golf-autoresearch-deep.timer
```

## 3. Daily use (all from the dashboard)

Open the site -> **/research/autoresearch**:

- **Next nightly cycle** card: countdown to the next run.
- **Effort dial**: click `light` / `standard` / `max`. Takes effect next cycle. Light ≈ 20 min, Standard ≈ 60 min (~100 trials), Max ≈ 3 h.
- **Promotion-ready cards**: when the loop finds a candidate that passed search AND confirmation, a card appears with the exact config diff and evidence. Click **Promote to Lab…**, type a reason, done. That swaps the `/lab` board's algorithm going forward.
- **Rollback lab**: one click restores the previous algorithm.
- **Algorithm eras table**: each algorithm's ROI/W-L counted only from its activation moment, plus an all-time line.

The full Research -> Lab ladder's second hop (Lab -> Main) is unchanged: /eval tab -> Promotion tab -> typed confirmation (charter gates apply).

## 4. Reading results

- Ledger: `output/research/ledger.jsonl` (append-only; every trial + verdict). Browse in the UI or:

```bash
tail -5 output/research/ledger.jsonl | python3 -m json.tool --json-lines
```

- Dossiers: `output/research/promotion_ready/*.json` (Tier 1), `output/research/tier2/*.json` (structural hypotheses).
- Health: `data/autoresearch_heartbeat.json` should update every cycle; stale heartbeat = stalled loop.

```bash
systemctl status golf-autoresearch.service
journalctl -u golf-autoresearch.service -n 50
```

## 5. Sealed holdout (quarterly ritual)

Two events are permanently excluded from all research windows ([list](../research/sealed_holdout_events.json)). Open them at most quarterly, deliberately:

```bash
python3 scripts/run_autoresearch_sealed_holdout.py            # preview (no writes)
python3 scripts/run_autoresearch_sealed_holdout.py --write    # append result to ledger permanently
```

Interpretation: strong positive = real edge confirmation. Negative/near-zero = the research score was overfitting; demote expectations for staged candidates. The result is appended either way — that is the point.

## 6. Tier 2 (ideas that need code)

When Telegram pings about structural signals:

1. Dashboard -> Autoresearch -> review dossiers under `output/research/tier2/`.
2. If convincing: `POST /api/autoresearch/tier2/create-pr {"segment": "..."}` (button lands with the next UI pass) — creates a DRAFT PR; nothing merges automatically.

## 7. Failure triage

| Symptom | Check | Fix |
|---|---|---|
| No ledger rows overnight | `ls -la data/autoresearch_heartbeat.json`; timers enabled? | `systemctl list-timers`; check journalctl |
| Heartbeat says error | `journalctl -u golf-autoresearch.service -n 100` | Usually ingestion; run `python3 scripts/run_weekly_research_refresh.py --ledger-only` |
| Evaluator fingerprint mismatch alert | Someone changed frozen evaluator files without bumping versions | Revert or do a proper reviewed evaluator PR + re-baseline |
| Cycle crashed mid-run | Safe by design | Just wait for the next cycle; recovery reads state from the ledger |
| Lock stuck (cycle skipped) | `lsof data/autoresearch_cycle.lock` | Kill stale holder or reboot; lock is advisory fcntl |

## 8. Deploy notes

Deploy ships the timer units but does not enable them (section 2 is manual by design). Full deploy remains:

```bash
DEPLOY_HOST='root@204.168.147.6' ./deploy.sh --update
```

## 9. Rules the loop itself follows (so you can trust it)

- Frozen evaluator: CI blocks edits to `backtester/strategy.py`, `pit_models.py`, etc.; characterization tests pin behavior; version bumps require reviewed PRs.
- Nothing auto-promotes. Ever. Autonomy ends at dossiers + alerts.
- Ledger is append-only; history is never rewritten.
- Budgets are hard caps read fresh from your effort dial each cycle.
