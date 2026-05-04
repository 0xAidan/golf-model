"""Tests for CLV aggregation by sportsbook."""

from src.clv import CLV_SIGNIFICANCE_MIN_BETS, compute_clv_summary_by_book


def test_compute_clv_summary_by_book_groups(tmp_db):
    conn = tmp_db.get_conn()
    rows = [
        ("DraftKings", 1.5),
        ("DraftKings", 2.5),
        ("FanDuel", -1.0),
        (None, 0.5),
    ]
    for book, clv in rows:
        conn.execute(
            """
            INSERT INTO clv_log (
                tournament_id, player_key, bet_type, market_book,
                odds_taken_decimal, closing_odds_decimal,
                implied_taken, implied_closing, clv_pct
            )
            VALUES (1, 'p1', 'top10', ?, 5.0, 5.0, 0.2, 0.18, ?)
            """,
            (book, clv),
        )
    conn.commit()
    conn.close()

    summary = compute_clv_summary_by_book()
    assert summary["overall"]["n_bets"] == 4
    by_book = {b["market_book"]: b for b in summary["by_book"]}
    assert by_book["DraftKings"]["n_bets"] == 2
    assert by_book["FanDuel"]["n_bets"] == 1
    assert by_book["(unknown)"]["n_bets"] == 1
    assert summary["min_bets_for_significance"] == CLV_SIGNIFICANCE_MIN_BETS
