import copy
import gzip
import json
import sqlite3

import pytest

from src.history_reconciliation import digest, load_vault, outcome_value, reconcile, write_store


CALENDAR = [{"key": "pga:2026:018", "year": 2026, "provider_event_id": "018", "name": "Real Event",
             "aliases": ["Real Event"], "starts_on": "2026-04-16", "ends_on": "2026-04-19", "source_url": "https://example.test/event"}]


def observation(sid, table, row, ordinal=1):
    return {"type": "row", "source_id": sid, "table": table, "ordinal": ordinal, "row": row, "row_sha256": digest(row)}


def fixture():
    rows = [observation("a", "tournaments", {"id": 1, "event_id": "018", "year": 2026, "name": "Real Event"}),
            observation("a", "picks", {"id": 2, "tournament_id": 1, "source": "cockpit", "bet_type": "matchup",
                                       "market_type": "tournament_matchups", "player_key": "one", "opponent_key": "two",
                                       "market_book": "book", "market_odds": "+120", "model_prob": .6, "ev": .32,
                                       "model_variant": "baseline", "model_config_hash": "original", "created_at": "2026-04-14 12:00:00"}),
            observation("a", "pick_outcomes", {"id": 3, "pick_id": 2, "profit": 1.2, "stake": 1, "hit": 1,
                                               "actual_finish": "win vs loss", "odds_decimal": 2.2})]
    return {"sources": {"a": {"kind": "test"}}, "streams": {}, "rows": rows}


def add_copy(vault, *, change=None):
    vault["sources"]["b"] = {"kind": "test"}
    for obs in copy.deepcopy(vault["rows"][:3]):
        obs["source_id"] = "b"
        if change:
            change(obs)
        obs["row_sha256"] = digest(obs["row"])
        vault["rows"].append(obs)


def test_repeat_archives_collapse_but_all_provenance_survives():
    v = fixture()
    add_copy(v)
    untouched = copy.deepcopy(v)
    decisions, report, links = reconcile(v, CALENDAR)
    assert v == untouched
    assert len(decisions) == 1
    assert decisions[0]["observation_count"] == 2
    assert decisions[0]["source_count"] == 2
    assert decisions[0]["eligible_for_retrospective_selection"]
    assert len(links) == 6
    lane = report["markets"][0]["lanes"][0]
    assert lane["profit"] == 1.2 and lane["wins"] == 1


def test_equivalent_numeric_and_text_quotes_do_not_inflate_profit():
    v = fixture()
    add_copy(v, change=lambda o: o["row"].update(market_odds=120) if o["table"] == "picks" else None)
    d, r, _ = reconcile(v, CALENDAR)
    assert len(d) == 1
    assert r["markets"][0]["lanes"][0]["profit"] == 1.2


def test_source_local_ids_do_not_join_between_generations():
    v = fixture()
    v["sources"]["b"] = {"kind": "test"}
    v["rows"][-1]["source_id"] = "b"
    d, _, _ = reconcile(v, CALENDAR)
    assert d[0]["settlement"] == "ungraded"


@pytest.mark.parametrize("field,value", [("model_prob", .7), ("model_config_hash", "changed"), ("market_type", "round_matchups")])
def test_changed_forecast_contract_or_model_stays_conflict(field, value):
    v = fixture()
    add_copy(v, change=lambda o: o["row"].update({field: value}) if o["table"] == "picks" else None)
    d, _, _ = reconcile(v, CALENDAR)
    assert len(d) == 1 and d[0]["status"] == "conflict"
    assert d[0]["profit"] is None
    assert not d[0]["eligible_for_retrospective_selection"]


def test_changed_settlement_does_not_select_favorable_version():
    v = fixture()
    add_copy(v, change=lambda o: o["row"].update(profit=-1, hit=0, actual_finish="loss vs win") if o["table"] == "pick_outcomes" else None)
    d, r, _ = reconcile(v, CALENDAR)
    assert len(d) == 1 and d[0]["settlement"] == "conflict"
    assert r["markets"][0]["lanes"][0]["roi"] is None


def test_recovery_reinsertions_do_not_double_count_or_infer_first_time():
    v = fixture()
    add_copy(v, change=lambda o: o["row"].update(created_at="2026-09-13") if o["table"] == "picks" else None)
    d, r, links = reconcile(v, CALENDAR)
    assert len(d) == 1 and len(links) == 6
    assert d[0]["recorded_at"] is None
    assert "ambiguous_quote_repetition" in d[0]["issues"]
    assert not d[0]["included_in_paper_record"]
    assert r["markets"][0]["lanes"][0]["profit"] is None


def test_recovery_lineage_is_an_exclusion_signal_not_an_earlier_quote():
    v = fixture()
    ledger = {"source_id": "a", "tournament_id": 1, "bet_type": "matchup", "player_key": "one", "opponent_key": "two",
              "book": "book", "odds": "+120", "event_id": "018", "year": 2026, "source_origin": "restore",
              "lane": "cockpit", "model_variant": "baseline",
              "ordinal": 999, "row_sha256": "preserved", "generated_at": "2026-01-01"}
    d, _, _ = reconcile(v, CALENDAR, lineage=[ledger])
    assert d[0]["included_in_paper_record"]
    assert not d[0]["eligible_for_retrospective_selection"]
    assert d[0]["recovery_lineage_candidates"][0]["ordinal"] == 999


def test_18_holes_needs_round_not_a_guessed_event_date():
    v = fixture()
    v["rows"][1]["row"]["market_type"] = "round_matchups"
    d, r, _ = reconcile(v, CALENDAR)
    assert d[0]["status"] == "incomplete" and "missing_round" in d[0]["issues"]
    assert not d[0]["included_in_paper_record"]
    assert r["markets"][1]["lanes"][0]["roi"] is None


@pytest.mark.parametrize("recorded,timing", [("2026-01-01T00:00:00+00:00", "restore_placeholder"),
                                               ("2026-04-20", "recorded_after_event"), ("2026-04-16T01:00:00", "recorded_during_event")])
def test_backfills_and_same_day_records_do_not_justify_selection(recorded, timing):
    v = fixture()
    v["rows"][1]["row"]["created_at"] = recorded
    d, _, _ = reconcile(v, CALENDAR)
    assert d[0]["chronology"] == timing and not d[0]["eligible_for_retrospective_selection"]


def test_leading_zero_provider_id_and_fixture_exclusion_are_exact():
    v = fixture()
    v["rows"][0]["row"]["event_id"] = "18"
    d, _, _ = reconcile(v, CALENDAR)
    assert d[0]["status"] == "unresolved_event"
    v["rows"][0]["row"].update(event_id="123", name="Test Event")
    d, r, _ = reconcile(v, CALENDAR)
    assert not d and r["coverage"]["fixture_pick_observations_excluded"] == 1


def test_void_loss_and_quote_mismatch_excluded():
    assert "void_has_nonzero_profit" in outcome_value({"profit": -1, "stake": 1, "hit": 0, "actual_finish": "void vs void"})[3]
    assert "contradictory_matchup_result" in outcome_value({"profit": -1, "stake": 1, "hit": 0, "actual_finish": "loss vs loss"})[3]
    v = fixture()
    v["rows"][2]["row"]["odds_decimal"] = 1.8
    d, _, _ = reconcile(v, CALENDAR)
    assert d[0]["status"] == "conflict" and "settlement_quote_mismatch" in d[0]["issues"]


def test_zero_return_does_not_invent_push_or_void():
    assert outcome_value({"profit": 0, "stake": 1, "hit": 0, "actual_finish": "CUT vs CUT"})[0] == "zero_return"


def test_missing_calendar_coverage_is_visible():
    v = fixture()
    extra = dict(CALENDAR[0], key="pga:2026:future", name="Future", starts_on="2026-11-01", ends_on="2026-11-04")
    _, r, _ = reconcile(v, CALENDAR + [extra])
    assert len(r["events"]) == 2 and r["events"][1]["records"] == 0
    assert r["events"][1]["state"] == "upcoming"


def test_unknown_round_cards_still_show_18h_coverage_without_settlement():
    v = fixture()
    card = {"input_sha256": "file", "line": 1, "canonical_event_key": "pga:2026:018", "market": "18h_round_unknown"}
    original = copy.deepcopy(card)
    _, r, _ = reconcile(v, CALENDAR, cards=[card])
    assert {"key": "18h", "records": 0, "cards": 1} in r["events"][0]["markets"]
    assert r["markets"][1]["lanes"][0]["roi"] is None
    assert card == original


def test_exclusive_derived_store_retains_every_observation(tmp_path):
    v = fixture()
    d, _, links = reconcile(v, CALENDAR)
    path = tmp_path / "derived.sqlite"
    write_store(path, v, d, links, [])
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        assert db.execute("select count(*) from observations").fetchone()[0] == 3
        assert db.execute("pragma integrity_check").fetchone()[0] == "ok"
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        write_store(path, v, d, links, [])
    assert path.read_bytes() == original


def test_salvage_preserved_but_never_promoted_to_profit(tmp_path):
    v = fixture()
    add_copy(v)
    v["sources"]["b"].update(recovery_status="salvaged_unverified", recovery_method="test_recover")
    for obs in v["rows"][3:]:
        obs.update(provenance_status="salvaged_unverified", primary_performance_eligible=False, input_sql_sha256="sql-line-hash")
    d, r, links = reconcile(v, CALENDAR)
    assert len(d) == 1 and d[0]["observation_count"] == 1
    assert r["coverage"]["salvaged_observations"] == 3
    assert r["coverage"]["salvaged_exact_payload_matches"] == 3
    path = tmp_path / "salvage.sqlite"
    write_store(path, v, d, links, [])
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM observations").fetchone()[0] == 6
        envelope = json.loads(db.execute("SELECT envelope_json FROM observations WHERE source_id='b' LIMIT 1").fetchone()[0])
        assert envelope["input_sql_sha256"] == "sql-line-hash" and not envelope["primary_performance_eligible"]


def test_partial_stream_is_not_complete_evidence():
    v = fixture()
    v["streams"][("a", "picks")] = {"state": "partial"}
    d, r, _ = reconcile(v, CALENDAR)
    assert not d and r["coverage"]["partial_stream_observations_excluded"] == 1


def test_truncated_or_tampered_vault_rejected(tmp_path):
    obs = fixture()["rows"][0]
    lines = [{"type": "source_begin", "source_id": "a", "source": {}},
             {"type": "table_begin", "source_id": "a", "table": "tournaments"}, obs,
             {"type": "table_end", "source_id": "a", "table": "tournaments", "rows": 1, "state": "complete"},
             {"type": "source_end", "source_id": "a", "source_metadata_unchanged": True}]
    path = tmp_path / "vault.gz"
    def write(xs):
        with gzip.open(path, "wt") as f:
            f.write("\n".join(json.dumps(x) for x in xs))
    write(lines)
    assert len(load_vault(path)["rows"]) == 1
    write(lines[:-1])
    with pytest.raises(ValueError, match="Truncated"):
        load_vault(path)
    lines[2]["row"]["name"] = "tampered"
    write(lines)
    with pytest.raises(ValueError, match="hash mismatch"):
        load_vault(path)
