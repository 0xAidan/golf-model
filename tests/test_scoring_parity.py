"""compute_profit parity with trackRecord pl samples."""

from __future__ import annotations

from src.scoring import compute_profit, parse_odds_to_decimal


def test_compute_profit_matches_trackrecord_samples():
    win_cases = [
        ("+103", 1.03),
        ("+118", 1.18),
        ("-116", 0.86),
        ("-100", 1.0),
    ]
    for odds, expected_pl in win_cases:
        dec = parse_odds_to_decimal(odds)
        profit = compute_profit(1, 1.0, False, dec, 1.0)
        assert abs(profit - expected_pl) < 0.01, f"win {odds}: {profit} != {expected_pl}"

    dec = parse_odds_to_decimal("+182")
    loss = compute_profit(0, 0.0, False, dec, 1.0)
    assert abs(loss - (-1.0)) < 0.01
