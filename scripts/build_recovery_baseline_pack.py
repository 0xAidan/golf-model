#!/usr/bin/env python3
"""Build baseline benchmark artifacts for recovery validation."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class CardStats:
    matchup_lines: int = 0
    placement_lines: int = 0
    total_bullet_bets: int = 0
    has_best_bets_section: bool = False
    has_matchup_section: bool = False
    has_methodology_marker: bool = False


BET_BULLET_RE = re.compile(r"^\s*[-*]\s+")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _compute_card_stats(text: str) -> CardStats:
    stats = CardStats()
    lower = text.lower()
    stats.has_best_bets_section = "best bets" in lower
    stats.has_matchup_section = "matchup" in lower
    stats.has_methodology_marker = "methodology" in lower

    lines = text.splitlines()
    in_matchup = False
    in_bets = False

    for raw in lines:
        line = raw.strip().lower()
        if line.startswith("#"):
            in_matchup = "matchup" in line
            in_bets = any(
                token in line for token in ("best bets", "value bets", "recommended bets", "card")
            )

        if BET_BULLET_RE.match(raw):
            stats.total_bullet_bets += 1
            if in_matchup or "vs" in line or " h2h " in f" {line} ":
                stats.matchup_lines += 1
            if any(token in line for token in ("top 5", "top5", "top 10", "top10", "top 20", "top20", "outright", "frl", "make cut")):
                stats.placement_lines += 1

    return stats


def _extract_card_date(path: Path) -> str | None:
    m = re.search(r"(20\d{6})", path.name)
    return m.group(1) if m else None


def build_baseline(config_path: Path, output_dir: Path) -> dict[str, Any]:
    config = json.loads(_read_text(config_path))
    events = config.get("events", [])
    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []

    for event in events:
        card_rel = event["card_path"]
        card_path = _repo_root() / card_rel
        method_rel = event.get("methodology_path")
        method_path = (_repo_root() / method_rel) if method_rel else None
        card_exists = card_path.exists()
        method_exists = bool(method_path and method_path.exists())
        card_stats = CardStats()
        if card_exists:
            card_stats = _compute_card_stats(_read_text(card_path))
        rows.append(
            {
                "event": event["event"],
                "label": event["label"],
                "card_path": card_rel,
                "card_exists": card_exists,
                "methodology_path": method_rel,
                "methodology_exists": method_exists,
                "card_date": _extract_card_date(card_path),
                "expected": event.get("expected", {}),
                "observed": {
                    "matchup_lines": card_stats.matchup_lines,
                    "placement_lines": card_stats.placement_lines,
                    "total_bullet_bets": card_stats.total_bullet_bets,
                    "has_best_bets_section": card_stats.has_best_bets_section,
                    "has_matchup_section": card_stats.has_matchup_section,
                    "has_methodology_marker": card_stats.has_methodology_marker,
                },
            }
        )

    pack = {
        "generated_at": now,
        "window_name": config.get("window_name"),
        "description": config.get("description"),
        "events": rows,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"baseline_pack_{stamp}.json"
    md_path = output_dir / f"baseline_pack_{stamp}.md"
    json_path.write_text(json.dumps(pack, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown(pack), encoding="utf-8")
    pack["artifacts"] = {"json": str(json_path), "markdown": str(md_path)}
    return pack


def _build_markdown(pack: dict[str, Any]) -> str:
    lines = [
        "# Recovery Baseline Pack",
        "",
        f"- Generated: {pack['generated_at']}",
        f"- Window: {pack.get('window_name')}",
        "",
        "| Event | Card | Exists | Matchup Lines | Placement Lines | Expected ROI |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in pack.get("events", []):
        expected = row.get("expected", {})
        lines.append(
            "| {event} | `{card}` | {exists} | {matchups} | {placements} | {roi} |".format(
                event=row["event"],
                card=row["card_path"],
                exists="yes" if row["card_exists"] else "no",
                matchups=row["observed"]["matchup_lines"],
                placements=row["observed"]["placement_lines"],
                roi=expected.get("roi_pct", "n/a"),
            )
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("- This artifact is the reference baseline pack for recovery validation.")
    lines.append("- Use this pack to compare pipeline outputs before and after fixes.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="docs/recovery_baseline_window.json",
        help="Path to recovery baseline config JSON (relative to repo root).",
    )
    parser.add_argument(
        "--output-dir",
        default="output/recovery",
        help="Directory where baseline artifacts are written (relative to repo root).",
    )
    args = parser.parse_args()

    root = _repo_root()
    config_path = (root / args.config).resolve()
    output_dir = (root / args.output_dir).resolve()

    if not config_path.exists():
        raise FileNotFoundError(f"Baseline config not found: {config_path}")

    pack = build_baseline(config_path, output_dir)
    print(json.dumps(pack["artifacts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
