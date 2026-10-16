"""CLV conventions stay explicit without rewriting the stored legacy series."""

import pytest

from src import clv


def test_quote_price_clv_rewards_the_better_taken_price():
    assert clv.quote_price_clv_pct(3.0, 2.5) == pytest.approx(20.0)
    assert clv.quote_price_clv_pct(2.5, 3.0) == pytest.approx(-100.0 / 6.0)


@pytest.mark.parametrize("taken,close", [(None, 2.5), (3.0, None), (1.0, 2.5), (3.0, 0), (float("inf"), 2.5)])
def test_quote_price_clv_requires_two_valid_decimal_prices(taken, close):
    assert clv.quote_price_clv_pct(taken, close) is None


def test_summary_derives_corrected_clv_and_keeps_legacy_rows_unchanged(tmp_db):
    conn = tmp_db.get_conn()
    for taken, close, legacy in [(3.0, 2.5, -6.666667), (2.0, None, None), (0.5, 2.0, 150.0)]:
        conn.execute(
            "INSERT INTO clv_log (odds_taken_decimal, closing_odds_decimal, clv_pct, market_book) VALUES (?, ?, ?, 'Book')",
            (taken, close, legacy),
        )
    conn.commit()
    before = [tuple(r) for r in conn.execute("SELECT * FROM clv_log ORDER BY id")]
    conn.close()

    summary = clv.compute_clv_summary()
    assert summary["n_bets"] == 3
    assert summary["quote_price_clv_pct"] == 20.0
    assert summary["legacy_signed_clv_pct"] == summary["avg_clv_pct"]
    assert summary["coverage"] == {
        "denominator": "recorded_clv_rows",
        "recorded_rows": 3,
        "valid_quote_pairs": 1,
        "missing_quote_pairs": 1,
        "invalid_quote_pairs": 1,
        "quote_pair_coverage_pct": 33.33,
    }
    assert summary["quote_price_clv_provenance"]["version"] == "quoted_price_v1"
    assert summary["quote_price_clv_provenance"]["devig_applied"] is False
    assert summary["qualified_clv_pct"] is None
    assert summary["quote_price_clv_provenance"]["close_verified"] is False
    assert summary["quote_price_clv_provenance"]["source_qualification"] == "unverified_legacy_close"
    assert "recorded prices only" in summary["quote_price_clv_provenance"]["qualification_reason"]
    assert summary["fair_close_ev_pct"] is None
    by_book = clv.compute_clv_summary_by_book()["by_book"][0]
    assert by_book["quote_price_clv_pct"] == 20.0
    assert by_book["qualified_clv_pct"] is None
    assert by_book["quote_price_clv_provenance"]["close_verified"] is False
    assert by_book["coverage"]["valid_quote_pairs"] == 1
    conn = tmp_db.get_conn()
    assert [tuple(r) for r in conn.execute("SELECT * FROM clv_log ORDER BY id")] == before
    conn.close()


def test_record_keeps_legacy_return_but_summary_exposes_correct_sign(tmp_db, monkeypatch):
    monkeypatch.setattr(clv, "is_enabled", lambda _: True)
    assert clv.record_clv(1, "golfer", "matchup", 3.0, 2.5) == pytest.approx(-100.0 / 15.0)
    assert clv.compute_clv_summary()["quote_price_clv_pct"] == 20.0


def test_empty_summary_does_not_claim_a_zero_edge(tmp_db):
    summary = clv.compute_clv_summary()
    assert summary["quote_price_clv_pct"] is None
    assert summary["coverage"]["quote_pair_coverage_pct"] is None
