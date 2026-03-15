import pytest

from backtester.checkpoint_replay import assert_checkpoint_temporal_integrity


def test_checkpoint_temporal_integrity_raises_on_leakage(monkeypatch):
    class FakeConn:
        def execute(self, *_args, **_kwargs):
            class Row(dict):
                def __getitem__(self, item):
                    return super().get(item)

            return type("Result", (), {"fetchone": lambda _self: Row(max_source_date="2026-03-20")})()

        def close(self):
            return None

    monkeypatch.setattr("backtester.checkpoint_replay.db.get_conn", lambda: FakeConn())

    with pytest.raises(ValueError):
        assert_checkpoint_temporal_integrity("event", 2026, "2026-03-18")

