def test_rollback_policy_uses_previous_live_record(monkeypatch):
    from backtester import model_registry
    from backtester.strategy import StrategyConfig

    monkeypatch.setattr(
        model_registry,
        "set_live_weekly_model",
        lambda strategy, **kwargs: {"strategy": strategy, "scope": kwargs.get("scope", "global")},
    )
    monkeypatch.setattr(
        "backtester.model_registry.db.get_conn",
        lambda: type(
            "Conn",
            (),
            {
                "execute": lambda self, *_args, **_kwargs: type(
                    "Rows",
                    (),
                    {
                        "fetchall": lambda _self: [
                            {"id": 2, "strategy_config_json": StrategyConfig(name="new").to_json()},
                            {"id": 1, "strategy_config_json": StrategyConfig(name="old").to_json()},
                        ]
                    },
                )(),
                "close": lambda self: None,
            },
        )(),
    )
    out = model_registry.rollback_live_weekly_model(scope="global")
    assert out["strategy"].name == "old"

