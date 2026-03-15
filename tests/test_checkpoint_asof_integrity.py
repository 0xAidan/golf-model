from backtester.autoresearch_config import resolve_checkpoint_dates


def test_checkpoint_dates_are_generated_in_order():
    contract = {
        "checkpoints": [
            {"id": "pre_tournament", "offset_days_from_start": 0},
            {"id": "before_day_2", "offset_days_from_start": 1},
            {"id": "before_day_3", "offset_days_from_start": 2},
        ]
    }
    cps = resolve_checkpoint_dates("2026-03-10", contract)
    assert [c["id"] for c in cps] == ["pre_tournament", "before_day_2", "before_day_3"]
    assert [c["as_of_date"] for c in cps] == ["2026-03-10", "2026-03-11", "2026-03-12"]

