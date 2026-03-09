"""Markdown and manifest generation for research proposals."""

from __future__ import annotations

import json
import os
import re
from typing import Any


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "proposal"


def write_research_dossier(
    *,
    proposal: dict[str, Any],
    evaluation: dict[str, Any],
    repro_metadata: dict[str, Any],
    output_dir: str,
) -> dict[str, str]:
    os.makedirs(output_dir, exist_ok=True)

    proposal_id = proposal["id"]
    proposal_name = proposal.get("name") or f"proposal_{proposal_id}"
    slug = _slugify(proposal_name)
    markdown_path = os.path.join(output_dir, f"{proposal_id}_{slug}.md")
    manifest_path = os.path.join(output_dir, f"{proposal_id}_{slug}.json")

    summary = evaluation["summary_metrics"]
    baseline = evaluation["baseline_summary_metrics"]
    guardrails = evaluation["guardrail_results"]
    segmented = evaluation.get("segmented_metrics", {})
    config_json = proposal.get("strategy_config_json") or "{}"
    theory_metadata = json.loads(proposal.get("theory_metadata_json") or "{}")

    markdown = f"""# Research Dossier: {proposal_name}

## Hypothesis
{proposal.get("hypothesis", "")}

## Theory Metadata
- Title: {theory_metadata.get("title", "n/a")}
- Source: {theory_metadata.get("source_type", proposal.get("source", "unknown"))}
- Why it may work: {theory_metadata.get("why_it_may_work", "n/a")}
- Novelty score: {theory_metadata.get("novelty_score", "n/a")}
- Ranking hint: {theory_metadata.get("ranking_hint", "n/a")}

## Synthetic Odds Warning
This backtest uses synthetic DataGolf-derived historical odds, not true sportsbook market tape. Treat ROI as directional research evidence, not sportsbook-true profit proof.

## Candidate Configuration
```json
{json.dumps(json.loads(config_json), indent=2, sort_keys=True)}
```

## Summary
- Weighted ROI: {summary.get("weighted_roi_pct", 0)}
- Unweighted ROI: {summary.get("unweighted_roi_pct", 0)}
- Total Bets: {summary.get("total_bets", 0)}
- Weighted CLV: {summary.get("weighted_clv_avg", 0)}
- Weighted Calibration Error: {summary.get("weighted_calibration_error", 0)}
- Max Drawdown: {summary.get("max_drawdown_pct", 0)}

## Baseline Comparison
- Baseline Weighted ROI: {baseline.get("weighted_roi_pct", 0)}
- Baseline Unweighted ROI: {baseline.get("unweighted_roi_pct", 0)}
- Baseline Weighted CLV: {baseline.get("weighted_clv_avg", 0)}
- Baseline Weighted Calibration Error: {baseline.get("weighted_calibration_error", 0)}

## Guardrail Results
- Passed: {guardrails.get("passed", False)}
- Verdict: {guardrails.get("verdict", "needs_review")}
- Reasons: {", ".join(guardrails.get("reasons", [])) or "none"}

## Segment Summary
```json
{json.dumps(segmented, indent=2, sort_keys=True)}
```

## Evaluation Windows
```json
{json.dumps(evaluation.get("splits", []), indent=2, sort_keys=True)}
```
"""

    with open(markdown_path, "w", encoding="utf-8") as handle:
        handle.write(markdown)

    manifest = {
        "proposal_id": proposal_id,
        "proposal_name": proposal_name,
        "seed": repro_metadata.get("seed"),
        "program_version": repro_metadata.get("program_version"),
        "code_commit": repro_metadata.get("code_commit"),
        "evaluation_windows": evaluation.get("splits", []),
        "artifact_markdown_path": markdown_path,
        "artifact_manifest_path": manifest_path,
    }
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)

    return {"markdown_path": markdown_path, "manifest_path": manifest_path}
