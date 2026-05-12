#!/usr/bin/env python3
"""
Read-only EV / implied-probability audit.

Writes timestamped JSON and Markdown under ``output/audits/`` (gitignored patterns).
Safe to run without API keys — uses fixed regression examples only.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import config  # noqa: E402
from src.odds_utils import american_to_decimal, american_to_implied_prob  # noqa: E402
from src.value import compute_ev  # noqa: E402


def _example(name: str, american: int, model_p: float, *, ev_prob: float | None = None) -> dict:
    p_ev = model_p if ev_prob is None else ev_prob
    dec = american_to_decimal(american)
    impl = american_to_implied_prob(american)
    return {
        "name": name,
        "american": american,
        "raw_implied_prob": round(impl, 8),
        "decimal_odds": round(dec, 6),
        "model_prob_displayed": model_p,
        "ev_prob_used": p_ev,
        "ev": round(compute_ev(p_ev, american), 6),
        "ev_pct": f"{compute_ev(p_ev, american) * 100:.2f}%",
    }


def build_report() -> dict:
    masters = [
        _example("Golden: 0.539 model EV-prob vs +100 (implied 0.5, EV 7.8%)", 100, 0.539, ev_prob=0.539),
        _example("Kitayama outright +17500 @ 0.69% model", 17500, 0.0069),
        _example("McNealy top5 +1300 @ 8.17% blend (EV uses dead-heat on calibrated)", 1300, 0.0817, ev_prob=0.0817 * (1.0 - config.DEAD_HEAT_DISCOUNT_TOP5)),
        _example("Min Woo Lee -130 @ 62.8% model", -130, 0.628),
        _example("Knapp +8000 @ 0.5% model (illustrative)", 8000, 0.005),
        _example("Spaun +10026 @ 0.5% model (illustrative)", 10026, 0.005),
    ]
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_snippet": {
            "DEAD_HEAT_DISCOUNT_TOP5": config.DEAD_HEAT_DISCOUNT_TOP5,
            "DEAD_HEAT_DISCOUNT_TOP10": config.DEAD_HEAT_DISCOUNT_TOP10,
            "DEAD_HEAT_DISCOUNT_TOP20": config.DEAD_HEAT_DISCOUNT_TOP20,
        },
        "clv_note": "multiplicative_devig in src/clv.py applies to CLV analytics, not card market_prob",
        "masters_style_examples": masters,
        "top15_status": "skipped_in_value_pipeline_until_fully_wired",
    }


def main() -> None:
    out_dir = ROOT / "output" / "audits"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    payload = build_report()
    jpath = out_dir / f"ev_math_{ts}.json"
    mpath = out_dir / f"ev_math_{ts}.md"
    jpath.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    lines = [
        f"# EV math audit ({ts} UTC)",
        "",
        "## Config (dead heat)",
        "",
        "```json",
        json.dumps(payload["config_snippet"], indent=2),
        "```",
        "",
        "## Masters-style examples",
        "",
    ]
    for row in payload["masters_style_examples"]:
        lines.append(f"### {row['name']}")
        lines.append("")
        lines.append(f"- American: {row['american']}")
        lines.append(f"- Raw implied: {row['raw_implied_prob']:.6f}")
        lines.append(f"- Decimal: {row['decimal_odds']}")
        lines.append(f"- EV (from ev_prob): **{row['ev_pct']}**")
        lines.append("")
    lines.append("## top15")
    lines.append("")
    lines.append(payload["top15_status"])
    lines.append("")
    mpath.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {jpath.relative_to(ROOT)}")
    print(f"Wrote {mpath.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
