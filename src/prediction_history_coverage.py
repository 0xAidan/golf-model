"""Sanitized inventory of preserved forecast artifacts, never a betting ledger.

This module imports no application/database code. Private file paths, raw chat
text and player-level payloads never enter the product report. Byte hashes bind
the inventory to the preserved recovery generation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import re

ALIASES = {
    "AT&T Pebble Beach Pro-Am 2026": "AT&T Pebble Beach Pro-Am",
    "Arnold Palmer Invitational presented by Mastercard": "Arnold Palmer Invitational",
    "WM Phoenix Open 2026": "WM Phoenix Open",
}
FIXTURES = {"test event", "current event", "future event", "next event", "live event"}
API_CAPTURES = {
    "9fb269051e7e3b7593e72f0a2f7361b53f894f2a672407627f2d20120778c31e": {
        "label": "Charles Schwab Challenge", "kind": "saved_api_response", "ranking_rows": 132,
        "frozen_ranking_rows": 132, "status": "capture_verified_publication_unverified"},
    "a42486578feab0a5ad4ef85fa3eeeeb17f91998c1cfe87b14a92df45f518708a": {
        "label": "the Memorial Tournament", "kind": "saved_api_subtree", "ranking_rows": 72,
        "frozen_ranking_rows": 72, "status": "capture_verified_publication_unverified"},
    "b6294332d54bac890f4799a911972f18ce68d0b849f2ce75691e34e8b6b0d54a": {
        "label": "RBC Canadian Open", "kind": "saved_api_subtree", "ranking_rows": 72,
        "frozen_ranking_rows": None, "status": "capture_verified_publication_unverified"},
}


def _label(value: object) -> str:
    label = str(value or "").strip()
    if not label or len(label) > 120 or any(ord(c) < 32 for c in label):
        raise ValueError("Invalid event label in recovered card inventory")
    if "/Users/" in label or "/opt/" in label or "://" in label:
        raise ValueError("A source path is not an event label")
    return ALIASES.get(label, label)


def _generated(value: object) -> str | None:
    text = str(value or "").strip()
    # Source-written wall-clock values have no known timezone. Preserve that
    # uncertainty: do not invent UTC or treat these as official event dates.
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?", text):
        return None
    try:
        return datetime.fromisoformat(text).isoformat(timespec="minutes")
    except ValueError:
        return None


def _count(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Invalid inventory count")
    return value


def build_coverage(markdown: dict, structured: dict, inventory: dict, *, as_of: str, sources: dict) -> dict:
    date.fromisoformat(as_of)
    cards: dict[str, dict] = {}
    for row in inventory["files"]:
        sha = str(row["sha256"])
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError("Invalid card digest")
        selected = {"label": _label(row.get("event_label")), "generated": _generated(row.get("generated_label")),
                    "observations": _count(row["prediction_observations"])}
        if selected["label"].lower() in FIXTURES:
            raise ValueError("Fixture included in named original-card inventory")
        if sha in cards and cards[sha] != selected:
            raise ValueError("Conflicting content-addressed card metadata")
        cards[sha] = selected
    with_forecasts = sum(row["observations"] > 0 for row in cards.values())
    if with_forecasts != inventory["complete_cards_with_indexed_forecast_observations"]:
        raise ValueError("Complete-card forecast count does not reconcile")
    if len(cards) != inventory["complete_card_payloads"]:
        raise ValueError("Complete-card count does not reconcile")

    groups: dict[str, list[dict]] = defaultdict(list)
    for sha, row in cards.items():
        if row["observations"]:
            groups[row["label"]].append({**row, "sha256": sha})
    # Source wrappers and headers never pass this boundary.
    by_sha = {row["sha256"]: row for row in markdown["files"]}
    for sha, row in cards.items():
        original = by_sha.get(sha)
        if original is None or original.get("prediction_observations") != row["observations"]:
            raise ValueError("Card inventory is not from this Markdown generation")
    events = []
    for label, versions in groups.items():
        times = sorted(v["generated"] for v in versions if v["generated"])
        events.append({"label": label, "card_versions": len(versions),
                       "first_generated": times[0] if times else None,
                       "last_generated": times[-1] if times else None,
                       "missing_generated_n": sum(v["generated"] is None for v in versions),
                       "observations": sum(v["observations"] for v in versions),
                       "status": "publication_unverified"})
    events.sort(key=lambda row: (row["first_generated"] or "9999", row["label"]))

    md_counts = {str(k): _count(v) for k, v in markdown["counts"].items()}
    json_counts = {str(k): _count(v) for k, v in structured["counts"].items()}
    total = sum(md_counts.values()) + sum(json_counts.values())
    files = [*markdown["files"], *structured["files"]]
    indexed_hashes = {r["sha256"] for r in files if r.get("prediction_observations", r.get("observations", 0))}
    all_hashes = {r["sha256"] for r in files}
    return {
        "schema_version": 1, "state": "recovered_source_inventory", "as_of": as_of,
        "basis": "Preserved source artifacts; versions, refreshes and research rows are not independent wagers.",
        "summary": {"complete_card_versions": with_forecasts, "named_event_labels": len(groups),
                    "complete_notices_without_indexed_forecasts": len(cards) - with_forecasts,
                    "indexed_observations": total, "payloads_with_observations": len(indexed_hashes),
                    "distinct_preserved_payloads": len(all_hashes)},
        "events": events, "observation_kinds": dict(sorted((Counter(md_counts) + Counter(json_counts)).items())),
        "sources": {str(k): str(v) for k, v in sources.items() if re.fullmatch(r"[0-9a-f]{64}", str(v))},
        "qualification": {"publication_verified": False, "independent_bet_count": None,
                          "roi_pct": None, "clv_pct": None, "generation_timezone": "unknown"},
        "additional_evidence": [{**API_CAPTURES[sha], "source_sha256": sha}
                                for sha in sorted(all_hashes & API_CAPTURES.keys())],
        "gaps": [
            "PGA Championship: full original field snapshot remains missing; a partial May 12 screenshot survives.",
            "Cloud-only research files and bounded filesystem listings remain outside confirmed recovery.",
            "No original 2025 published card was confirmed. Historical round inputs are a separate evidence class.",
            "Damaged-database salvage is preserved separately and excluded from verified performance and promotion.",
        ],
        "notes": [
            "Dates are source-written generation labels with unknown timezone, not official event dates or publication proof.",
            "Event titles are source labels. Restored or stale cards can carry an event title on an unrelated date.",
            "Every conflicting version remains in the private evidence archive; identical bytes share one payload.",
            "The smaller performance cohort has separate timing, event identity, price and settlement requirements.",
        ],
    }


def report_from_latest(latest_path: Path, *, as_of: str) -> dict:
    latest = json.loads(latest_path.read_text())
    loaded, hashes = {}, {}
    for key in ("markdown_index", "structured_index", "complete_card_inventory"):
        entry = latest["current"][key]
        raw = Path(entry["path"]).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != entry["sha256"]:
            raise ValueError(f"Recovery generation digest mismatch: {key}")
        loaded[key] = json.loads(raw)
        hashes[key + "_sha256"] = digest
    return build_coverage(loaded["markdown_index"], loaded["structured_index"], loaded["complete_card_inventory"],
                          as_of=as_of, sources=hashes)
