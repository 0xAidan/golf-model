import gzip
import json
from pathlib import Path

import pytest

from src.prediction_archive import build_archive, digest, parse_json_forecasts, parse_markdown


CARD = b"""# Fixture Open \xe2\x80\x94 Betting Card
**Generated:** 2026-02-17 15:04

## Model Rankings
| Rank | Player | Composite | Form |
|------|--------|-----------|------|
| 1 | A Player | 78.2 | 81.0 |

## Top 10 Finish
- **VALUE** **A Player** (#1) \xe2\x80\x94 +230 @ bet365, model 34.1% vs market 30.3%, EV 12.4%

## Round Matchups
| Pick | vs | Odds | Model Win% | EV |
|------|----|------|------------|----|
| A Player | B Player | -110 | 58.0% | 10.7% |

## Matchup Edges
- **A Player** over B Player \xe2\x80\x94 edge: 12.0 pts (form)
"""


def test_all_prediction_kinds_keep_source_lines_and_strings_without_inventing_rules():
    result = parse_markdown(CARD)
    assert result["generated_label"] == "2026-02-17 15:04"
    assert [r["kind"] for r in result["observations"]] == ["ranking", "priced_prediction", "priced_prediction", "matchup_projection"]
    assert result["observations"][2]["fields"]["model_win"] == "58.0%"
    assert result["observations"][2]["section"].endswith("Round Matchups")
    assert "round_num" not in result["observations"][2]
    assert all(not r["publication_verified"] and not r["settlement_inferred"] for r in result["observations"])
    for row in result["observations"]:
        assert CARD.decode().splitlines()[row["line"] - 1] == row["raw_text"]


def test_code_fences_do_not_turn_documentation_into_forecasts():
    result = parse_markdown(b"# Documentation\n```markdown\n" + CARD + b"\n```\n")
    assert result["observations"] == []


def test_hash_mismatch_is_rejected():
    with pytest.raises(ValueError, match="hash"):
        parse_markdown(CARD, source_hash="wrong")


def test_sandbox_model_declaration_is_preserved_without_inventing_publication_context():
    card = CARD.replace(b"## Model Rankings", b"**Baseline Strategy:** optuna_241 via `sandbox`\n\n## Model Rankings")
    result = parse_markdown(card)
    assert result["artifact_role"] == "original_card"
    assert result["declared_execution_context"] == "sandbox"
    assert len(result["observations"]) == 4
    assert all(row["declared_execution_context"] == "sandbox" for row in result["observations"])


def test_json_forecast_rows_keep_exact_payload_pointer_and_model_lane():
    payload = {"generated_at": "2026-02-01T10:00:00Z", "upcoming_tournament": {
        "event_name": "Fixture Open", "source_event_id": "123", "model_variant": "baseline",
        "rankings": [{"player": "A Player", "rank": 1, "composite": 71.23}],
        "matchup_bets_all_books": [{"pick": "A Player", "opponent": "B Player", "odds": "+120"}]}}
    result = parse_json_forecasts(json.dumps(payload).encode())
    assert len(result["observations"]) == 2
    first = result["observations"][0]
    assert first["json_pointer"] == "/upcoming_tournament/rankings/0"
    assert first["payload"] == payload["upcoming_tournament"]["rankings"][0]
    assert first["model_variant"] == "baseline"
    assert first["source_event_id"] == "123"
    assert not first["publication_verified"]


def test_provenance_metadata_is_not_a_prediction():
    result = parse_json_forecasts(b'{"event_name":"Open", "runtime_settings":{"markets":["win"]}}')
    assert result["state"] == "no_supported_forecast_arrays"
    assert result["observations"] == []


def test_api_wrapper_and_frozen_rankings_remain_distinct_from_live_rows():
    payload = {"snapshot": {"generated_at": "2026-06-04", "live_tournament": {
        "event_name": "Memorial", "rankings": [{"player": "A", "rank": 1}],
        "frozen_pre_teeoff_rankings": [{"player": "A", "rank": 2}]}}}
    result = parse_json_forecasts(json.dumps(payload).encode())
    rows = result["observations"]
    assert [r["json_pointer"] for r in rows] == ["/snapshot/live_tournament/rankings/0", "/snapshot/live_tournament/frozen_pre_teeoff_rankings/0"]
    assert rows[1]["kind"] == "ranking_frozen_pre_teeoff_rankings"
    assert rows[1]["generated_label"] == "2026-06-04"
    assert rows[1]["publication_verified"] is False


def test_content_dedupe_retains_all_source_references_and_compressed_bytes(tmp_path):
    corpus = tmp_path / "input"
    corpus.mkdir()
    sha = digest(CARD)
    (corpus / "card.md.gz").write_bytes(gzip.compress(CARD, mtime=0))
    refs = [{"sha256": sha, "corpus_path": "card.md.gz", "source_path": f"source-{i}.md"} for i in range(2)]
    (corpus / "sources.jsonl").write_text("".join(json.dumps(r) + "\n" for r in refs))
    target = tmp_path / "run"
    result = build_archive([corpus], target)
    assert result["source_files"] == 1
    assert result["source_references"] == 2
    assert len(result["files"][0]["sources"]) == 2
    assert result["files"][0]["sources"][0]["resolved_corpus_path"] == str(corpus / "card.md.gz")
    assert result["files"][0]["sources"][0]["corpus_path"] == "card.md.gz"
    assert len((target / "prediction-observations.jsonl").read_text().splitlines()) == 4
    assert gzip.decompress((corpus / "card.md.gz").read_bytes()) == CARD
    with pytest.raises(FileExistsError):
        build_archive([corpus], target)


def test_explicit_research_source_context_is_not_promoted_by_card_heading(tmp_path):
    corpus = tmp_path / "input"
    corpus.mkdir()
    sha = digest(CARD)
    (corpus / "card.md").write_bytes(CARD)
    source = {"sha256": sha, "corpus_path": "card.md", "source_path": "output/sandbox/card.md", "source_kind": "sandbox_or_backtest_output"}
    (corpus / "sources.jsonl").write_text(json.dumps(source) + "\n")
    result = build_archive([corpus], tmp_path / "run")
    assert result["files"][0]["artifact_role"] == "research_card"
    assert result["named_original_card_observations"] == {}
    assert sum(result["counts_by_artifact_role"]["research_card"].values()) == 4
