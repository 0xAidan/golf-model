# Grading reconciliation report

> Provenance: generated from the **local dev `data/golf.db`** (a small fixture copy), so
> counts are zero/trivially "ok". This file is the committed *template/example*. Run the
> real check against production on the VPS:
> `python3 scripts/grading_reconciliation.py --write` (exit code is non-zero on
> discrepancies, so it can gate a deploy check). See `src/grading_reconciliation.py`.

- **Status:** ok
- **Pick source:** all
- **Events with ungraded +EV picks (post-results):** 0
- **Orphan pick_outcomes rows:** 0

| Event | Year | Results | +EV picks | Graded | Ungraded | OK |
|-------|------|---------|-----------|--------|----------|----|
| RBC Heritage | 2026 | 0 | 0 | 0 | 0 | ok |
| Zurich Classic of New Orleans | 2026 | 0 | 0 | 0 | 0 | ok |
| Test Event | 2026 | 0 | 0 | 0 | 0 | ok |
| Future Event | 2026 | 0 | 0 | 0 | 0 | ok |
| Masters Tournament | 2026 | 0 | 0 | 0 | 0 | ok |
| Current Event | 2026 | 0 | 0 | 0 | 0 | ok |
