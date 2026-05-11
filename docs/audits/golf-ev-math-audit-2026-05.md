# Golf Model — EV & Probability Math Audit (May 2026)

**Scope:** Read-only verification of odds conversion, implied probability, EV formulas, calibration/dead-heat ordering vs displayed probabilities, and where de-vig applies. **Status:** Formulas **pass** for all audited market types; historical Masters headline discrepancies are explained by **probability lineage** (displayed blend vs `ev_prob`), not broken arithmetic.

---

## 1. Canonical formulas (`src/odds_utils.py`)

**American → decimal**

- Favorites (negative): \(d = 1 + \frac{100}{|o|}\)
- Underdogs (positive): \(d = 1 + \frac{o}{100}\)

**American → raw implied probability** (includes book margin; **not** de-vigged)

- Positive: \(q = \frac{100}{o + 100}\)
- Negative: \(q = \frac{|o|}{|o| + 100}\)

**EV (outright / placement / props using one price)**

\[
\mathrm{EV} = p_{\mathrm{ev}} \cdot d - 1
\]

where \(p_{\mathrm{ev}}\) is the probability actually multiplied into the ticket payoff (after calibration and placement dead-heat discount when applicable — see §4).

---

## 2. De-vig vs card labels

| Surface | Raw implied from posted odds? | De-vig / fair prob? |
|--------|--------------------------------|---------------------|
| Value rows `market_prob` / `market_implied_prob_raw` | Yes — per-book American conversion | No |
| Card / dashboard copy (after this audit) | Labeled **posted implied** | No |
| `src/clv.py` `multiplicative_devig()` | Uses implied from decimals | Yes — **only** for CLV-style normalization when multiple implied probs are provided |

**Pass/fail:** **Pass** for internal consistency: the system does not claim card `market_prob` is de-vigged. CLV de-vig is a separate analytics path.

---

## 3. Masters-era headline recomputations (fixtures)

Numbers below use current `american_to_implied_prob` / `american_to_decimal` / `compute_ev` semantics. Rounded display probabilities can shift EV by meaningful amounts at long prices.

### 3.1 Kurt Kitayama outright **+17500**, model **0.69%** (0.0069)

- Raw implied \(q = 100 / 17600 \approx 0.5682\%\)
- Decimal \(d = 176\)
- \(\mathrm{EV} = 0.0069 \times 176 - 1 \approx 21.44\%\)

An older **~20.6%** headline is consistent with a slightly **lower** unrounded win probability (~0.657% would land near 20.6% at +17500).

**Market type:** outright — **pass**.

### 3.2 Maverick McNealy top-5 **+1300**, displayed model **8.17%** (0.0817)

- Decimal \(d = 14\)
- Raw implied \(q \approx 7.143\%\)

If EV used the **same** 8.17% with no dead-heat adjustment:

\[
0.0817 \times 14 - 1 \approx 14.4\%
\]

The pipeline applies a **dead-heat discount** to placement **EV only** (`DEAD_HEAT_DISCOUNT_TOP5 = 5%` in `src/config.py`), i.e. `ev_prob = calibrated × 0.95` while `model_prob` remains the **blended** display probability. With calibration ~1:

\[
0.0817 \times 0.95 \times 14 - 1 \approx 8.7\%
\]

So an old card showing **~8.7% EV** next to **8.17% model** is explained by **EV on `ev_prob`** vs **display on pre-dead-heat blend** — not a formula bug.

**Market type:** top-5 — **pass** (with explicit lineage fields after hardening).

### 3.3 Min Woo Lee vs Brooks Koepka **−130**, model **62.8%** (0.628)

- Implied \(q = 130 / 230 \approx 56.52\%\)
- Decimal \(d = 1 + 100/130 \approx 1.7692\)
- \(\mathrm{EV} \approx 0.628 \times 1.7692 - 1 \approx 11.1\%\)

Matches the historical ~11% style output.

**Market type:** matchup (binary price side) — **pass** (matchup baseline EV uses `model_win_prob / implied - 1` or void-tie variant in v5; this example is the binary check).

### 3.4 Reference long-shots (Knapp **+8000**, Spaun **+10026**)

- **+8000:** \(q = 100/8100 \approx 1.2346\%\), \(d = 81\). Tiny changes in \(p_{\mathrm{ev}}\) move EV sharply (fragility), but the formula is standard.
- **+10026:** \(q = 100/10126 \approx 0.9876\%\), \(d = 101.26\).

**Market type:** outright long-shot — **pass** math; **warn** for marketing (large EV swing from tiny probability deltas).

---

## 4. Pass / fail by market type

| Market | Formula | Display vs EV probability | Verdict |
|--------|---------|----------------------------|---------|
| Outright | \(p \cdot d - 1\) | `model_prob` = blend; `ev_prob` = calibrated (no dead heat) | **Pass** |
| Top 5/10/20 | Same | `ev_prob` includes dead-heat factor | **Pass** |
| Top 15 | Previously inconsistent (softmax target / DG sums / thresholds) | **Suppressed** in live value computation until wired | **Fail → mitigated** (hidden / skipped) |
| FRL / make cut / 3-ball | Same core EV | Blend + calibration path analogous | **Pass** |
| Matchup | Binary or void-tie v5 | `model_win_prob` / `ev_prob` aligned with EV | **Pass** |

---

## 5. Code references

- Odds & implied: `src/odds_utils.py`
- EV & lineage fields: `src/value.py`, `src/matchup_value.py`
- De-vig (CLV): `src/clv.py` — `multiplicative_devig()`
- Dead-heat discounts: `src/config.py`
- Read-only audit runner: `scripts/audit_ev_math.py` → `output/audits/` (gitignored artifacts; run locally)

---

## 6. Probability pipeline notes (U2 overlap)

- **Field sums:** DG sims are renormalized after phantom-field filtering in `_get_dg_probabilities()`; softmax fallback targets correct totals per market in `model_score_to_prob()` (including **top15 = 15** for defensive consistency if ever enabled).
- **Calibration:** `get_calibration_correction()` scales probabilities before EV; field-wide sums after per-bet calibration are **not** forced to 1.0 — acceptable for bet-level auditability; sums are reported via `src/probability_audit.py`.

---

*Generated as part of the Golf Model EV audit plan (implementation May 2026).*
