"""Recovery totals must not turn copies, notices or fixtures into wagering claims."""
import hashlib
import json

import pytest

from src.prediction_history_coverage import build_coverage, report_from_latest


def sources():
    cards = [{"sha256": str(i) * 64, "event_label": event, "generated_label": generated,
              "prediction_observations": n, "sources": [{"source_path": "/Users/private/chat.txt"}]}
             for i, event, generated, n in [
                 (1, "WM Phoenix Open", "2026-02-07 16:00", 20),
                 (2, "WM Phoenix Open 2026", "2026-02-07 18:00", 21),
                 (3, "Zurich Classic", None, 0)]]
    md = {"files": cards, "counts": {"ranking": 41}}
    structured = {"files": [{"sha256": "4" * 64, "observations": 72}], "counts": {"saved_ranking": 72}}
    inventory = {"files": cards + [cards[0]], "complete_cards_with_indexed_forecast_observations": 2,
                 "complete_card_payloads": 3}
    return md, structured, inventory


def test_deduplicated_card_versions_aliases_and_notices_do_not_become_bets():
    report = build_coverage(*sources(), as_of="2026-10-16", sources={"markdown_index_sha256": "a" * 64})
    assert report["summary"] == {"complete_card_versions": 2, "named_event_labels": 1,
                                 "complete_notices_without_indexed_forecasts": 1, "indexed_observations": 113,
                                 "payloads_with_observations": 3, "distinct_preserved_payloads": 4}
    assert report["events"][0]["card_versions"] == 2
    assert report["events"][0]["status"] == "publication_unverified"
    assert report["qualification"]["independent_bet_count"] is None
    assert report["qualification"]["roi_pct"] is None
    assert report["qualification"]["clv_pct"] is None
    assert report["qualification"]["generation_timezone"] == "unknown"
    assert report["additional_evidence"] == []
    assert "/Users/" not in json.dumps(report)
    assert "sources" not in report["events"][0]


@pytest.mark.parametrize("edit", ["conflict", "fixture", "cross_generation"])
def test_rejects_conflicting_or_mismatched_inventory(edit):
    md, structured, inventory = sources()
    if edit == "conflict":
        inventory["files"][-1] = {**inventory["files"][0], "prediction_observations": 30}
    elif edit == "fixture":
        inventory["files"][0]["event_label"] = "Future Event"
    else:
        md["files"] = []
    with pytest.raises(ValueError):
        build_coverage(md, structured, inventory, as_of="2026-10-16", sources={})


def test_rejects_tampered_generation_before_building(tmp_path):
    current = {}
    for key, payload in zip(("markdown_index", "structured_index", "complete_card_inventory"), sources()):
        p = tmp_path / (key + ".json")
        raw = json.dumps(payload).encode()
        p.write_bytes(raw)
        current[key] = {"path": str(p), "sha256": hashlib.sha256(raw).hexdigest()}
    latest = tmp_path / "LATEST.json"
    latest.write_text(json.dumps({"current": current}))
    report_from_latest(latest, as_of="2026-10-16")
    (tmp_path / "complete_card_inventory.json").write_text("{}")
    with pytest.raises(ValueError, match="digest mismatch"):
        report_from_latest(latest, as_of="2026-10-16")
