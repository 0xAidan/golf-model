"""Source identity and price qualification must survive historical recovery."""
import gzip
import json
import sqlite3

import pytest

from src.historical_market_quotes import (
    Capture, QuoteRequest, analyze_quote, digest, fetch, ingest_capture, open_vault,
    quote_analyses, reconcile_forecasts, summarize,
)


def capture(payload, *, at="2026-10-16T03:30:00+00:00", status=200):
    body = json.dumps(payload).encode() if not isinstance(payload, bytes) else payload
    return Capture(body, status, at, "test", {"Date": "Fri, 16 Oct 2026 03:30:00 GMT"})


def catalog(root):
    ingest_capture(root, QuoteRequest("pga", kind="event-list"), capture([
        {"event_id": 480, "calendar_year": 2026, "event_name": "Truist Championship", "outrights": "yes", "matchups": "yes"},
    ]))


def request(**overrides):
    values = dict(tour="pga", event_id="480", year=2026, book="pinnacle", market="win")
    values.update(overrides)
    return QuoteRequest(**values)


def payload(**overrides):
    value = {
        "event_id": "480", "year": 2026, "season": 2026,
        "event_name": "Truist Championship", "book": "pinnacle", "market": "win",
        "odds": [{"dg_id": 123, "player_name": "Golfer, One", "open_odds": 3.0, "close_odds": 2.5,
                  "open_time": "2026-05-05 08:03", "close_time": "2026-05-07 10:37",
                  "bet_outcome_numeric": 0, "bet_outcome_text": "loss"}],
    }
    value.update(overrides)
    return value


def test_exact_raw_response_and_acquisitions_are_preserved_idempotently(tmp_path):
    catalog(tmp_path)
    original = capture(payload())
    first = ingest_capture(tmp_path, request(), original)
    repeat = ingest_capture(tmp_path, request(), original)
    assert first["new_quote_rows"] == 1 and repeat["new_quote_rows"] == 0
    assert first["source_id"] == repeat["source_id"]
    raw = gzip.decompress((tmp_path / first["raw_path"]).read_bytes())
    assert raw == original.body
    assert digest(raw) == first["raw_sha256"]
    assert summarize(tmp_path)["acquisitions"] == 2  # catalog + original capture
    ingest_capture(tmp_path, request(), capture(payload(), at="2026-10-17T03:30:00Z"))
    assert summarize(tmp_path)["acquisitions"] == 3
    assert summarize(tmp_path)["quote_rows"] == 1


@pytest.mark.parametrize("table", ["sources", "acquisitions", "event_catalog", "quote_rows"])
def test_evidence_tables_refuse_updates_and_deletes(tmp_path, table):
    catalog(tmp_path)
    ingest_capture(tmp_path, request(), capture(payload()))
    conn = open_vault(tmp_path)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(f"DELETE FROM {table}")
    column = "source_id"
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(f"UPDATE {table} SET {column}={column}")
    conn.close()


@pytest.mark.parametrize("override,reason", [
    ({"event_id": "14"}, "response_event_id_mismatch"),
    ({"year": 2025}, "response_year_mismatch"),
    ({"book": "fanduel"}, "response_book_mismatch"),
    ({"book": "DG-Base"}, "response_book_mismatch"),
    ({"market": "top_20"}, "response_market_mismatch"),
    ({"tour": "euro"}, "response_tour_mismatch"),
])
def test_response_identity_mismatch_is_retained_and_never_qualified(tmp_path, override, reason):
    catalog(tmp_path)
    result = ingest_capture(tmp_path, request(), capture(payload(**override)))
    assert result["state"] == "identity_rejected" and reason in result["validation"]
    row = quote_analyses(tmp_path)[0]
    assert not row["identity_verified"]
    assert row["vendor_open_close_pct"] is None and row["qualified_clv_pct"] is None
    assert (tmp_path / result["raw_path"]).exists()


def test_naive_times_and_missing_settlement_do_not_claim_verified_clv(tmp_path):
    catalog(tmp_path)
    ingest_capture(tmp_path, request(), capture(payload()))
    row = quote_analyses(tmp_path)[0]
    assert row["vendor_open_close_pct"] == pytest.approx(20)
    assert row["qualified_clv_pct"] is None and row["fair_close_ev_pct"] is None
    assert set(row["qualification_reasons"]) == {
        "quote_time_timezone_unverified", "market_start_unverified", "settlement_contract_unverified",
    }
    assert row["open_time_raw"] == "2026-05-05 08:03" and not row["devig_applied"]


def test_timing_and_contract_are_required_even_for_valid_identity():
    row = {"identity_verified": True, "book": "pinnacle", "open_decimal": 3, "close_decimal": 2.5,
           "open_time_raw": "2026-05-05T08:03:00Z", "close_time_raw": "2026-05-07T10:37:00Z",
           "settlement_rule": "Bets are void in event of tie"}
    source = {"source_sha256": "b" * 64, "json_pointer": "/event/start"}
    result = analyze_quote(row, catalog_verified=True, market_start_at="2026-05-07T11:00:00Z", market_start_source=source)
    assert result["qualified_clv_pct"] == pytest.approx(20)
    assert result["close_verified"]
    late = analyze_quote(row, catalog_verified=True, market_start_at="2026-05-07T10:00:00Z", market_start_source=source)
    assert late["qualified_clv_pct"] is None
    assert "closing_not_before_market_start" in late["qualification_reasons"]
    unproven = analyze_quote(row, catalog_verified=True, market_start_at="2026-05-07T11:00:00Z")
    assert "market_start_unverified" in unproven["qualification_reasons"]


def test_two_sided_matchup_preserves_explicit_contract_without_inventing_times(tmp_path):
    catalog(tmp_path)
    odds = [{"bet_type": "72-hole Match", "p1_dg_id": 1, "p2_dg_id": 2,
             "p1_player_name": "Golfer, One", "p2_player_name": "Golfer, Two",
             "p1_open": 1.79, "p1_close": 1.76, "p2_open": 2.04, "p2_close": 2.1,
             "p1_outcome": 1.0, "p2_outcome": 0.0, "p1_outcome_text": "win", "p2_outcome_text": "loss",
             "tie_rule": "Bets are void in event of tie", "open_time": "2026-05-05 08:30", "close_time": "2026-05-07 08:30"}]
    data = payload(odds=odds)
    data.pop("market")
    result = ingest_capture(tmp_path, request(kind="matchups", market=None), capture(data))
    assert result["new_quote_rows"] == 2
    rows = quote_analyses(tmp_path)
    assert {r["player_dg_id"] for r in rows} == {1, 2}
    assert {r["market"] for r in rows} == {"72-hole Match"}
    assert all(r["json_pointer"] == "/odds/0" and not r["close_verified"] for r in rows)
    assert {r["side"] for r in rows} == {"p1", "p2"}


def test_three_ball_keeps_third_player_and_cannot_join_a_two_way_forecast(tmp_path):
    catalog(tmp_path)
    odds = [{"bet_type": "R1 3-Ball", "p1_dg_id": 1, "p2_dg_id": 2, "p3_dg_id": 3,
             "p1_player_name": "One", "p2_player_name": "Two", "p3_player_name": "Three",
             "p1_open": 3, "p1_close": 2.5, "p2_open": 4, "p2_close": 4.5, "p3_open": 2, "p3_close": 2.2}]
    data = payload(odds=odds)
    data.pop("market")
    ingest_capture(tmp_path, request(kind="matchups", market=None), capture(data))
    rows = quote_analyses(tmp_path)
    assert len(rows) == 3 and {r["side"] for r in rows} == {"p1", "p2", "p3"}
    assert all(r["family"] == "three_ball" and r["contract_players_json"] == "[1,2,3]" for r in rows)
    assert all(r["opponent_dg_id"] is None for r in rows)
    forecast = {"source_sha256": "a" * 64, "source_pointer": "/picks/0", "identity_provenance": "exact mapping",
                "tour": "pga", "event_id": "480", "year": 2026, "book": "pinnacle", "market": "R1 3-Ball", "player_dg_id": 1, "odds_decimal": 3}
    assert reconcile_forecasts([forecast], rows)[0]["matched_quote_ids"] == []


def test_extra_categorical_tie_outcome_is_not_a_guessed_player_or_binary_matchup(tmp_path):
    catalog(tmp_path)
    odds = [{"bet_type": "R3 Match-Up", "p1_dg_id": 1, "p2_dg_id": 2, "p3_dg_id": 0,
             "p1_player_name": "One", "p2_player_name": "Two", "p3_player_name": "Halve",
             "p1_open": 3, "p1_close": 2.5, "p2_open": 4, "p2_close": 4.5, "p3_open": 8, "p3_close": 8.5,
             "tie_rule": "Separate bet offered for tie"}]
    data = payload(odds=odds)
    data.pop("market")
    ingest_capture(tmp_path, request(kind="matchups", market=None), capture(data))
    rows = quote_analyses(tmp_path)
    assert len(rows) == 3
    assert all(r["family"] == "multi_outcome_matchup" and not r["identity_verified"] for r in rows)
    assert all(r["vendor_open_close_pct"] is None for r in rows)
    assert any(r["player_dg_id"] is None and r["player_name"] == "Halve" for r in rows)


@pytest.mark.parametrize("kind", ["DG-Base", "DG-CH", "DataGolf"])
def test_synthetic_model_prices_are_not_supported_sportsbooks(kind):
    with pytest.raises(ValueError, match="sportsbook"):
        request(book=kind)


@pytest.mark.parametrize("body,status,state", [(b"not json", 200, "invalid_json"), (b'{"error":"subscription required"}', 403, "http_error"), (b"[]", 200, "unsupported_shape")])
def test_failed_sources_keep_raw_evidence_and_no_quote_rows(tmp_path, body, status, state):
    result = ingest_capture(tmp_path, request(), capture(body, status=status))
    assert result["state"] == state
    assert summarize(tmp_path)["quote_rows"] == 0
    assert gzip.decompress((tmp_path / result["raw_path"]).read_bytes()) == body


def test_missing_close_stays_unknown_and_empty_coverage_is_explicit(tmp_path):
    catalog(tmp_path)
    data = payload()
    data["odds"][0]["close_odds"] = None
    ingest_capture(tmp_path, request(), capture(data))
    row = quote_analyses(tmp_path)[0]
    assert row["vendor_open_close_pct"] is None
    assert "missing_or_invalid_price_pair" in row["qualification_reasons"]
    empty = ingest_capture(tmp_path, request(), capture(payload(odds=[])))
    assert empty["state"] == "empty_coverage" and empty["new_quote_rows"] == 0


def test_exact_forecast_join_uses_original_price_and_never_fills_missing_ids(tmp_path):
    catalog(tmp_path)
    data = payload()
    data["odds"][0]["open_odds"] = 4.0
    ingest_capture(tmp_path, request(), capture(data))
    forecasts = [{"source_sha256": "a" * 64, "source_pointer": "/picks/0", "identity_provenance": "exact source-local ID mapping",
                  "tour": "pga", "event_id": "480", "year": 2026, "book": "pinnacle", "market": "win",
                  "player_dg_id": 123, "opponent_dg_id": None, "odds_decimal": 3.0}]
    result = reconcile_forecasts(forecasts, quote_analyses(tmp_path))[0]
    assert result["recorded_forecast_price_vs_vendor_close_pct"] == pytest.approx(20)
    assert result["qualified_clv_pct"] is None and not result["executed_bet"]
    wrong_year = reconcile_forecasts([{**forecasts[0], "year": 2025}], quote_analyses(tmp_path))[0]
    assert wrong_year["matched_quote_ids"] == []
    missing_id = reconcile_forecasts([{**forecasts[0], "player_dg_id": None, "player_name": "Golfer, One"}], quote_analyses(tmp_path))[0]
    assert missing_id["matched_quote_ids"] == []  # Display-name match cannot guess a vendor ID.


def test_conflicting_close_revisions_are_not_silently_selected(tmp_path):
    catalog(tmp_path)
    ingest_capture(tmp_path, request(), capture(payload()))
    revised = payload()
    revised["odds"][0]["close_odds"] = 2.4
    ingest_capture(tmp_path, request(), capture(revised))
    forecast = {"source_sha256": "a" * 64, "source_pointer": "/picks/0", "identity_provenance": "exact mapping",
                "tour": "pga", "event_id": "480", "year": 2026, "book": "pinnacle", "market": "win", "player_dg_id": 123, "odds_decimal": 3}
    result = reconcile_forecasts([forecast], quote_analyses(tmp_path))[0]
    assert "conflicting_vendor_closing_versions" in result["qualification_reasons"]
    assert result["recorded_forecast_price_vs_vendor_close_pct"] is None


def test_transport_errors_never_expose_key_in_exception(monkeypatch):
    import requests
    key = "PRIVATE_TEST_TOKEN"
    def fail(*args, **kwargs):
        raise requests.exceptions.ConnectionError("secret query key=" + key)
    monkeypatch.setattr(requests, "get", fail)
    with pytest.raises(RuntimeError) as error:
        fetch(request(), api_key=key)
    assert key not in str(error.value)


def test_raw_hash_collision_or_modified_file_is_refused(tmp_path):
    original = capture(payload())
    first = ingest_capture(tmp_path, request(), original)
    (tmp_path / first["raw_path"]).write_bytes(gzip.compress(b"altered"))
    with pytest.raises(ValueError, match="hash verification"):
        ingest_capture(tmp_path, request(), original)
