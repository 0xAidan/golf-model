# Sunday Workflow Checklist (Perfect Sprint Gate)

Run on production after deploy. Log results in `docs/frontend-overhaul/verification-YYYY-MM-DD.log`.

| Step | Action | Pass |
|------|--------|------|
| 1 | Open `/` during live week | Lands Live; board <1s; freshness indicator clear |
| 2 | Full picks tab | Grid populated; no Pending on graded +EV |
| 3 | `/lab` + Full lab picks | Parity with Dashboard |
| 4 | `/compare` | Dashboard vs Lab diff for current event |
| 5 | Grade or verify auto-grade | Results trust strip Ungraded +EV = 0 |
| 6 | `/results?tab=analytics` | Latest event expanded; preset works; filter slice ~10s |
| 7 | `/system` | Worker healthy; no SSH needed |

**Operator sign-off:** _________________ Date: _________
